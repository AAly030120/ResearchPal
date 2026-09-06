"""
KeyManager encryption-at-rest tests.

Verifies that API keys are never written as plaintext to .api_keys.json,
that they round-trip across instances (simulating a restart), that legacy
plaintext files are auto-migrated, and that corrupted files are safely
discarded rather than crashing the app.
"""
import json

import pytest

from app.core import key_manager as km_module
from app.core.key_manager import KeyManager


def _new_manager(tmp_path, monkeypatch):
    f = tmp_path / ".api_keys.json"
    monkeypatch.setattr(km_module, "KEY_FILE", f)
    return KeyManager(), f


def test_keys_encrypted_at_rest_not_plaintext(tmp_path, monkeypatch):
    m, f = _new_manager(tmp_path, monkeypatch)
    m.set("OPENAI_API_KEY", "sk-super-secret-value")
    raw = f.read_text(encoding="utf-8")
    # Plaintext must NEVER hit disk.
    assert "sk-super-secret-value" not in raw
    data = json.loads(raw)
    assert data.get("v") == 1
    assert isinstance(data.get("enc"), str) and len(data["enc"]) > 0


def test_roundtrip_across_instances(tmp_path, monkeypatch):
    m, f = _new_manager(tmp_path, monkeypatch)
    m.set("DEEPSEEK_API_KEY", "sk-deepseek-xyz")
    # New instance (simulates a restart) must decrypt and read it back.
    m2, _ = _new_manager(tmp_path, monkeypatch)
    assert m2.get("DEEPSEEK_API_KEY") == "sk-deepseek-xyz"


def test_legacy_plaintext_auto_migrated(tmp_path, monkeypatch):
    f = tmp_path / ".api_keys.json"
    # Old plaintext format.
    f.write_text(json.dumps({"OPENAI_API_KEY": "sk-legacy-plain"}), encoding="utf-8")
    m, f = _new_manager(tmp_path, monkeypatch)
    assert m.get("OPENAI_API_KEY") == "sk-legacy-plain"
    # After load, the file must be encrypted.
    raw = f.read_text(encoding="utf-8")
    assert "sk-legacy-plain" not in raw
    data = json.loads(raw)
    assert data.get("enc")


def test_corrupted_file_recovered_from_env(tmp_path, monkeypatch):
    f = tmp_path / ".api_keys.json"
    f.write_text(json.dumps({"v": 1, "enc": "not-a-valid-token"}), encoding="utf-8")
    m, f = _new_manager(tmp_path, monkeypatch)
    # Decryption failure must not crash; key is cleared, bad file dropped.
    assert m.get("OPENAI_API_KEY") == ""
    assert not f.exists()


def test_set_empty_removes_key(tmp_path, monkeypatch):
    m, f = _new_manager(tmp_path, monkeypatch)
    m.set("GLM_API_KEY", "sk-glm-123")
    assert m.has("GLM_API_KEY")
    m.set("GLM_API_KEY", "")
    assert not m.has("GLM_API_KEY")
    # Removed key must not linger in the encrypted blob.
    raw = f.read_text(encoding="utf-8")
    assert "sk-glm-123" not in raw
