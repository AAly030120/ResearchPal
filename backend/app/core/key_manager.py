"""
Runtime API Key Manager
Stores keys in an ENCRYPTED JSON file so they can be updated at runtime
without restart. Encryption uses a Fernet key derived from SECRET_KEY
(production) or a built-in dev fallback (dev/Demo mode) — never plaintext.

Priority: File keys > Environment variables
"""
import os
import json
import base64
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

KEY_FILE = Path(__file__).parent.parent.parent / ".api_keys.json"

ENV_KEYS = ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY", "QWEN_API_KEY")

# Built-in fallback secret for dev/Demo mode ONLY. It is a source constant, so
# it is NOT a real security boundary — its only purpose is to avoid writing
# API keys as plaintext on disk during local development. In production a
# strong, unique SECRET_KEY is mandatory, at which point this fallback is
# dropped from the key ring entirely.
_DEV_FALLBACK_SECRET = "researchpal-dev-insecure-fallback-REPLACE-ME-9f3c"


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte url-safe Fernet key from an arbitrary secret string."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"researchpal-key-manager-v1",
        info=b"api-keys",
    )
    return base64.urlsafe_b64encode(hkdf.derive(secret.encode("utf-8")))


def _fernet_keys() -> list:
    """Return the ordered list of Fernet keys for the current settings.

    - Production (SECRET_KEY set): only the derived prod key is used.
    - Dev/Demo (no SECRET_KEY): the dev fallback key is used instead.
    - Both present: prod key first (used for encryption), both can decrypt.
    """
    keys = []
    if settings.SECRET_KEY:
        keys.append(_derive_fernet_key(settings.SECRET_KEY))
    if not settings.SECRET_KEY or settings.DEBUG:
        keys.append(_derive_fernet_key(_DEV_FALLBACK_SECRET))
    return keys


def _encrypt(plain: bytes) -> str:
    """Encrypt with the strongest available key (first in the list)."""
    return Fernet(_fernet_keys()[0]).encrypt(plain).decode("utf-8")


def _decrypt(token: str) -> bytes:
    """Decrypt by trying each available key; raise if none succeed."""
    last_err = None
    for k in _fernet_keys():
        try:
            return Fernet(k).decrypt(token.encode("utf-8"))
        except InvalidToken as e:
            last_err = e
    raise last_err or InvalidToken()


class KeyManager:
    """Thread-safe API key manager with encrypted file persistence."""

    def __init__(self):
        self._lock = threading.Lock()
        self._keys: dict[str, str] = {}
        self._load()

    def _env_keys(self) -> dict[str, str]:
        out = {}
        for k in ENV_KEYS:
            v = getattr(settings, k, None) or ""
            if v:
                out[k] = v
        return out

    def _load(self):
        """Load keys: env vars + encrypted file (legacy plaintext auto-migrated)."""
        keys = self._env_keys()
        migrated = False
        if KEY_FILE.exists():
            try:
                data = json.loads(KEY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = None

            if isinstance(data, dict) and data.get("enc"):
                # Encrypted format: decrypt and merge.
                try:
                    plain = _decrypt(data["enc"]).decode("utf-8")
                    file_keys = json.loads(plain)
                    if isinstance(file_keys, dict):
                        keys.update(file_keys)
                except (InvalidToken, json.JSONDecodeError):
                    # Corrupted or key-mismatched file: drop it, rebuild from env.
                    try:
                        KEY_FILE.unlink()
                    except OSError:
                        pass
            elif isinstance(data, dict):
                # Legacy plaintext format → migrate to encrypted on next save.
                keys.update(data)
                migrated = True

        with self._lock:
            self._keys = keys
        if migrated:
            self._save()

    def _save(self):
        """Encrypt and persist current keys to file."""
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        plain = json.dumps(self._keys, ensure_ascii=False, indent=2)
        token = _encrypt(plain.encode("utf-8"))
        KEY_FILE.write_text(json.dumps({"v": 1, "enc": token}), encoding="utf-8")

    def get(self, key_env: str) -> str:
        """Get an API key by its environment variable name."""
        with self._lock:
            return self._keys.get(key_env, "")

    def set(self, key_env: str, value: str):
        """Set an API key and persist to file (encrypted)."""
        with self._lock:
            if value:
                self._keys[key_env] = value
            else:
                self._keys.pop(key_env, None)
            self._save()

    def has(self, key_env: str) -> bool:
        """Check if a key is configured and non-empty."""
        return bool(self.get(key_env))

    def get_all_status(self) -> dict:
        """Get masked status of all known keys."""
        result = {}
        with self._lock:
            for key_env in ENV_KEYS:
                val = self._keys.get(key_env, "")
                result[key_env] = {
                    "configured": bool(val),
                    "masked": val[:6] + "..." + val[-4:] if len(val) > 10 else (val[:3] + "***" if val else ""),
                }
        return result


key_manager = KeyManager()
