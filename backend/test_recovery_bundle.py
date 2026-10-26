"""Safety and fidelity checks for the source-only recovery review bundle."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_recovery_bundle.py"
SPEC = importlib.util.spec_from_file_location("prepare_recovery_bundle", SCRIPT)
bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bundle
SPEC.loader.exec_module(bundle)


class RecoveryBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.input = self.directory / "all-three.zip"
        self.output = self.directory / "source-review.zip"

    def write_zip(self, entries, *, compression=zipfile.ZIP_DEFLATED):
        with zipfile.ZipFile(self.input, "w", compression=compression) as archive:
            for name, data in entries:
                archive.writestr(name, data)

    def run_bundle(self, **kwargs):
        return bundle.prepare_bundle(self.input, self.output, **kwargs)

    def read_result(self):
        with zipfile.ZipFile(self.output) as archive:
            names = archive.namelist()
            content = {name: archive.read(name) for name in names}
        return content, json.loads(content[bundle.MANIFEST_NAME])

    def test_preserves_three_roots_source_bytes_and_config_templates(self):
        sources = {
            "old/backend/server.py": b"print('old')\r\n",
            "middle/src/App.jsx": "export default 'Tiếng Việt';\n".encode(),
            "latest/package.json": b'{"name":"pasion","scripts":{"dev":"vite"}}',
            "latest/.env.example": b"API_KEY=YOUR_API_KEY\nAPI_URL=http://localhost:8000\n",
            "latest/mail-config.example.json": b'{"smtp_password":"","host":"example.org"}',
            "latest/.github/workflows/test.yml": b"name: test\n",
            "latest/.gitignore": b"node_modules/\n",
        }
        self.write_zip(list(sources.items()))
        original_hash = hashlib.sha256(self.input.read_bytes()).hexdigest()
        summary = self.run_bundle()
        content, manifest = self.read_result()
        self.assertEqual(summary["top_level_names"], ["latest", "middle", "old"])
        self.assertEqual(set(content), set(sources) | {bundle.MANIFEST_NAME})
        for name, data in sources.items():
            self.assertEqual(content[name], data)
        self.assertEqual(hashlib.sha256(self.input.read_bytes()).hexdigest(), original_hash)
        self.assertEqual(manifest["preserved_top_level_names"], ["latest", "middle", "old"])
        indexed = {entry["path"]: entry for entry in manifest["source_files"]}
        self.assertEqual(indexed["old/backend/server.py"]["sha256"], hashlib.sha256(sources["old/backend/server.py"]).hexdigest())

    def test_private_files_and_sidecars_are_inventory_only(self):
        secret = b"PRIVATE-PASSWORD-HASH-DO-NOT-UPLOAD"
        private_paths = [
            "one/backend/accounts.sqlite3", "one/backend/accounts.sqlite3-wal",
            "one/backend/accounts.sqlite3-shm", "one/backend/accounts.sqlite-journal",
            "one/backend/accounts.sqlite3.bak", "one/backend/finance.db-journal",
            "two/.env", "two/.env.production", "two/production.env",
            "two/backend/mail-config.json", "two/backend/service-account.json",
            "three/private-event-models/catalog.json", "three/event-agent-state/state.json",
            "three/id_rsa", "three/key.pem", "three/backend/recovery-report.json",
            "three/RECOVERY-MANIFEST.json", "three/RECOVERY-INCOMPLETE.txt", "three/accounts.sql",
        ]
        self.write_zip([("one/backend/server.py", b"# source\n")] + [(name, secret) for name in private_paths])
        # Reject accidental reads, including database hashing or CRC checks.
        original_open = zipfile.ZipFile.open
        def guarded_open(archive, member, *args, **kwargs):
            name = member.filename if isinstance(member, zipfile.ZipInfo) else member
            if name in private_paths:
                raise AssertionError("private file contents must never be read")
            return original_open(archive, member, *args, **kwargs)
        from unittest.mock import patch
        with patch.object(zipfile.ZipFile, "open", guarded_open):
            summary = self.run_bundle()
        content, manifest = self.read_result()
        self.assertEqual(set(content), {"one/backend/server.py", bundle.MANIFEST_NAME})
        inventory = {entry["path"]: entry for entry in manifest["private_recovery_inventory"]}
        self.assertEqual(set(inventory), set(private_paths))
        self.assertEqual(summary["private_count"], len(private_paths))
        self.assertNotIn(secret, content[bundle.MANIFEST_NAME])
        self.assertNotIn(hashlib.sha256(secret).hexdigest().encode(), content[bundle.MANIFEST_NAME])
        for entry in inventory.values():
            self.assertEqual(set(entry), {"path", "size", "reason"})
            self.assertEqual(entry["size"], len(secret))

    def test_populated_secret_config_is_not_copied(self):
        self.write_zip([
            ("app.py", b"# keep source\n"),
            ("config.json", b'{"smtp":{"password":"ACTUAL-SECRET"}}'),
            ("settings.toml", b'API_KEY = "ACTUAL-SECRET"\n'),
            ("settings.yml", b'credentials: {password: ACTUAL-SECRET}\n'),
            (".env.example", b"API_KEY=ACTUAL-SECRET\n"),
            ("safe.json", b'{"host":"localhost","port":8000}'),
        ])
        self.run_bundle()
        content, manifest = self.read_result()
        self.assertEqual(set(content), {"app.py", "safe.json", bundle.MANIFEST_NAME})
        self.assertEqual({item["path"] for item in manifest["private_recovery_inventory"]},
                         {"config.json", "settings.toml", "settings.yml", ".env.example"})
        self.assertNotIn(b"ACTUAL-SECRET", b"".join(content.values()))

    def test_dependencies_binaries_and_generated_files_are_not_decompressed(self):
        excluded = ["a/.venv/Lib/site.py", "b/node_modules/lib/index.js", "b/.git/config",
                    "c/dist/index.html", "c/__pycache__/thing.pyc", "c/.cache/data.json",
                    "c/artifacts/report.json", "c/test-results/test.json", "c/logo.png",
                    "c/setup.exe", "c/node_modules/library/archive.zip"]
        self.write_zip([("a/src/index.js", b"export {};\n")] + [(name, b"not source") for name in excluded])
        original_open = zipfile.ZipFile.open
        def guarded_open(archive, member, *args, **kwargs):
            name = member.filename if isinstance(member, zipfile.ZipInfo) else member
            if name in excluded:
                raise AssertionError("excluded entry must not be decompressed")
            return original_open(archive, member, *args, **kwargs)
        from unittest.mock import patch
        with patch.object(zipfile.ZipFile, "open", guarded_open):
            self.run_bundle()
        content, manifest = self.read_result()
        self.assertEqual(set(content), {"a/src/index.js", bundle.MANIFEST_NAME})
        self.assertEqual(sum(manifest["ignored_file_counts"].values()), len(excluded))

    def test_unsafe_paths_are_rejected_without_output(self):
        for name in ["../escape.py", "/absolute.py", "C:/escape.py", "a/../../escape.py",
                     "a\\..\\escape.py", "a//file.py", "a/./file.py", "a/file.py:stream",
                     "a/NUL.py", "a/file.py.", "a/file.py "]:
            with self.subTest(name=name):
                self.write_zip([(name, b"source")])
                original = self.input.read_bytes()
                with self.assertRaises(bundle.BundleError):
                    self.run_bundle()
                self.assertEqual(self.input.read_bytes(), original)
                self.assertFalse(self.output.exists())

    def test_forbidden_windows_characters_are_rejected_without_changing_input(self):
        for char in '<>"|?*':
            with self.subTest(char=char):
                self.write_zip([(f"version/src/file{char}.py", b"# original")])
                original = self.input.read_bytes()
                with self.assertRaisesRegex(bundle.BundleError, "Windows"):
                    self.run_bundle()
                self.assertEqual(self.input.read_bytes(), original)
                self.assertFalse(self.output.exists())

    def test_duplicate_case_unicode_and_parent_file_collisions_are_rejected(self):
        cases = [
            [("a.py", b"1"), ("a.py", b"2")],
            [("One/App.py", b"1"), ("one/app.py", b"2")],
            [("caf\u00e9.py", b"1"), ("cafe\u0301.py", b"2")],
            [("backend", b"file"), ("backend/server.py", b"source")],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    self.write_zip(entries)
                with self.assertRaises(bundle.BundleError):
                    self.run_bundle()
                self.assertFalse(self.output.exists())

    def test_backslash_paths_are_preserved_as_portable_relative_paths(self):
        self.write_zip([("older\\backend\\server.py", b"# older\n")])
        self.run_bundle()
        content, _ = self.read_result()
        self.assertIn("older/backend/server.py", content)

    def test_symbolic_links_are_never_copied(self):
        symlink = zipfile.ZipInfo("source/link.py")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.write_zip([(symlink, b"/etc/passwd"), ("source/app.py", b"# app")])
        with self.assertRaises(bundle.BundleError):
            self.run_bundle()
        self.assertFalse(self.output.exists())
        dependency_link = zipfile.ZipInfo("source/.venv/bin/python")
        dependency_link.create_system = 3
        dependency_link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.write_zip([(dependency_link, b"/usr/bin/python"), ("source/app.py", b"# app")])
        self.run_bundle()
        content, _ = self.read_result()
        self.assertNotIn(dependency_link.filename, content)

    def test_no_overwrite_input_or_existing_output(self):
        self.write_zip([("app.py", b"# app")])
        original = self.input.read_bytes()
        with self.assertRaises(bundle.BundleError):
            bundle.prepare_bundle(self.input, self.input)
        self.output.write_bytes(b"keep existing output")
        with self.assertRaises(bundle.BundleError):
            self.run_bundle()
        self.assertEqual(self.output.read_bytes(), b"keep existing output")
        self.assertEqual(self.input.read_bytes(), original)

    def test_repeat_run_creates_identical_source_without_mutating_input(self):
        self.write_zip([("root/app.py", b"# unchanged\n")])
        original = self.input.read_bytes()
        self.run_bundle()
        second = self.directory / "second.zip"
        bundle.prepare_bundle(self.input, second)
        self.assertEqual(self.input.read_bytes(), original)
        # Source members are stable regardless of ZIP creation timestamps.
        with zipfile.ZipFile(self.output) as one, zipfile.ZipFile(second) as two:
            self.assertEqual(one.read("root/app.py"), two.read("root/app.py"))
            self.assertEqual(one.read(bundle.MANIFEST_NAME), two.read(bundle.MANIFEST_NAME))

    def test_size_and_count_limits_remove_only_new_output(self):
        self.write_zip([("one/app.py", b"# source\n"), ("two/app.py", b"# source\n")])
        original = self.input.read_bytes()
        for limits in [bundle.Limits(max_entries=1), bundle.Limits(max_declared_bytes=1),
                       bundle.Limits(max_source_file_bytes=1), bundle.Limits(max_source_bytes=10),
                       bundle.Limits(max_output_bytes=20)]:
            with self.subTest(limits=limits):
                with self.assertRaises(bundle.BundleError):
                    self.run_bundle(limits=limits)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.input.read_bytes(), original)

    def test_suspicious_expansion_ratio_is_bounded(self):
        self.write_zip([("source.py", b"a" * (2 * 1024**2))])
        with self.assertRaisesRegex(bundle.BundleError, "nén bất thường"):
            self.run_bundle(limits=bundle.Limits(max_expansion_ratio=2))
        self.assertFalse(self.output.exists())

    def test_nul_and_special_device_names_are_rejected_before_copying(self):
        nul_name = zipfile.ZipInfo("source.py\0hidden")
        with self.assertRaises(bundle.BundleError):
            bundle.safe_name(nul_name)
        device = zipfile.ZipInfo("source/device.py")
        device.create_system = 3
        device.external_attr = (stat.S_IFCHR | 0o600) << 16
        self.write_zip([(device, b"device")])
        with self.assertRaises(bundle.BundleError):
            self.run_bundle()
        self.assertFalse(self.output.exists())

    def test_private_inventory_bound_and_default_output_do_not_lose_original(self):
        self.write_zip([("app.py", b"# app"), ("accounts.sqlite3", b"private")])
        original = self.input.read_bytes()
        with self.assertRaises(bundle.BundleError):
            self.run_bundle(limits=bundle.Limits(max_private_entries=0))
        self.assertFalse(self.output.exists())
        summary = bundle.prepare_bundle(self.input)
        self.assertTrue(Path(summary["output"]).is_file())
        self.assertEqual(self.input.read_bytes(), original)

    def test_missing_inputs_and_missing_output_directory_are_actionable(self):
        with self.assertRaises(bundle.BundleError):
            self.run_bundle()
        self.write_zip([("app.py", b"# app")])
        with self.assertRaises(bundle.BundleError):
            bundle.prepare_bundle(self.input, self.directory / "missing" / "new.zip")
        self.assertTrue(self.input.exists())

    def test_empty_nested_only_bad_and_manifest_inputs_are_actionable(self):
        self.write_zip([("one.zip", b"not an expanded version")])
        with self.assertRaisesRegex(bundle.BundleError, "tệp nén con"):
            self.run_bundle()
        self.assertFalse(self.output.exists())
        self.input.write_bytes(b"not a zip")
        with self.assertRaises(bundle.BundleError):
            self.run_bundle()
        self.write_zip([(bundle.MANIFEST_NAME, b"{}"), ("source.py", b"# app")])
        with self.assertRaisesRegex(bundle.BundleError, "ZIP gốc"):
            self.run_bundle()

    def test_nested_versions_fail_before_output_even_with_readme_or_flat_source(self):
        nested_bytes = io.BytesIO()
        with zipfile.ZipFile(nested_bytes, "w") as archive:
            archive.writestr("package.json", '{"name":"pasion"}')
            archive.writestr("backend/server.py", "# version backend")
            archive.writestr("src/App.jsx", "export default function App() {}")
        cases = [
            [("README.md", b"# All three versions")] +
            [(f"version-{number}.zip", nested_bytes.getvalue()) for number in range(1, 4)],
            [("flat/package.json", b"{}"), ("flat/backend/server.py", b"# flat version")] +
            [(f"version-{number}.zip", nested_bytes.getvalue()) for number in range(2, 4)],
        ]
        from unittest.mock import patch
        for entries in cases:
            with self.subTest(paths=[name for name, _ in entries]):
                self.write_zip(entries)
                original = self.input.read_bytes()
                # The central directory is enough to reject this input. Even a
                # harmless README must not be copied before discovering omissions.
                with patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("must fail before reading members")):
                    with self.assertRaises(bundle.BundleError) as caught:
                        self.run_bundle()
                message = str(caught.exception)
                self.assertIn("Không tạo ZIP đầu ra", message)
                for name, _ in entries:
                    if name.endswith(".zip"):
                        self.assertIn(name, message)
                self.assertEqual(self.input.read_bytes(), original)
                self.assertFalse(self.output.exists())

    def test_common_nested_archive_formats_are_rejected(self):
        suffixes = [".ZIP", ".zipx", ".7Z", ".rar", ".tar", ".tar.gz", ".tgz", ".tar.bz2",
                    ".tbz", ".tbz2", ".tar.xz", ".txz", ".tar.lz", ".tar.lzma", ".tlz",
                    ".tar.zst", ".tzst", ".tar.Z", ".taz", ".tar.lz4"]
        for suffix in suffixes:
            with self.subTest(suffix=suffix):
                self.write_zip([("README.md", b"# Versions"), ("older/version" + suffix, b"archive")])
                original = self.input.read_bytes()
                with self.assertRaisesRegex(bundle.BundleError, "tệp nén con"):
                    self.run_bundle()
                self.assertEqual(self.input.read_bytes(), original)
                self.assertFalse(self.output.exists())
        # A filename resembling private state does not exempt a whole archive;
        # only excluded directories are safe to omit without inspecting it.
        for name in ["version/accounts.sqlite3.zip", "version/.env.zip"]:
            with self.subTest(name=name):
                self.write_zip([("README.md", b"# Versions"), (name, b"archive")])
                with self.assertRaisesRegex(bundle.BundleError, "tệp nén con"):
                    self.run_bundle()
                self.assertFalse(self.output.exists())

    def test_nested_archives_in_excluded_directories_are_not_opened(self):
        ignored = ["version/node_modules/lib/archive.zip", "version/.venv/archive.7z",
                   "version/artifacts/archive.tar.gz", "version/.cache/archive.rar"]
        private = ["version/private-event-models/archive.zip", "version/event-agent-state/archive.tar.xz"]
        self.write_zip([("version/app.py", b"# source")] + [(name, b"private or generated") for name in ignored + private])
        original_open = zipfile.ZipFile.open
        def guarded_open(archive, member, *args, **kwargs):
            name = member.filename if isinstance(member, zipfile.ZipInfo) else member
            if name in ignored + private:
                raise AssertionError("excluded archives must not be opened")
            return original_open(archive, member, *args, **kwargs)
        from unittest.mock import patch
        with patch.object(zipfile.ZipFile, "open", guarded_open):
            self.run_bundle()
        content, manifest = self.read_result()
        self.assertEqual(set(content), {"version/app.py", bundle.MANIFEST_NAME})
        self.assertEqual({entry["path"] for entry in manifest["private_recovery_inventory"]}, set(private))
        self.assertEqual(sum(manifest["ignored_file_counts"].values()), len(ignored))

    def test_nested_archive_error_lists_only_bounded_paths(self):
        paths = [f"version-{number}/" + "long-name-" * 20 + ".zip" for number in range(8)]
        self.write_zip([("README.md", b"# Versions")] + [(name, b"archive") for name in paths])
        with self.assertRaises(bundle.BundleError) as caught:
            self.run_bundle()
        message = str(caught.exception)
        self.assertIn("8 tệp nén con", message)
        self.assertIn("và 3 tệp khác", message)
        self.assertIn("version-0/", message)
        self.assertNotIn("version-5/", message)
        self.assertLess(len(message), 1500)
        self.assertFalse(self.output.exists())

    def test_cli_nested_archive_failure_does_not_announce_or_leave_output(self):
        self.write_zip([("README.md", b"# Versions"), ("older.zip", b"archive")])
        original = self.input.read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), "--input", str(self.input),
                                 "--output", str(self.output)], capture_output=True, text=True,
                                encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn("older.zip", result.stderr)
        self.assertIn("Không tạo ZIP đầu ra", result.stderr)
        self.assertNotIn("Đã tạo:", result.stdout)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.input.read_bytes(), original)

    def test_cli_works_without_tkinter_or_external_dependencies(self):
        self.write_zip([("one/app.py", b"# one")])
        result = subprocess.run([sys.executable, str(SCRIPT), "--input", str(self.input),
                                 "--output", str(self.output)], capture_output=True, text=True,
                                encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.output), result.stdout)
        self.assertTrue(zipfile.is_zipfile(self.output))


if __name__ == "__main__":
    unittest.main()
