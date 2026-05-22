from pathlib import Path
import hashlib
import json
import time
from typing import Any, Dict


class ShelbyCache:
    """Simple local shard cache."""

    def __init__(self, cache_dir: str = ".shelby-cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / "index.json"

    def key_for_blob(self, blob_name: str) -> str:
        digest = hashlib.sha256(blob_name.encode()).hexdigest()
        return digest + ".tar"

    def path_for_blob(self, blob_name: str) -> Path:
        return self.cache_dir / self.key_for_blob(blob_name)

    def has(self, blob_name: str) -> bool:
        return self.path_for_blob(blob_name).exists()

    def get(self, blob_name: str) -> Path:
        return self.path_for_blob(blob_name)

    def load_index(self) -> Dict[str, Any]:
        if not self.index_path.exists():
            return {"version": "0.1.0", "shards": {}}

        try:
            data = json.loads(self.index_path.read_text())
            if isinstance(data, dict) and isinstance(data.get("shards"), dict):
                return data
        except Exception:
            pass

        return {"version": "0.1.0", "shards": {}}

    def save_index(self, index: Dict[str, Any]) -> None:
        temp = self.index_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(index, indent=2, sort_keys=True))
        temp.replace(self.index_path)

    def update_entry(self, blob_name: str, updates: Dict[str, Any]) -> None:
        index = self.load_index()
        key = self.key_for_blob(blob_name)
        entry = index["shards"].get(key, {})
        entry.update({
            "key": key,
            "blob_name": blob_name,
            "cache_path": str(self.path_for_blob(blob_name)),
            "last_accessed": time.time(),
            **updates,
        })
        index["shards"][key] = entry
        self.save_index(index)

    def increment(self, blob_name: str, field: str, amount: float = 1) -> None:
        index = self.load_index()
        key = self.key_for_blob(blob_name)
        entry = index["shards"].get(key, {
            "key": key,
            "blob_name": blob_name,
            "cache_path": str(self.path_for_blob(blob_name)),
        })
        entry[field] = round(float(entry.get(field, 0)) + amount, 6)
        entry["last_accessed"] = time.time()
        index["shards"][key] = entry
        self.save_index(index)

    def record_error(self, blob_name: str, error: str) -> None:
        index = self.load_index()
        key = self.key_for_blob(blob_name)
        entry = index["shards"].get(key, {
            "key": key,
            "blob_name": blob_name,
            "cache_path": str(self.path_for_blob(blob_name)),
        })
        errors = entry.get("errors", [])
        if not isinstance(errors, list):
            errors = []
        errors.append({"time": time.time(), "error": error})
        entry["errors"] = errors[-5:]
        entry["last_accessed"] = time.time()
        index["shards"][key] = entry
        self.save_index(index)
