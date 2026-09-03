"""
Runtime API Key Manager
Stores keys in a JSON file so they can be updated at runtime without restart.
Priority: File keys > Environment variables
"""
import os
import json
import threading
from pathlib import Path
from app.core.config import settings

KEY_FILE = Path(__file__).parent.parent.parent / ".api_keys.json"


class KeyManager:
    """Thread-safe API key manager with file persistence."""

    def __init__(self):
        self._lock = threading.Lock()
        self._keys: dict[str, str] = {}
        self._load()

    def _load(self):
        """Load keys from file, fall back to env vars."""
        keys = {}
        # Start with env var values
        for key_env in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY", "QWEN_API_KEY"):
            env_val = getattr(settings, key_env, None) or ""
            if env_val:
                keys[key_env] = env_val

        # File overrides env (user explicitly set)
        if KEY_FILE.exists():
            try:
                with open(KEY_FILE, "r", encoding="utf-8") as f:
                    file_keys = json.load(f)
                if isinstance(file_keys, dict):
                    keys.update(file_keys)
            except (json.JSONDecodeError, OSError):
                pass

        with self._lock:
            self._keys = keys

    def _save(self):
        """Save current keys to file."""
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._keys, f, ensure_ascii=False, indent=2)

    def get(self, key_env: str) -> str:
        """Get an API key by its environment variable name."""
        with self._lock:
            return self._keys.get(key_env, "")

    def set(self, key_env: str, value: str):
        """Set an API key and persist to file."""
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
            for key_env in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY", "QWEN_API_KEY"):
                val = self._keys.get(key_env, "")
                result[key_env] = {
                    "configured": bool(val),
                    "masked": val[:6] + "..." + val[-4:] if len(val) > 10 else (val[:3] + "***" if val else ""),
                }
        return result


key_manager = KeyManager()
