import re
import zipfile
from collections.abc import Mapping
from io import BytesIO
from pathlib import PurePosixPath


class BundleFormatError(ValueError):
    """Raised when a project bundle violates its file format contract."""


MAX_TOTAL_UNCOMPRESSED = 50 * 1024 * 1024
MAX_FILE_UNCOMPRESSED = 5 * 1024 * 1024
MAX_FILES = 5000
_DRIVE = re.compile(r"^[A-Za-z]:")


def _safe_path(name: str) -> str:
    if (
        not name
        or "\\" in name
        or ":" in name
        or any(ord(char) < 32 for char in name)
        or name.startswith("/")
        or _DRIVE.match(name)
    ):
        raise BundleFormatError(f"unsafe archive path: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise BundleFormatError(f"unsafe archive path: {name!r}")
    normalized = str(PurePosixPath(*parts))
    if normalized != name:
        raise BundleFormatError(f"non-canonical archive path: {name!r}")
    return normalized


def build_zip(files: Mapping[str, str | bytes]) -> bytes:
    if len(files) > MAX_FILES:
        raise BundleFormatError("archive contains too many files")
    checked: dict[str, bytes] = {}
    total = 0
    for name, value in files.items():
        path = _safe_path(name)
        if path in checked:
            raise BundleFormatError(f"duplicate archive path: {path!r}")
        data = value.encode("utf-8") if isinstance(value, str) else value
        if not isinstance(data, bytes):
            raise TypeError("archive values must be str or bytes")
        if len(data) > MAX_FILE_UNCOMPRESSED:
            raise BundleFormatError("archive file exceeds uncompressed size limit")
        total += len(data)
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise BundleFormatError("archive exceeds uncompressed size limit")
        checked[path] = data
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(checked):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            archive.writestr(info, checked[path])
    return output.getvalue()


def read_zip(data: bytes) -> dict[str, bytes]:
    if not zipfile.is_zipfile(BytesIO(data)):
        raise BundleFormatError("data is not a ZIP archive")
    result: dict[str, bytes] = {}
    seen_paths: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            file_infos = [info for info in infos if not info.is_dir()]
            if len(file_infos) > MAX_FILES:
                raise BundleFormatError("archive contains too many files")
            for info in infos:
                if info.is_dir():
                    if not info.filename.endswith("/"):
                        raise BundleFormatError("invalid archive directory path")
                    path = _safe_path(info.filename[:-1])
                    if path in seen_paths:
                        raise BundleFormatError(f"duplicate archive path: {path!r}")
                    seen_paths.add(path)
                    continue
                path = _safe_path(info.filename)
                if info.flag_bits & 0x1:
                    raise BundleFormatError(
                        "encrypted archive entries are not supported"
                    )
                if path in seen_paths:
                    raise BundleFormatError(f"duplicate archive path: {path!r}")
                seen_paths.add(path)
                file_data = archive.read(info)
                if len(file_data) > MAX_FILE_UNCOMPRESSED:
                    raise BundleFormatError(
                        "archive file exceeds uncompressed size limit"
                    )
                total += len(file_data)
                if total > MAX_TOTAL_UNCOMPRESSED:
                    raise BundleFormatError("archive exceeds uncompressed size limit")
                result[path] = file_data
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise BundleFormatError("invalid ZIP archive") from exc
    return result
