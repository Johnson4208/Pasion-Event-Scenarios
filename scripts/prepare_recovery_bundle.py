#!/usr/bin/env python3
"""Prepare a bounded, source-only review ZIP without extracting its input."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import unicodedata
import zipfile


MANIFEST_NAME = "RECOVERY-MANIFEST.json"
UPLOAD_LIMIT = 31 * 1024 * 1024
IGNORED_DIRS = {
    ".venv", "venv", "env", "node_modules", ".git", "dist", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache", ".parcel-cache",
    ".vite", ".next", "coverage", "htmlcov", "test-results", "playwright-report",
    "artifacts", "site-packages", ".tox", ".nox", ".idea", ".vscode",
}
PRIVATE_DIRS = {"event-agent-state", "private-event-models"}
ARCHIVE_SUFFIXES = (
    ".zip", ".zipx", ".7z", ".rar", ".tar", ".tar.gz", ".tgz", ".tar.bz2",
    ".tbz", ".tbz2", ".tar.xz", ".txz", ".tar.lz", ".tar.lzma", ".tlz",
    ".tar.zst", ".tzst", ".tar.z", ".taz", ".tar.lz4",
)
SOURCE_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue",
    ".svelte", ".css", ".scss", ".sass", ".less", ".html", ".htm", ".svg",
    ".json", ".jsonc", ".toml", ".ini", ".cfg", ".yaml", ".yml", ".md",
    ".txt", ".rst", ".sql", ".xml", ".bat", ".cmd", ".ps1", ".sh", ".bash",
    ".zsh", ".lock", ".graphql", ".gql", ".csv", ".example", ".sample",
    ".template", ".in",
}
SOURCE_NAMES = {
    ".gitignore", ".gitattributes", ".editorconfig", ".dockerignore", ".browserslistrc",
    ".nvmrc", ".npmignore", "dockerfile", "makefile", "license", "licence", "procfile",
}
PRIVATE_NAMES = {
    "mail-config.json", "credentials.json", "credential.json", "secrets.json",
    "secret.json", "accounts.json", "users.json", "sessions.json", "tokens.json",
    ".npmrc", ".pypirc", ".netrc", "_netrc", ".git-credentials", ".pgpass",
    ".htpasswd", ".my.cnf", "service-account.json", "service_account.json",
    "id_rsa", "id_ed25519", "id_dsa", "authorized_keys", "known_hosts",
}
DATABASE_RE = re.compile(r"\.(?:sqlite\d*|db)(?:$|[.\-])", re.I)
SECRET_KEY_RE = re.compile(
    r"^(?:password|passwd|pwd|passwordhash|passworddigest|smtp(?:password|pass)|"
    r"(?:api|access|auth|refresh|bearer|session|id)?token|apikey|secret|clientsecret|"
    r"secretkey|privatekey|signingkey|authorization|databaseurl|connectionstring)$"
)
ASSIGNMENT_RE = re.compile(
    r"(?=(?:^|[,{\s])[\"']?([A-Za-z_][A-Za-z0-9_.-]*)[\"']?\s*[:=]\s*([^,\n}]*))", re.M
)
RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}


class BundleError(Exception):
    """An input cannot safely be turned into a source review bundle."""


@dataclass(frozen=True)
class Limits:
    max_entries: int = 200_000
    max_declared_bytes: int = 20 * 1024**3
    max_source_file_bytes: int = 8 * 1024**2
    max_source_bytes: int = 256 * 1024**2
    max_expansion_ratio: int = 1000
    max_output_bytes: int = UPLOAD_LIMIT
    max_private_entries: int = 20_000


def safe_name(info: zipfile.ZipInfo) -> tuple[str, bool]:
    """Validate names for both POSIX and Windows, without touching disk."""
    original = info.orig_filename
    if "\0" in original or original != info.filename:
        raise BundleError("ZIP chứa tên đường dẫn có ký tự NUL không hợp lệ.")
    name = original.replace("\\", "/")
    is_dir = name.endswith("/")
    if is_dir:
        name = name[:-1]
    if not name or len(name) > 1024 or name.startswith("/"):
        raise BundleError(f"Đường dẫn ZIP không an toàn: {original!r}")
    parts = name.split("/")
    for part in parts:
        if (part in {"", ".", ".."} or any(char in '<>:"|?*' for char in part)
                or part.endswith((" ", "."))
                or any(ord(char) < 32 for char in part)
                or part.split(".", 1)[0].casefold() in RESERVED_NAMES):
            raise BundleError(f"Đường dẫn ZIP không an toàn trên Windows: {original!r}")
    return name, is_dir


def is_template(name: str) -> bool:
    return name.endswith((".example", ".sample", ".template", ".example.json", ".sample.json", ".template.json"))


def classify(name: str) -> str:
    parts = name.casefold().split("/")
    base = parts[-1]
    if any(part in IGNORED_DIRS for part in parts[:-1]):
        return "dependencies-or-generated"
    if any(part in PRIVATE_DIRS for part in parts[:-1]):
        return "private-runtime-directory"
    if base.endswith(ARCHIVE_SUFFIXES):
        return "nested-archive"
    if (base in {"recovery-manifest.json", "recovery-incomplete.txt"} or
            re.match(r"^(?:backend-)?recover(?:y)?[-_].*(?:report|inventory|manifest).*\.json$", base)):
        return "private-recovery-report"
    if DATABASE_RE.search(base):
        return "private-database-or-sidecar"
    if (base in PRIVATE_NAMES or base.endswith((".pem", ".key", ".p12", ".pfx", ".jks"))
            or ((base.startswith(".env") or base.endswith(".env")) and not is_template(base))
            or re.match(r"^(?:credentials?|secrets?|tokens?|accounts?|users?|sessions?)\.(?:json|ya?ml|toml|ini|csv|sql|bak)$", base)):
        return "private-configuration"
    if (base in SOURCE_NAMES or Path(base).suffix in SOURCE_SUFFIXES
            or (is_template(base) and ".env" in base)):
        return "source"
    return "binary-or-other"


def _nonempty_secret(value: object) -> bool:
    if value is None or value is False or value == "":
        return False
    if not isinstance(value, str):
        return bool(value)
    value = value.strip()
    if value.startswith("#"):
        return False
    value = value.strip("\"'")
    if not value or value.lower() in {"none", "null", "false", "changeme", "change_me", "..."}:
        return False
    return not (
        value.startswith(("${", "{{", "<", "$ENV", "$env:", "process.env.", "os.environ"))
        or value.lower().startswith(("your_", "your-", "replace_", "replace-", "example_"))
    )


def _secret_key(key: str) -> bool:
    return bool(SECRET_KEY_RE.fullmatch(re.sub(r"[^a-z0-9]", "", key.lower())))


def has_private_config(name: str, data: bytes) -> bool:
    """Recognize populated secret fields; never return their values in diagnostics."""
    base = name.casefold().rsplit("/", 1)[-1]
    config_like = (
        Path(base).suffix in {".json", ".jsonc", ".toml", ".ini", ".cfg", ".yaml", ".yml"}
        or base.startswith(".env") or is_template(base)
    )
    if not config_like:
        return False
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return True
    if "-----BEGIN " in content and "PRIVATE KEY-----" in content:
        return True
    if base.endswith(".json"):
        try:
            parsed = json.loads(content)
        except (ValueError, RecursionError):
            parsed = None
        def contains_secret(item: object) -> bool:
            if isinstance(item, dict):
                return any((_secret_key(str(key)) and _nonempty_secret(value))
                           or contains_secret(value) for key, value in item.items())
            if isinstance(item, list):
                return any(contains_secret(value) for value in item)
            return False
        try:
            if contains_secret(parsed):
                return True
        except RecursionError:
            return True
    return any(_secret_key(key) and _nonempty_secret(value)
               for key, value in ASSIGNMENT_RE.findall(content))


def _default_output(source: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return source.with_name(f"{source.stem}-recovery-source-{stamp}.zip")


def prepare_bundle(input_path: str | Path, output_path: str | Path | None = None,
                   *, limits: Limits | None = None) -> dict:
    limits = limits or Limits()
    source = Path(input_path).expanduser().resolve()
    output = Path(output_path).expanduser().absolute() if output_path else _default_output(source)
    if not source.is_file():
        raise BundleError("Không tìm thấy ZIP đầu vào. Hãy chọn đúng file ZIP gốc.")
    if source == output.resolve():
        raise BundleError("File đầu ra phải khác file ZIP gốc. ZIP gốc luôn được giữ nguyên.")
    if output.exists() or output.is_symlink():
        raise BundleError("File đầu ra đã tồn tại. Hãy chọn tên mới; công cụ không ghi đè file.")
    if not output.parent.is_dir():
        raise BundleError("Thư mục đầu ra không tồn tại.")

    created_output = False
    try:
        with zipfile.ZipFile(source, "r") as archive:
            entries = archive.infolist()
            if len(entries) > limits.max_entries:
                raise BundleError("ZIP có quá nhiều mục. Hãy tạo ZIP riêng cho từng phiên bản.")
            if sum(entry.file_size for entry in entries) > limits.max_declared_bytes:
                raise BundleError("ZIP khai báo quá nhiều dữ liệu giải nén. Hãy bỏ thư viện cài sẵn rồi thử lại.")
            names: dict[str, str] = {}
            file_keys: set[str] = set()
            validated = []
            for info in entries:
                name, is_dir = safe_name(info)
                key = unicodedata.normalize("NFC", name).casefold()
                if key == MANIFEST_NAME.casefold():
                    raise BundleError("ZIP đã có RECOVERY-MANIFEST.json. Hãy chọn ZIP gốc, chưa qua công cụ này.")
                if key in names:
                    raise BundleError(f"ZIP có đường dẫn trùng nhau: {name!r}. Hãy nén lại từ các thư mục gốc.")
                names[key] = name
                if not is_dir:
                    file_keys.add(key)
                mode = (info.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                category = classify(name)
                if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    if category == "dependencies-or-generated":
                        category = "ignored-symbolic-link"
                    else:
                        raise BundleError(f"ZIP chứa liên kết hoặc file đặc biệt: {name!r}. Hãy bỏ liên kết đó rồi nén lại.")
                if bool(kind == stat.S_IFDIR) != is_dir and kind != 0:
                    raise BundleError(f"Kiểu đường dẫn ZIP không nhất quán: {name!r}")
                validated.append((info, name, is_dir, category))
            for key in names:
                components = key.split("/")
                if any("/".join(components[:index]) in file_keys for index in range(1, len(components))):
                    raise BundleError("ZIP có file trùng với tên thư mục cha. Hãy nén lại từ thư mục gốc.")
            nested = [name for _, name, is_dir, category in validated
                      if not is_dir and category == "nested-archive"]
            if nested:
                examples = "\n".join("- " + (name if len(name) <= 160 else name[:157] + "...")
                                     for name in nested[:5])
                remaining = f"\n... và {len(nested) - 5} tệp khác." if len(nested) > 5 else ""
                raise BundleError(
                    f"Phát hiện {len(nested)} tệp nén con chưa được mở:\n{examples}{remaining}\n"
                    "Không tạo ZIP đầu ra vì có thể thiếu mã nguồn của các phiên bản. "
                    "Hãy giải nén từng tệp nén con vào thư mục riêng, giữ tên phiên bản khác nhau, "
                    "rồi nén chung các thư mục và chạy lại. ZIP gốc giữ nguyên."
                )

            included = []
            private = []
            ignored: Counter[str] = Counter()
            roots = set()
            total_source = 0
            with output.open("xb") as output_file:
                created_output = True
                with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as result:
                    for info, name, is_dir, category in validated:
                        if is_dir:
                            continue
                        if category.startswith("private-"):
                            private.append({"path": name, "size": info.file_size, "reason": category})
                        elif category != "source":
                            ignored[category] += 1
                        else:
                            if info.flag_bits & 1:
                                raise BundleError(f"File nguồn bị mã hóa: {name!r}. Hãy tạo ZIP không đặt mật khẩu.")
                            if info.file_size > limits.max_source_file_bytes:
                                raise BundleError(f"File nguồn quá lớn: {name!r}. Hãy kiểm tra file sinh tự động hoặc gửi riêng từng phiên bản.")
                            if (info.file_size > 1024 * 1024 and
                                    info.file_size > max(1, info.compress_size) * limits.max_expansion_ratio):
                                raise BundleError(f"Tỷ lệ nén bất thường: {name!r}. Hãy kiểm tra rồi tạo lại ZIP nguồn.")
                            total_source += info.file_size
                            if total_source > limits.max_source_bytes:
                                raise BundleError("Tổng mã nguồn quá lớn. Hãy chuẩn bị ZIP riêng cho từng phiên bản.")
                            # Only source candidates are decompressed. Runtime databases are never opened.
                            with archive.open(info) as member:
                                data = member.read(limits.max_source_file_bytes + 1)
                            if len(data) != info.file_size or len(data) > limits.max_source_file_bytes:
                                raise BundleError(f"Kích thước file nguồn không hợp lệ: {name!r}")
                            if has_private_config(name, data):
                                private.append({"path": name, "size": info.file_size, "reason": "private-config-fields"})
                            else:
                                safe_info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                                safe_info.compress_type = zipfile.ZIP_DEFLATED
                                safe_info.external_attr = (stat.S_IFREG | 0o644) << 16
                                result.writestr(safe_info, data)
                                included.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
                                roots.add(name.split("/", 1)[0] if "/" in name else ".")
                        if len(private) > limits.max_private_entries:
                            raise BundleError("Quá nhiều file dữ liệu riêng. Hãy chuẩn bị ZIP riêng cho từng phiên bản.")
                        if output_file.tell() >= limits.max_output_bytes:
                            raise BundleError("ZIP nguồn vượt giới hạn 31 MiB. Hãy chuẩn bị ZIP riêng cho từng phiên bản; ZIP gốc vẫn nguyên vẹn.")
                    if not included:
                        raise BundleError("Không tìm thấy mã nguồn. Nếu ZIP chứa các ZIP con, hãy giải nén chúng vào các thư mục riêng rồi nén chung các thư mục đó.")
                    manifest = {
                        "schema_version": 1,
                        "purpose": "source-review-only; private data remains in the original local ZIP",
                        "input_archive_name": source.name,
                        "preserved_top_level_names": sorted(roots),
                        "source_files": included,
                        "private_recovery_inventory": private,
                        "ignored_file_counts": dict(sorted(ignored.items())),
                        "notice": "Inventory contains paths and declared sizes only for private files; no private contents or password hashes are included. This is not a runnable full application backup.",
                    }
                    result.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
            if output.stat().st_size >= limits.max_output_bytes:
                raise BundleError("ZIP nguồn vượt giới hạn 31 MiB. Hãy chuẩn bị ZIP riêng cho từng phiên bản; ZIP gốc vẫn nguyên vẹn.")
            return {"output": str(output), "size": output.stat().st_size,
                    "source_count": len(included), "private_count": len(private),
                    "top_level_names": sorted(roots)}
    except Exception as error:
        if created_output:
            output.unlink(missing_ok=True)
        if isinstance(error, BundleError):
            raise
        if isinstance(error, (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, NotImplementedError, EOFError, ValueError)):
            raise BundleError("Không đọc/ghi được ZIP. Hãy kiểm tra ZIP có mở được, không đặt mật khẩu, và còn đủ dung lượng ổ đĩa.") from error
        raise


def choose_input() -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
        window = tk.Tk()
        window.withdraw()
        try:
            window.attributes("-topmost", True)
            return filedialog.askopenfilename(
                parent=window, title="Chọn ZIP gốc chứa các phiên bản Pasion",
                filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
            )
        finally:
            window.destroy()
    except Exception as error:
        raise BundleError('Không mở được cửa sổ chọn file. Chạy: py -3.12 scripts\\prepare_recovery_bundle.py --input "C:\\duong-dan\\ban-goc.zip"') from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tạo ZIP mã nguồn nhỏ để đối chiếu các phiên bản; giữ nguyên ZIP gốc.")
    parser.add_argument("--input", help="ZIP gốc chứa một hoặc nhiều thư mục phiên bản")
    parser.add_argument("--output", help="Tên ZIP mới, chưa tồn tại; mặc định tạo cạnh ZIP gốc")
    args = parser.parse_args(argv)
    try:
        input_path = args.input or choose_input()
        if not input_path:
            print("Đã hủy chọn file. Không có file nào bị thay đổi.")
            return 0
        summary = prepare_bundle(input_path, args.output)
        print(f"Đã tạo: {summary['output']}")
        print(f"Kích thước: {summary['size'] / 1024**2:.2f} MiB; {summary['source_count']} file nguồn.")
        print(f"{summary['private_count']} file riêng chỉ được ghi nhận đường dẫn/kích thước trong manifest.")
        print("Hãy gửi ZIP mới này để đối chiếu. Giữ ZIP gốc trên máy để phục hồi dữ liệu sau đó.")
        return 0
    except BundleError as error:
        print(f"Lỗi: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
