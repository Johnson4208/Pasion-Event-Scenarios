"""Synthetic coverage for consolidating latest source with local backend state."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import recover_state as recovery


ACCOUNT_EMAIL = 'synthetic-owner@example.invalid'
ACCOUNT_NAME = 'Private synthetic owner'
SALT = bytes(range(16))
PASSWORD_HASH = b'private-synthetic-password-hash!'


class RecoverStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.latest = self.project('latest', 'LATEST_BACKEND')
        self.old = self.project('older', 'OLD_BACKEND_MUST_NOT_REPLACE_LATEST')
        self.output = self.root / 'combined'

    def project(self, name, marker):
        path = self.root / name
        (path / 'backend').mkdir(parents=True)
        (path / 'src').mkdir()
        (path / 'package.json').write_text(json.dumps({'name': name}), encoding='utf-8')
        (path / 'backend' / 'server.py').write_text(marker, encoding='utf-8')
        (path / 'src' / 'App.jsx').write_text(marker + '_FRONTEND', encoding='utf-8')
        return path

    def create_db(self, relative, schema, root=None):
        path = (root or self.old) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript(schema)
        return path

    def accounts(self, *, extras=True, root=None):
        suffix = ', disabled INTEGER NOT NULL DEFAULT 0, created REAL, is_admin INTEGER NOT NULL DEFAULT 0' if extras else ''
        path = self.create_db('backend/accounts.sqlite3',
            'CREATE TABLE accounts(email TEXT PRIMARY KEY, name TEXT NOT NULL, '
            'salt BLOB NOT NULL, password_hash BLOB NOT NULL' + suffix + ');', root)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('INSERT INTO accounts(email,name,salt,password_hash) VALUES(?,?,?,?)',
                               (ACCOUNT_EMAIL, ACCOUNT_NAME, SALT, PASSWORD_HASH))
        return path

    def documents(self, *, original=True):
        path = self.create_db('backend/documents.sqlite3',
            'CREATE TABLE documents(id TEXT PRIMARY KEY, created REAL NOT NULL, content TEXT NOT NULL'
            + (', original BLOB' if original else '') + ');')
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('INSERT INTO documents(id,created,content) VALUES(?,?,?)',
                               ('document-1', 1234.5, json.dumps({'id': 'document-1', 'status': 'ready'})))
            if original:
                connection.execute('UPDATE documents SET original=?', (b'private original document bytes',))
        return path

    def finance(self):
        return self.create_db('backend/finance.sqlite3', '''
            CREATE TABLE issuers(ticker TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE calendars(ticker TEXT REFERENCES issuers(ticker), year TEXT,
                payload TEXT NOT NULL, PRIMARY KEY(ticker,year));
            CREATE TABLE reports(id TEXT PRIMARY KEY, ticker TEXT REFERENCES issuers(ticker), payload TEXT NOT NULL);
            CREATE TABLE facts(id TEXT PRIMARY KEY, ticker TEXT REFERENCES issuers(ticker), payload TEXT NOT NULL);
            CREATE TABLE definitions(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            INSERT INTO issuers VALUES('SYN','Synthetic issuer');
        ''')

    def rejected(self, **kwargs):
        with self.assertRaises(recovery.RecoveryError):
            recovery.assemble(self.latest, self.old, self.output, stopped=True, **kwargs)
        self.assertFalse(self.output.exists(), 'A failed recovery must not leave a partial application')

    @staticmethod
    def source_snapshot(path):
        return {str(file.relative_to(path)): (file.read_bytes(), file.stat().st_mtime_ns)
                for file in path.rglob('*') if file.is_file()}

    def test_assemble_retains_latest_code_and_complete_account_state(self):
        self.accounts()
        self.documents()
        self.finance()
        with closing(sqlite3.connect(self.old / 'backend/accounts.sqlite3')) as connection, connection:
            connection.executescript('''
                CREATE TABLE owned_data(owner TEXT REFERENCES accounts(email), namespace TEXT,
                    key TEXT, payload TEXT, PRIMARY KEY(owner,namespace,key));
                CREATE TABLE password_resets(email TEXT PRIMARY KEY, code_hash BLOB, expires REAL,
                    attempts INTEGER, sent_at REAL, account_hash BLOB);
            ''')
            connection.execute('UPDATE accounts SET disabled=1, created=1234.5, is_admin=1')
            connection.execute('INSERT INTO owned_data VALUES(?,?,?,?)',
                               (ACCOUNT_EMAIL, 'portfolio', 'positions', '{"private":"saved portfolio"}'))
            connection.execute('INSERT INTO password_resets VALUES(?,?,?,?,?,?)',
                               (ACCOUNT_EMAIL, b'old-code', 9999999999, 0, 1234.5, PASSWORD_HASH))
        with closing(sqlite3.connect(self.old / 'backend/finance.sqlite3')) as connection, connection:
            connection.execute('INSERT INTO reports VALUES(?,?,?)',
                               ('report-1', 'SYN', json.dumps({'document_id': 'document-1'})))
        before = self.source_snapshot(self.old)
        report = recovery.assemble(self.latest, self.old, self.output, stopped=True)
        self.assertIsInstance(report, dict)
        self.assertEqual((self.output / 'backend/server.py').read_text(), 'LATEST_BACKEND')
        self.assertEqual((self.output / 'src/App.jsx').read_text(), 'LATEST_BACKEND_FRONTEND')
        with closing(sqlite3.connect(self.output / 'backend/accounts.sqlite3')) as connection, connection:
            self.assertEqual(connection.execute('SELECT email,name,salt,password_hash,disabled,created,is_admin FROM accounts').fetchone(),
                             (ACCOUNT_EMAIL, ACCOUNT_NAME, SALT, PASSWORD_HASH, 1, 1234.5, 1))
            self.assertEqual(connection.execute('SELECT payload FROM owned_data').fetchone()[0],
                             '{"private":"saved portfolio"}')
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM password_resets').fetchone()[0], 0)
        with closing(sqlite3.connect(self.output / 'backend/documents.sqlite3')) as connection, connection:
            self.assertEqual(connection.execute('SELECT original FROM documents').fetchone()[0],
                             b'private original document bytes')
        self.assertEqual(before, self.source_snapshot(self.old))

    def test_legacy_accounts_and_documents_without_new_optional_columns_are_accepted(self):
        self.accounts(extras=False)
        self.documents(original=False)
        recovery.assemble(self.latest, self.old, self.output, stopped=True)
        with closing(sqlite3.connect(self.output / 'backend/accounts.sqlite3')) as connection, connection:
            self.assertEqual(connection.execute('SELECT salt,password_hash FROM accounts').fetchone(), (SALT, PASSWORD_HASH))
        self.assertTrue((self.output / 'backend/documents.sqlite3').is_file())

    def test_all_recognized_stores_are_preserved_and_only_transient_lease_is_cleared(self):
        self.accounts()
        self.documents()
        self.finance()
        schemas = {
            'backend/macro.sqlite3': '''
                CREATE TABLE series(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE vintages(id TEXT PRIMARY KEY,series_id TEXT REFERENCES series(id),payload TEXT NOT NULL);
                CREATE TABLE exposures(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                INSERT INTO series VALUES('series-1','{}');
                INSERT INTO vintages VALUES('vintage-1','series-1','{"known_at":"2025-01-01","reviewed":true}');''',
            'backend/stock_models.sqlite3': '''
                CREATE TABLE models(id TEXT PRIMARY KEY,ticker TEXT,horizon INTEGER,frozen_at TEXT,expires_at TEXT,payload TEXT);
                CREATE TABLE evaluations(id TEXT PRIMARY KEY,model_id TEXT,known_at TEXT,payload TEXT);
                INSERT INTO models VALUES('model-1','SYN',21,'2025-01-01','2025-02-01','{"status":"UNVALIDATED"}');
                INSERT INTO evaluations VALUES('evaluation-1','model-1','2025-02-02','{}');''',
            'backend/technical.sqlite3': '''
                CREATE TABLE snapshots(id TEXT PRIMARY KEY,ticker TEXT,known_at TEXT,payload TEXT);
                INSERT INTO snapshots VALUES('snapshot-1','SYN','2025-01-01','{"provider_verified":false}');''',
            'event-agent-state/intelligence.sqlite3': '''
                CREATE TABLE watches(id TEXT PRIMARY KEY,category TEXT NOT NULL,factor TEXT NOT NULL,
                    focus TEXT NOT NULL,horizon TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,UNIQUE(category,factor,focus,horizon));
                CREATE TABLE versions(id INTEGER PRIMARY KEY AUTOINCREMENT,watch_id TEXT REFERENCES watches(id),
                    created_at TEXT NOT NULL,content_hash TEXT NOT NULL,snapshot_json TEXT NOT NULL,change_json TEXT NOT NULL);
                CREATE TABLE polls(id INTEGER PRIMARY KEY AUTOINCREMENT,watch_id TEXT REFERENCES watches(id),
                    checked_at TEXT NOT NULL,status TEXT NOT NULL,reason TEXT,version_id INTEGER);
                CREATE TABLE lease(name TEXT PRIMARY KEY,holder TEXT NOT NULL,until_epoch REAL NOT NULL);
                INSERT INTO watches VALUES('watch-1','Economy','Inflation','World','30 days',1,'2026-01-01');
                INSERT INTO lease VALUES('poller','old-process',9999999999);''',
            'backend/private-event-models/outcomes.sqlite3': '''
                CREATE TABLE outcome_snapshots(id TEXT PRIMARY KEY,profile_id TEXT NOT NULL,retrieved_at TEXT NOT NULL,metadata TEXT NOT NULL);
                CREATE TABLE outcome_observations(snapshot_id TEXT NOT NULL,observation_key TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(snapshot_id,observation_key));
                CREATE TABLE outcome_raw_responses(snapshot_id TEXT NOT NULL,page INTEGER NOT NULL,source_url TEXT NOT NULL,sha256 TEXT NOT NULL,body BLOB NOT NULL,PRIMARY KEY(snapshot_id,page));
                INSERT INTO outcome_snapshots VALUES('snapshot-1','profile-1','2025-01-01','{"point_in_time_ready":false}');
                INSERT INTO outcome_observations VALUES('snapshot-1','observation-1','{"adjudication_status":"UNREVIEWED","known_at":"2025-01-01"}');
                INSERT INTO outcome_raw_responses VALUES('snapshot-1',0,'https://example.invalid/data','synthetic-hash',X'010203');''',
        }
        for path, schema in schemas.items():
            self.create_db(path, schema)
        original_contents = {}
        for path in schemas:
            if path != 'event-agent-state/intelligence.sqlite3':
                with closing(sqlite3.connect(self.old / path)) as connection:
                    original_contents[path] = list(connection.iterdump())
        recovery.assemble(self.latest, self.old, self.output, stopped=True)
        for path in schemas:
            self.assertTrue((self.output / path).is_file(), path)
            if path in original_contents:
                with closing(sqlite3.connect(self.output / path)) as connection:
                    self.assertEqual(list(connection.iterdump()), original_contents[path])
        with closing(sqlite3.connect(self.output / 'event-agent-state/intelligence.sqlite3')) as connection, connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM lease').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT id FROM watches').fetchone()[0], 'watch-1')
        with closing(sqlite3.connect(self.old / 'event-agent-state/intelligence.sqlite3')) as connection, connection:
            self.assertEqual(connection.execute('SELECT holder FROM lease').fetchone()[0], 'old-process')

    def test_committed_wal_is_recovered_without_opening_or_modifying_source_database(self):
        path = self.old / 'backend/accounts.sqlite3'
        connection = sqlite3.connect(path)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA wal_autocheckpoint=0')
            connection.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY,name TEXT NOT NULL,salt BLOB NOT NULL,password_hash BLOB NOT NULL)')
            connection.execute('INSERT INTO accounts VALUES(?,?,?,?)',
                               (ACCOUNT_EMAIL, ACCOUNT_NAME, SALT, PASSWORD_HASH))
            connection.commit()
            self.assertTrue(Path(str(path) + '-wal').is_file())
            before = self.source_snapshot(self.old)
            connect = sqlite3.connect

            def open_only_private_copies(database, *args, **kwargs):
                value = str(database)
                self.assertNotIn(str(self.old.resolve()), value, 'Original databases must not be opened')
                self.assertNotIn(self.old.resolve().as_uri(), value, 'Original databases must not be opened')
                return connect(database, *args, **kwargs)

            # An open but idle connection keeps the committed WAL on disk.
            with patch('sqlite3.connect', side_effect=open_only_private_copies):
                recovery.assemble(self.latest, self.old, self.output, stopped=True)
            self.assertEqual(before, self.source_snapshot(self.old))
            with closing(sqlite3.connect(self.output / 'backend/accounts.sqlite3')) as restored:
                self.assertEqual(restored.execute('SELECT email,password_hash FROM accounts').fetchone(),
                                 (ACCOUNT_EMAIL, PASSWORD_HASH))
            self.assertFalse((self.output / 'backend/accounts.sqlite3-wal').exists())
            self.assertFalse((self.output / 'backend/accounts.sqlite3-shm').exists())
        finally:
            connection.close()

    def test_private_configs_dependencies_and_old_code_are_not_copied(self):
        self.accounts()
        private_paths = ['.env', 'backend/.env', 'backend/mail-config.json',
                         '.git/config', '.venv/private.txt', 'node_modules/private.txt',
                         'backend/private-event-models/private-catalog.json']
        for root in (self.latest, self.old):
            for relative in private_paths:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('PRIVATE_CONFIGURATION_MUST_NOT_LEAK', encoding='utf-8')
        (self.latest / 'backend/accounts.sqlite3').write_bytes(b'LATEST_RUNTIME_MUST_NOT_BE_COPIED')
        recovery.assemble(self.latest, self.old, self.output, stopped=True)
        for relative in private_paths:
            self.assertFalse((self.output / relative).exists(), relative)
        with closing(sqlite3.connect(self.output / 'backend/accounts.sqlite3')) as connection, connection:
            self.assertEqual(connection.execute('SELECT email FROM accounts').fetchone()[0], ACCOUNT_EMAIL)

    def test_windows_case_variants_of_private_configs_and_runtime_directories_are_excluded(self):
        self.accounts()
        private_paths = ['backend/MAIL-CONFIG.JSON', 'backend/Credentials.Json',
                         'backend/PRIVATE-EVENT-MODELS/catalog.json',
                         'backend/NODE_MODULES/private.json', 'backend/VeNv/private.py']
        for relative in private_paths:
            path = self.latest / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('PRIVATE_SYNTHETIC_CONFIGURATION', encoding='utf-8')
        recovery.assemble(self.latest, self.old, self.output, stopped=True)
        for relative in private_paths:
            self.assertFalse((self.output / relative).exists(), relative)

    def test_inspection_and_reports_do_not_disclose_account_or_config_values(self):
        self.accounts()
        (self.old / 'backend/mail-config.json').write_text('{"password":"PRIVATE_SMTP_PASSWORD"}')
        before = self.source_snapshot(self.old)
        metadata = recovery.inspect_project(self.old)
        self.assertIsInstance(metadata, dict)
        self.assertTrue(metadata)
        serialized = json.dumps(metadata, default=str)
        for secret in (ACCOUNT_EMAIL, ACCOUNT_NAME, PASSWORD_HASH.decode(), 'PRIVATE_SMTP_PASSWORD'):
            self.assertNotIn(secret, serialized)
        self.assertEqual(before, self.source_snapshot(self.old))

    def test_recovery_requires_stopped_services_acknowledgment(self):
        self.accounts()
        with self.assertRaises(recovery.RecoveryError):
            recovery.assemble(self.latest, self.old, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_never_overwritten(self):
        self.accounts()
        self.output.mkdir()
        marker = self.output / 'existing-user-data'
        marker.write_text('KEEP')
        with self.assertRaises(recovery.RecoveryError):
            recovery.assemble(self.latest, self.old, self.output, stopped=True)
        self.assertEqual(marker.read_text(), 'KEEP')
        self.assertEqual(list(self.output.iterdir()), [marker])

    def test_output_cannot_be_nested_in_either_input(self):
        self.accounts()
        for root in (self.latest, self.old):
            with self.subTest(root=root.name):
                output = root / 'nested-output'
                with self.assertRaises(recovery.RecoveryError):
                    recovery.assemble(self.latest, self.old, output, stopped=True)
                self.assertFalse(output.exists())

    def test_incomplete_latest_and_state_projects_are_rejected(self):
        self.accounts()
        for root in (self.latest, self.old):
            with self.subTest(root=root.name):
                marker = root / 'recovery-INCOMPLETE.txt'
                marker.write_text('A previous operation was interrupted')
                before = self.source_snapshot(root)
                try:
                    self.rejected()
                    self.assertEqual(before, self.source_snapshot(root))
                    with self.assertRaises(recovery.RecoveryError):
                        recovery.inspect_project(root)
                finally:
                    marker.unlink()

    def test_required_project_structure_is_validated(self):
        self.accounts()
        for root in (self.latest, self.old):
            for relative in ('package.json', 'backend/server.py', 'src'):
                with self.subTest(root=root.name, missing=relative):
                    path = root / relative
                    held = root / ('held-' + path.name)
                    path.rename(held)
                    try:
                        self.rejected()
                    finally:
                        held.rename(path)

    def test_project_markers_must_have_the_expected_file_types(self):
        self.accounts()
        for root in (self.latest, self.old):
            for relative in ('package.json', 'backend/server.py', 'src'):
                with self.subTest(root=root.name, invalid=relative):
                    path = root / relative
                    held = root / ('held-' + path.name)
                    path.rename(held)
                    try:
                        if relative == 'src':
                            path.write_text('NOT_A_DIRECTORY')
                        else:
                            path.mkdir()
                        self.rejected()
                    finally:
                        if path.is_dir():
                            path.rmdir()
                        else:
                            path.unlink()
                        held.rename(path)

    def test_malformed_database_and_missing_core_columns_are_rejected(self):
        path = self.old / 'backend/accounts.sqlite3'
        for schema in (None, 'CREATE TABLE accounts(email TEXT PRIMARY KEY,name TEXT);'):
            with self.subTest(schema=schema):
                if schema is None:
                    path.write_bytes(b'not a SQLite database')
                else:
                    self.create_db('backend/accounts.sqlite3', schema)
                try:
                    self.rejected()
                finally:
                    path.unlink()

    def test_missing_document_and_finance_core_schema_is_rejected(self):
        self.accounts()
        for relative, schema in (
            ('backend/documents.sqlite3', 'CREATE TABLE documents(id TEXT PRIMARY KEY,created REAL);'),
            ('backend/finance.sqlite3', 'CREATE TABLE issuers(ticker TEXT PRIMARY KEY,name TEXT);'),
        ):
            with self.subTest(relative=relative):
                path = self.create_db(relative, schema)
                try:
                    self.rejected()
                finally:
                    path.unlink()

    def test_invalid_document_metadata_is_rejected_without_changing_source(self):
        self.accounts()
        path = self.documents()
        for content in ('invalidJSON', '[]', '42', '"scalar"', 'null'):
            with self.subTest(content=content):
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute('UPDATE documents SET content=?', (content,))
                before = self.source_snapshot(self.old)
                self.rejected()
                self.assertEqual(before, self.source_snapshot(self.old))

    def test_views_triggers_and_virtual_tables_are_rejected(self):
        for schema in (
            'CREATE VIEW imported_view AS SELECT email FROM accounts;',
            'CREATE TRIGGER imported_trigger AFTER UPDATE ON accounts BEGIN SELECT 1; END;',
            'CREATE VIRTUAL TABLE imported_search USING fts5(content);',
        ):
            with self.subTest(schema=schema):
                path = self.accounts()
                try:
                    with closing(sqlite3.connect(path)) as connection, connection:
                        try:
                            connection.execute(schema)
                        except sqlite3.OperationalError as error:
                            if 'fts5' in schema and 'no such module' in str(error):
                                continue
                            raise
                    self.rejected()
                finally:
                    path.unlink()

    def test_dangling_foreign_keys_are_rejected(self):
        path = self.accounts()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('CREATE TABLE owned_data(owner TEXT REFERENCES accounts(email),payload TEXT)')
            connection.execute('INSERT INTO owned_data VALUES(?,?)', ('missing@example.invalid', '{}'))
        self.rejected()

    def test_financial_document_links_require_matching_document_store(self):
        self.accounts()
        path = self.finance()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('INSERT INTO reports VALUES(?,?,?)',
                               ('report-1', 'SYN', json.dumps({'document_id': 'document-1'})))
        self.rejected()
        self.documents()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('UPDATE reports SET payload=?', (json.dumps({'document_id': 'missing-document'}),))
        self.rejected()

    def test_stage_document_links_and_malformed_report_json_are_rejected(self):
        self.accounts()
        self.documents()
        path = self.finance()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('CREATE TABLE finance_stages(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,payload TEXT NOT NULL)')
            connection.execute('INSERT INTO finance_stages VALUES(?,?,?)', ('stage-1', 'missing-document', '{}'))
        self.rejected()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('DELETE FROM finance_stages')
            connection.execute('INSERT INTO reports VALUES(?,?,?)', ('report-1', 'SYN', '{broken-json'))
        self.rejected()

    def test_symlinked_source_state_and_latest_code_are_rejected(self):
        external = self.root / 'outside.sqlite3'
        external.write_bytes(b'OUTSIDE_PRIVATE_FILE')
        state = self.old / 'backend/accounts.sqlite3'
        try:
            state.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest('Symbolic links are unavailable')
        self.rejected()
        state.unlink()
        self.accounts()
        code = self.latest / 'src/linked.txt'
        code.symlink_to(external)
        self.rejected()
        self.assertEqual(external.read_bytes(), b'OUTSIDE_PRIVATE_FILE')

    def test_orphaned_wal_and_nonempty_rollback_journal_are_rejected(self):
        wal = self.old / 'backend/accounts.sqlite3-wal'
        wal.write_bytes(b'ORPHANED_WAL')
        self.rejected()
        wal.unlink()
        self.accounts()
        (self.old / 'backend/accounts.sqlite3-journal').write_bytes(b'UNFINISHED_TRANSACTION')
        self.rejected()

    def test_logical_orphans_without_declared_foreign_keys_are_rejected(self):
        self.accounts()
        path = self.create_db('backend/stock_models.sqlite3', '''
            CREATE TABLE models(id TEXT PRIMARY KEY,ticker TEXT,horizon INTEGER,frozen_at TEXT,expires_at TEXT,payload TEXT);
            CREATE TABLE evaluations(id TEXT PRIMARY KEY,model_id TEXT,known_at TEXT,payload TEXT);
            INSERT INTO evaluations VALUES('evaluation-1','missing-model','2026-01-01','{}');
        ''')
        self.rejected()
        path.unlink()
        self.create_db('backend/private-event-models/outcomes.sqlite3', '''
            CREATE TABLE outcome_snapshots(id TEXT PRIMARY KEY,profile_id TEXT NOT NULL,retrieved_at TEXT NOT NULL,metadata TEXT NOT NULL);
            CREATE TABLE outcome_observations(snapshot_id TEXT NOT NULL,observation_key TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(snapshot_id,observation_key));
            CREATE TABLE outcome_raw_responses(snapshot_id TEXT NOT NULL,page INTEGER NOT NULL,source_url TEXT NOT NULL,sha256 TEXT NOT NULL,body BLOB NOT NULL,PRIMARY KEY(snapshot_id,page));
            INSERT INTO outcome_observations VALUES('missing-snapshot','observation-1','{}');
        ''')
        self.rejected()

    def test_source_changes_during_snapshot_are_detected_before_installation(self):
        path = self.accounts()
        original_copy = recovery.shutil.copyfile
        mutated = False

        def change_source_after_copy(source, destination, *args, **kwargs):
            nonlocal mutated
            result = original_copy(source, destination, *args, **kwargs)
            if Path(source) == path and not mutated:
                mutated = True
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute('UPDATE accounts SET name=?', ('Changed while copying',))
            return result

        with patch.object(recovery.shutil, 'copyfile', side_effect=change_source_after_copy):
            self.rejected()
        self.assertTrue(mutated)

    def test_state_changes_after_snapshot_and_during_installation_are_rejected(self):
        path = self.accounts()
        check = recovery._cross_checks
        move = recovery.shutil.move

        def change_source():
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('UPDATE accounts SET name=name || ?', (' changed',))

        def change_after_snapshot(staged):
            change_source()
            return check(staged)

        with patch.object(recovery, '_cross_checks', side_effect=change_after_snapshot):
            self.rejected()

        def change_during_installation(source, destination, *args, **kwargs):
            result = move(source, destination, *args, **kwargs)
            change_source()
            return result

        with patch.object(recovery.shutil, 'move', side_effect=change_during_installation):
            self.rejected()

    def test_latest_code_changes_after_copying_are_detected(self):
        self.accounts()
        copy = recovery.shutil.copyfile
        marker = self.latest / 'backend/server.py'
        before = self.source_snapshot(self.old)

        def change_previously_copied_code(source, destination, *args, **kwargs):
            result = copy(source, destination, *args, **kwargs)
            if Path(source) == self.latest / 'src/App.jsx':
                marker.write_text('NEWER_BACKEND_CHANGED_DURING_COPY')
            return result

        with patch.object(recovery.shutil, 'copyfile', side_effect=change_previously_copied_code):
            self.rejected()
        self.assertEqual(before, self.source_snapshot(self.old))

    def test_copied_state_must_match_fingerprint_even_if_original_path_is_restored(self):
        source = self.accounts()
        alternate_root = self.root / 'alternate'
        (alternate_root / 'backend').mkdir(parents=True)
        alternate = self.accounts(root=alternate_root)
        with closing(sqlite3.connect(alternate)) as connection, connection:
            connection.execute('UPDATE accounts SET name=?', ('Different copied state',))
        before = self.source_snapshot(self.old)
        copy = recovery.shutil.copyfile

        def swap_during_copy(path, destination, *args, **kwargs):
            if Path(path) != source:
                return copy(path, destination, *args, **kwargs)
            held = self.root / 'held-original.sqlite3'
            source.rename(held)
            alternate.rename(source)
            try:
                return copy(path, destination, *args, **kwargs)
            finally:
                source.rename(alternate)
                held.rename(source)

        with patch.object(recovery.shutil, 'copyfile', side_effect=swap_during_copy):
            self.rejected()
        self.assertEqual(before, self.source_snapshot(self.old))

    def test_failed_partial_cleanup_recreates_the_incomplete_marker(self):
        self.accounts()
        before = self.source_snapshot(self.old)
        move, remove = recovery.shutil.move, recovery.shutil.rmtree
        moved = 0

        def fail_after_one_move(source, destination, *args, **kwargs):
            nonlocal moved
            moved += 1
            if moved > 1:
                raise PermissionError('Synthetic Windows move failure')
            return move(source, destination, *args, **kwargs)

        def fail_after_removing_marker(path, *args, **kwargs):
            if Path(path) == self.output:
                (self.output / 'RECOVERY-INCOMPLETE.txt').unlink(missing_ok=True)
                raise PermissionError('Synthetic Windows locked output file')
            return remove(path, *args, **kwargs)

        with patch.object(recovery.shutil, 'move', side_effect=fail_after_one_move), \
                patch.object(recovery.shutil, 'rmtree', side_effect=fail_after_removing_marker):
            with self.assertRaisesRegex(recovery.RecoveryError, 'remains marked RECOVERY-INCOMPLETE'):
                recovery.assemble(self.latest, self.old, self.output, stopped=True)
        self.assertTrue((self.output / 'RECOVERY-INCOMPLETE.txt').is_file())
        self.assertEqual(before, self.source_snapshot(self.old))

    def test_failed_cleanup_and_marker_write_produce_an_explicit_unusable_output_error(self):
        self.accounts()
        remove, mark = recovery.shutil.rmtree, recovery._mark_incomplete
        marking = 0

        def mark_only_once(output):
            nonlocal marking
            marking += 1
            if marking > 1:
                raise PermissionError('Synthetic marker write denial')
            return mark(output)

        def fail_partial_cleanup(path, *args, **kwargs):
            if Path(path) == self.output:
                (self.output / 'RECOVERY-INCOMPLETE.txt').unlink(missing_ok=True)
                raise PermissionError('Synthetic cleanup denial')
            return remove(path, *args, **kwargs)

        with patch.object(recovery, '_mark_incomplete', side_effect=mark_only_once), \
                patch.object(recovery.shutil, 'move', side_effect=PermissionError('Synthetic move failure')), \
                patch.object(recovery.shutil, 'rmtree', side_effect=fail_partial_cleanup):
            with self.assertRaisesRegex(recovery.RecoveryError, 'could not be marked') as raised:
                recovery.assemble(self.latest, self.old, self.output, stopped=True)
        self.assertIn(str(self.output), str(raised.exception))
        self.assertTrue(self.output.exists())


if __name__ == '__main__':
    unittest.main()
