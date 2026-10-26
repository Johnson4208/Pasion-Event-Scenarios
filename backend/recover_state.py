"""Build a new project from current source and one stopped project's state.

Uses only the standard library. Never imports or executes the old application.
Original databases are copied with their WAL into a private staging directory;
only the copies are opened with SQLite. No rows or credentials are printed.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time


class RecoveryError(Exception):
    """Recovery cannot safely proceed."""


def _safe_errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except sqlite3.Error:
            raise RecoveryError("A database is unreadable or incompatible. Original data was not changed.") from None
        except OSError:
            raise RecoveryError("A file could not be read or written. Check permissions and free disk space.") from None
    return checked


STORES = {
    "backend/accounts.sqlite3": {
        "accounts": {"email", "name", "salt", "password_hash"}},
    "backend/documents.sqlite3": {
        "documents": {"id", "created", "content"}},
    "backend/finance.sqlite3": {
        "issuers": {"ticker", "name"}, "calendars": {"ticker", "year", "payload"},
        "reports": {"id", "ticker", "payload"},
        "facts": {"id", "ticker", "payload"}, "definitions": {"id", "payload"}},
    "backend/macro.sqlite3": {
        "series": {"id", "payload"}, "vintages": {"id", "series_id", "payload"},
        "exposures": {"id", "payload"}},
    "backend/stock_models.sqlite3": {
        "models": {"id", "ticker", "horizon", "frozen_at", "expires_at", "payload"},
        "evaluations": {"id", "model_id", "known_at", "payload"}},
    "backend/technical.sqlite3": {
        "snapshots": {"id", "ticker", "known_at", "payload"}},
    "event-agent-state/intelligence.sqlite3": {
        "watches": {"id", "category", "factor", "focus", "horizon", "enabled", "created_at"},
        "versions": {"id", "watch_id", "created_at", "content_hash", "snapshot_json", "change_json"},
        "polls": {"id", "watch_id", "checked_at", "status", "reason", "version_id"},
        "lease": {"name", "holder", "until_epoch"}},
    "backend/private-event-models/outcomes.sqlite3": {
        "outcome_snapshots": {"id", "profile_id", "retrieved_at", "metadata"},
        "outcome_observations": {"snapshot_id", "observation_key", "payload"},
        "outcome_raw_responses": {"snapshot_id", "page", "source_url", "sha256", "body"}},
}
MAX_STATE_BYTES = 16 * 1024**3
MAX_SOURCE_BYTES = 512 * 1024**2
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "artifacts",
             "__pycache__", ".pytest_cache", ".cache", ".mypy_cache",
             "test-results", "playwright-report", "event-agent-state", "private-event-models"}
SOURCE_DIRS = {".github", "backend", "public", "scripts", "src", "tests", "unit"}
SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".json",
                   ".scss", ".css", ".html", ".md", ".txt", ".yml", ".yaml",
                   ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".ttf",
                   ".woff", ".woff2", ".cmd", ".bat", ".ps1", ".sh"}
SOURCE_SUFFIXES.update({".toml", ".ini", ".cfg", ".sql", ".lock"})
PRIVATE_NAMES = {"mail-config.json", "recovery-manifest.json", "delivery.json",
                 "credentials.json", "secrets.json", "config.local.json", "recovery-incomplete.txt"}
WARNINGS = [
    "State comes from one selected version; records from other versions were not merged.",
    "Both applications and the independent event agent must remain stopped during recovery.",
    "SQLite checks do not prove semantic compatibility of arbitrary older versions.",
    "Passwords and roles are retained; sessions and pending reset codes do not survive restart.",
    "SMTP credentials, environment variables and private model JSON catalogs were not copied.",
    "Custom external database paths are not followed; only documented project-local stores are recovered.",
    "Browser localStorage is separate: keep the same browser profile and URL to retain saved research.",
    "This output contains private data. Do not upload it or commit it to Git.",
]


def _safe_path(value: Path | str) -> Path:
    path = Path(os.path.abspath(value))
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise RecoveryError("Symlinks and junctions are not supported. Select the real project folder.")
    return path.resolve()


def _project(value: Path | str) -> Path:
    root = _safe_path(value)
    for name in ("package.json", "backend/server.py", "src"):
        path = _safe_path(root / name)
        valid_type = path.is_dir() if name == "src" else path.is_file()
        if not valid_type or not path.is_relative_to(root):
            raise RecoveryError("Select a project folder containing package.json, backend/server.py and src.")
    if any(path.name.casefold() == "recovery-incomplete.txt" for path in root.iterdir()):
        raise RecoveryError("The selected project has an incomplete recovery marker. Select an intact original project.")
    return root


def _state_files(root: Path) -> dict[str, Path]:
    paths = {}
    total = 0
    for relative in STORES:
        base = root / relative
        for suffix in ("", "-wal", "-shm", "-journal"):
            path = base.with_name(base.name + suffix)
            if path.is_symlink():
                raise RecoveryError("A state store is a symlink; original folders were not changed.")
            checked = _safe_path(path)
            if not checked.is_relative_to(root):
                raise RecoveryError("A state path escapes the selected project folder.")
            if checked.exists():
                if not checked.is_file():
                    raise RecoveryError("A state-store path is not a regular file.")
                if suffix == "-journal" and checked.stat().st_size:
                    raise RecoveryError("A rollback journal exists. Close the application cleanly before recovery.")
                if suffix in ("", "-wal"):
                    total += checked.stat().st_size
                    paths[relative + suffix] = checked
        if not base.is_file() and base.with_name(base.name + "-wal").exists():
            raise RecoveryError("A WAL has no main database; restore its matching database first.")
    if total > MAX_STATE_BYTES:
        raise RecoveryError("Local state exceeds the 16 GiB recovery limit; use an operator-assisted backup.")
    return paths


def _file_fingerprint(path: Path) -> tuple:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    attributes = lambda value: (value.st_size, value.st_mtime_ns, value.st_ino)
    if attributes(before) != attributes(after):
        raise RecoveryError("Source files changed. Stop editing and close both applications and the event agent, then retry.")
    return (*attributes(after), digest.hexdigest())


def _fingerprint(root: Path) -> dict:
    return {name: _file_fingerprint(path) for name, path in _state_files(root).items()}


def _verify_copy(path: Path, expected: tuple) -> None:
    actual = _file_fingerprint(path)
    if (actual[0], actual[-1]) != (expected[0], expected[-1]):
        raise RecoveryError("A source file changed while it was copied. No output project was installed.")


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def _open(path: Path):
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 60
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        yield db
    finally:
        db.close()


def _validate(path: Path, relative: str) -> dict:
    with _open(path) as db:
        objects = list(db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        if any(kind in ("trigger", "view") or "VIRTUAL TABLE" in (sql or "").upper()
               for kind, _, sql in objects):
            raise RecoveryError("Unsupported triggers, views or virtual tables in " + relative)
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RecoveryError("Database integrity check failed: " + relative)
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise RecoveryError("Database has broken foreign-key links: " + relative)
        tables = {}
        for kind, name, _ in objects:
            if kind == "table":
                columns = [row[1] for row in db.execute("PRAGMA table_info(" + _quoted(name) + ")")]
                tables[name] = {"name": name, "columns": columns,
                                "rows": db.execute("SELECT count(*) FROM " + _quoted(name)).fetchone()[0]}
        for name, required in STORES[relative].items():
            if name not in tables or not required.issubset(tables[name]["columns"]):
                raise RecoveryError("Missing or incompatible table schema in " + relative + ": " + name)
        if relative == "backend/accounts.sqlite3":
            invalid = db.execute("SELECT count(*) FROM accounts WHERE typeof(salt)!='blob' "
                                 "OR length(salt)!=16 OR typeof(password_hash)!='blob' "
                                 "OR length(password_hash)!=32").fetchone()[0]
            if invalid:
                raise RecoveryError("Account password format is unsupported; passwords were not modified.")
        if relative == "backend/documents.sqlite3":
            for (payload,) in db.execute("SELECT content FROM documents"):
                try:
                    if not isinstance(json.loads(payload), dict):
                        raise ValueError()
                except (ValueError, TypeError, RecursionError):
                    raise RecoveryError("A document has incompatible metadata; original documents were not modified.") from None
        return {"path": relative, "present": True, "bytes": path.stat().st_size,
                "tables": list(tables.values()), "integrity": "ok"}


def _snapshot(root: Path, destination: Path) -> list[dict]:
    before = _fingerprint(root)
    stores = []
    with tempfile.TemporaryDirectory(prefix="pasion-state-", dir=destination.parent) as directory:
        clone = Path(directory)
        for name in before:
            path = clone / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, path)
        if _fingerprint(root) != before:
            raise RecoveryError("Source data changed during copying. Stop the application and retry.")
        for name, fingerprint in before.items():
            _verify_copy(clone / name, fingerprint)
        for relative in STORES:
            path = clone / relative
            if not path.exists():
                stores.append({"path": relative, "present": False})
                continue
            _validate(path, relative)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # Backup reads the private clone and its committed WAL, never the original.
            with _open(path) as source, closing(sqlite3.connect(target)) as output:
                deadline = time.monotonic() + 60
                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise RecoveryError("SQLite backup timed out; no output project was installed.")
                source.backup(output, pages=256, progress=progress, sleep=0.05)
            stores.append(_validate(target, relative))
        if _fingerprint(root) != before:
            raise RecoveryError("Source changed during verification. No output project was installed.")
    return stores


def _cross_checks(root: Path) -> None:
    finance = root / "backend/finance.sqlite3"
    documents = root / "backend/documents.sqlite3"
    if finance.exists():
        with _open(finance) as db:
            db.execute("ATTACH DATABASE ? AS recovered_docs",
                       ((documents.as_uri() + "?mode=ro") if documents.exists() else ":memory:",))
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "finance_stages" in tables:
                columns = {row[1] for row in db.execute("PRAGMA table_info(finance_stages)")}
                if not {"id", "document_id", "payload"}.issubset(columns):
                    raise RecoveryError("Unsupported finance stage schema.")
                if not documents.exists():
                    missing = db.execute("SELECT 1 FROM finance_stages LIMIT 1").fetchone()
                else:
                    missing = db.execute("SELECT 1 FROM finance_stages s LEFT JOIN recovered_docs.documents d "
                                         "ON d.id=s.document_id WHERE d.id IS NULL LIMIT 1").fetchone()
                if missing:
                    raise RecoveryError("Finance stages reference missing documents; select the complete original project.")
            for (payload,) in db.execute("SELECT payload FROM reports"):
                try:
                    record = json.loads(payload)
                    if not isinstance(record, dict):
                        raise ValueError()
                except (ValueError, TypeError):
                    raise RecoveryError("A financial report has an incompatible payload.") from None
                ident = record.get("document_id")
                if ident and (not documents.exists() or not db.execute(
                        "SELECT 1 FROM recovered_docs.documents WHERE id=?", (ident,)).fetchone()):
                    raise RecoveryError("A financial report references a missing document.")
    for relative, query in (
        ("backend/stock_models.sqlite3", "SELECT 1 FROM evaluations e LEFT JOIN models m ON m.id=e.model_id WHERE m.id IS NULL LIMIT 1"),
        ("backend/private-event-models/outcomes.sqlite3", "SELECT 1 FROM outcome_observations o LEFT JOIN outcome_snapshots s ON s.id=o.snapshot_id WHERE s.id IS NULL UNION ALL SELECT 1 FROM outcome_raw_responses o LEFT JOIN outcome_snapshots s ON s.id=o.snapshot_id WHERE s.id IS NULL LIMIT 1"),
    ):
        if (root / relative).exists():
            with _open(root / relative) as db:
                if db.execute(query).fetchone():
                    raise RecoveryError("State has broken logical links: " + relative)


@_safe_errors
def inspect_project(root: Path) -> dict:
    """Inspect a staged snapshot; never display records or open original DBs."""
    root = _project(root)
    with tempfile.TemporaryDirectory(prefix="pasion-inspect-") as directory:
        staged = Path(directory) / "snapshot"
        staged.mkdir(mode=0o700)
        stores = _snapshot(root, staged)
        _cross_checks(staged)
    return {"version": 1, "stores": stores, "warnings": WARNINGS}


def _source_files(root: Path):
    for folder, dirs, names in os.walk(root, followlinks=False):
        parent = Path(folder)
        dirs[:] = [name for name in sorted(dirs) if name.casefold() not in SKIP_DIRS and
                   (parent != root or name.casefold() in SOURCE_DIRS)]
        for name in dirs:
            _safe_path(parent / name)
        for name in sorted(names):
            path = parent / name
            folded = name.casefold()
            templates = {".env.example", ".env.sample", ".env.template"}
            dot_source = templates | {".gitignore", ".gitattributes", ".editorconfig"}
            if folded in PRIVATE_NAMES or (folded.startswith(".env") and folded not in templates) or (folded.startswith(".") and folded not in dot_source):
                continue
            if path.suffix.lower() not in SOURCE_SUFFIXES and folded not in dot_source:
                continue
            _safe_path(path)
            if not stat.S_ISREG(path.stat().st_mode):
                raise RecoveryError("Latest source contains a non-regular source file.")
            yield path


def _source_fingerprint(root: Path) -> dict:
    result, size = {}, 0
    for path in _source_files(root):
        size += path.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise RecoveryError("Source exceeds 512 MiB; remove generated files from a copy and retry.")
        result[path.relative_to(root).as_posix()] = _file_fingerprint(path)
    return result


def _mark_incomplete(output: Path) -> None:
    marker = _safe_path(output / "RECOVERY-INCOMPLETE.txt")
    with marker.open("w", encoding="utf-8") as stream:
        stream.write("Recovery was interrupted. Do not run this folder; select a new output and retry.\n")
        stream.flush()
        os.fsync(stream.fileno())


@_safe_errors
def assemble(latest: Path, state_source: Path, output: Path, *, stopped=False) -> dict:
    """Create a new complete project; never replace an existing destination."""
    if not stopped:
        raise RecoveryError("Stop both applications and the event agent; then use --stopped.")
    latest, state_source, output = _project(latest), _project(state_source), _safe_path(output)
    if output.exists():
        raise RecoveryError("Output already exists. Choose a new empty folder name.")
    if not output.parent.is_dir():
        raise RecoveryError("The output parent folder must already exist.")
    for source in (latest, state_source):
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise RecoveryError("Output must be a separate sibling folder, outside both project folders.")
    source_before = _source_fingerprint(latest)
    state_before = _fingerprint(state_source)

    def verify_inputs():
        _project(latest)
        _project(state_source)
        if _source_fingerprint(latest) != source_before or _fingerprint(state_source) != state_before:
            raise RecoveryError("Source files changed during recovery. No output project was installed; stop both applications and retry.")

    with tempfile.TemporaryDirectory(prefix=".pasion-recovery-", dir=output.parent) as directory:
        staged = Path(directory) / "project"
        staged.mkdir(mode=0o700)
        count = 0
        for name, fingerprint in source_before.items():
            source = _safe_path(latest / name)
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            _verify_copy(target, fingerprint)
            count += 1
        stores = _snapshot(state_source, staged)
        if not any(store["present"] for store in stores):
            raise RecoveryError("No recognized state databases found in the selected old project.")
        _cross_checks(staged)
        transient = {}
        for relative, table in (("backend/accounts.sqlite3", "password_resets"),
                                ("event-agent-state/intelligence.sqlite3", "lease")):
            if (staged / relative).exists():
                with closing(sqlite3.connect(staged / relative)) as db, db:
                    db.execute("PRAGMA trusted_schema=OFF")
                    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                    if exists:
                        transient[table] = db.execute("SELECT count(*) FROM " + _quoted(table)).fetchone()[0]
                        db.execute("DELETE FROM " + _quoted(table))
        stores = [_validate(staged / item["path"], item["path"]) if item["present"] else item for item in stores]
        report = {"version": 1, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "source_files": count, "stores": stores, "cleared_transient_rows": transient,
                  "warnings": WARNINGS, "private_data": True}
        with (staged / "recovery-manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        verify_inputs()
        # mkdir reserves a fresh destination. We never rename onto a preexisting folder.
        output.mkdir(mode=0o700)
        try:
            _mark_incomplete(output)
            for path in staged.iterdir():
                shutil.move(str(path), str(output / path.name))
            verify_inputs()
            (output / "RECOVERY-INCOMPLETE.txt").unlink()
        except BaseException:
            try:
                shutil.rmtree(output)
            except OSError:
                try:
                    _safe_path(output).mkdir(exist_ok=True)
                    _mark_incomplete(output)
                except (OSError, RecoveryError):
                    raise RecoveryError("Recovery and cleanup failed, and the partial output could not be marked. "
                                        "Do not run this folder; remove it manually: " + str(output)) from None
                raise RecoveryError("Recovery failed and the partial output could not be removed. "
                                    "It remains marked RECOVERY-INCOMPLETE.txt; do not run it. "
                                    "Choose a new output folder. Original projects were not changed.") from None
            raise
    return report


def _gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    window = tk.Tk()
    window.withdraw()
    try:
        if not messagebox.askokcancel("Khôi phục dữ liệu PASION", "Đóng cả hai bản PASION và Event Agent trước khi tiếp tục.\n\nMã mới được giữ; dữ liệu được lấy từ một bản cũ. Bản gốc không bị sửa."):
            return 0
        selected = filedialog.askdirectory(title="Chọn thư mục bản cũ chứa dữ liệu (có package.json)")
        if not selected:
            return 0
        latest = Path(__file__).resolve().parents[1]
        output = latest.parent / ("Pasion-recovered-" + time.strftime("%Y%m%d-%H%M%S"))
        assemble(latest, Path(selected), output, stopped=True)
        messagebox.showinfo("Đã tạo một bản hoàn chỉnh", "Thư mục mới:\n" + str(output) + "\n\nBản này có dữ liệu riêng tư; đừng gửi lên GitHub.\nXem BACKEND-RECOVERY.md để cài và chạy.")
        return 0
    except (RecoveryError, OSError, sqlite3.Error) as error:
        messagebox.showerror("Chưa khôi phục được", str(error))
        return 1
    finally:
        window.destroy()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gui", action="store_true")
    commands = parser.add_subparsers(dest="command")
    check = commands.add_parser("inspect", help="Print metadata only; old applications must be stopped.")
    check.add_argument("--source", required=True, type=Path)
    build = commands.add_parser("assemble", help="Create a new project from latest source and one old state set.")
    build.add_argument("--latest", type=Path, default=Path(__file__).resolve().parents[1])
    build.add_argument("--state-source", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--stopped", action="store_true", help="Confirm both apps and the event agent are stopped.")
    args = parser.parse_args(argv)
    if args.gui:
        return _gui()
    try:
        if args.command == "inspect":
            result = inspect_project(args.source)
        elif args.command == "assemble":
            result = assemble(args.latest, args.state_source, args.output, stopped=args.stopped)
        else:
            parser.print_help()
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RecoveryError, OSError, sqlite3.Error) as error:
        print("Recovery stopped: " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
