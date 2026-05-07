from pathlib import Path
import hashlib


class ShelbyCache:
    """Simple local shard cache."""

    def __init__(self, cache_dir: str = ".shelby-cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def key_for_blob(self, blob_name: str) -> str:
        digest = hashlib.sha256(blob_name.encode()).hexdigest()
        return digest + ".tar"

    def path_for_blob(self, blob_name: str) -> Path:
        return self.cache_dir / self.key_for_blob(blob_name)

    def has(self, blob_name: str) -> bool:
        return self.path_for_blob(blob_name).exists()

    def get(self, blob_name: str) -> Path:
        return self.path_for_blob(blob_name)
