from pathlib import Path

from cryptography.fernet import Fernet

import app.settings as settings_module
from app.settings import _ensure_encryption_key


def test_ensure_encryption_key_reads_key_file_and_ignores_env(monkeypatch, tmp_path: Path) -> None:
    known_key = Fernet.generate_key().decode()
    key_file = tmp_path / "data" / ".key"
    key_file.parent.mkdir(parents=True)
    key_file.write_text(known_key, encoding="utf-8")
    monkeypatch.setattr(settings_module, "ENCRYPTION_KEY_FILE_PATH", key_file)
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

    key = _ensure_encryption_key()

    assert key == known_key
