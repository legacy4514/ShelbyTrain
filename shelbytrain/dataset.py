from pathlib import Path
import hashlib
import json
import tarfile
import csv
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import torch
from torch.utils.data import Dataset

from .cache import ShelbyCache


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ── Base Dataset ─────────────────────────────────────────────────────────────

class ShelbyBaseDataset(Dataset, ABC):
    """
    Base class for all ShelbyTrain datasets.
    Handles all Shelby-specific logic: downloading, caching, verification.
    Subclasses only implement format-specific indexing and item loading.
    """

    def __init__(
        self,
        manifest_path: str,
        client: Optional[Any] = None,
        cache_dir: str = ".shelby-cache",
        max_shards: Optional[int] = None,
    ):
        self.manifest = json.loads(Path(manifest_path).read_text())
        self.client = client
        self.cache = ShelbyCache(cache_dir)

        self.shards = self.manifest["shards"]
        if max_shards:
            self.shards = self.shards[:max_shards]

        self.shards_by_index = {shard["index"]: shard for shard in self.shards}
        self.samples: List[Dict[str, Any]] = []
        self.extracted_dirs: Dict[int, Path] = {}

        self.metrics: Dict[str, Any] = {
            "cache_hits": 0,
            "cache_misses": 0,
            "local_reads": 0,
            "downloads": 0,
            "download_sec": 0.0,
            "extract_sec": 0.0,
            "index_sec": 0.0,
            "bytes_downloaded": 0,
            "shards_indexed": 0,
            "errors": [],
        }

        self._index_shards()

    # ── Shelby internals ──────────────────────────────────────────────────────

    def _verify_shard(self, shard: Dict[str, Any], path: Path) -> None:
        expected_size = shard.get("size_bytes")
        if expected_size and path.stat().st_size != int(expected_size):
            raise RuntimeError(
                f"Size mismatch for {path.name}: "
                f"expected {expected_size}, got {path.stat().st_size}"
            )
        expected_hash = shard.get("sha256")
        if expected_hash:
            actual = sha256_file(path)
            if actual != expected_hash:
                raise RuntimeError(
                    f"Hash mismatch for {path.name}: "
                    f"expected {expected_hash}, got {actual}"
                )

    def _ensure_shard_cached(self, shard: Dict[str, Any]) -> Path:
        blob_name = shard["blob_name"]
        cached_path = self.cache.get(blob_name)

        if cached_path.exists():
            try:
                self._verify_shard(shard, cached_path)
                self.metrics["cache_hits"] += 1
                return cached_path
            except Exception:
                cached_path.unlink(missing_ok=True)

        local_path = Path(shard.get("local_path", ""))
        if self.client is None:
            if local_path.exists():
                self.metrics["local_reads"] += 1
                return local_path
            raise RuntimeError(
                "No Shelby client and local shard not found. "
                "Provide a ShelbyHTTPClient to download from Shelby."
            )

        self.metrics["cache_misses"] += 1
        t = time.perf_counter()
        print(f"📥 Downloading {blob_name} from Shelby...")
        self.client.download_blob(blob_name, str(cached_path))
        dl_sec = time.perf_counter() - t
        self._verify_shard(shard, cached_path)
        self.metrics["downloads"] += 1
        self.metrics["download_sec"] = round(self.metrics["download_sec"] + dl_sec, 4)
        self.metrics["bytes_downloaded"] += cached_path.stat().st_size
        return cached_path

    def _get_shard_dir(self, shard: Dict[str, Any]) -> Path:
        idx = shard["index"]
        if idx in self.extracted_dirs:
            return self.extracted_dirs[idx]

        shard_path = self._ensure_shard_cached(shard)
        extract_dir = Path(tempfile.mkdtemp(prefix=f"shelbytrain-{idx}-"))

        t = time.perf_counter()
        self._extract_to_dir(shard_path, extract_dir)
        self.metrics["extract_sec"] = round(
            self.metrics["extract_sec"] + time.perf_counter() - t, 4
        )
        self.metrics["shards_indexed"] += 1
        self.extracted_dirs[idx] = extract_dir
        return extract_dir

    def _extract_to_dir(self, shard_path: Path, extract_dir: Path) -> None:
        """Default extraction — works for TAR files. Override for other formats."""
        with tarfile.open(shard_path, "r") as tar:
            tar.extractall(extract_dir)

    def _index_shards(self) -> None:
        t = time.perf_counter()
        for shard in self.shards:
            shard_dir = self._get_shard_dir(shard)
            self._index_shard(shard, shard_dir)
        self.metrics["index_sec"] = round(time.perf_counter() - t, 4)
        print(f"Indexed {len(self.samples)} samples")

    # ── Abstract methods — subclasses implement these ─────────────────────────

    @abstractmethod
    def _index_shard(self, shard: Dict[str, Any], shard_dir: Path) -> None:
        """Read all sample metadata from a shard directory into self.samples."""
        ...

    @abstractmethod
    def __getitem__(self, idx: int):
        """Return one (input, label) pair."""
        ...

    def __len__(self) -> int:
        return len(self.samples)


# ── Image Dataset (TAR + CSV labels) ─────────────────────────────────────────

class ShelbyImageDataset(ShelbyBaseDataset):
    """
    Image dataset stored as TAR shards.

    Expected shard layout:
        labels.csv      — columns: filename, label
        images/
            000001.png
            000002.png
    """

    def __init__(self, *args, transform=None, **kwargs):
        from torchvision import transforms
        self.transform = transform or transforms.Compose([
            transforms.Grayscale(),
            transforms.ToTensor(),
        ])
        super().__init__(*args, **kwargs)

    def _index_shard(self, shard: Dict[str, Any], shard_dir: Path) -> None:
        labels_path = shard_dir / "labels.csv"
        with labels_path.open("r", newline="") as f:
            for row in csv.DictReader(f):
                self.samples.append({
                    "shard_index": shard["index"],
                    "filename": row["filename"],
                    "label": int(row["label"]),
                })

    def __getitem__(self, idx: int):
        from PIL import Image
        sample = self.samples[idx]
        shard = self.shards_by_index[sample["shard_index"]]
        shard_dir = self._get_shard_dir(shard)
        img = Image.open(shard_dir / "images" / sample["filename"]).convert("RGB")
        if self.transform:
            img = self.transform(img)
        label = torch.tensor(sample["label"], dtype=torch.long)
        return img, label


# ── Text Dataset (JSONL) ──────────────────────────────────────────────────────

class ShelbyTextDataset(ShelbyBaseDataset):
    """
    Text dataset stored as JSONL shards.

    Expected shard layout (TAR containing):
        data.jsonl      — one JSON object per line
                          must have a "text" field
                          optional "label" field

    Example JSONL line:
        {"text": "The movie was great", "label": 1}
    """

    def __init__(self, *args, text_field: str = "text",
                 label_field: str = "label", max_length: int = 512, **kwargs):
        self.text_field = text_field
        self.label_field = label_field
        self.max_length = max_length
        super().__init__(*args, **kwargs)

    def _index_shard(self, shard: Dict[str, Any], shard_dir: Path) -> None:
        jsonl_path = shard_dir / "data.jsonl"
        if not jsonl_path.exists():
            # Also try .json extension
            jsonl_path = shard_dir / "data.json"
        with jsonl_path.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                self.samples.append({
                    "shard_index": shard["index"],
                    "text": obj[self.text_field],
                    "label": obj.get(self.label_field, -1),
                })

    def __getitem__(self, idx: int):
        sample = self.samples[idx]
        text = sample["text"][:self.max_length]
        label = torch.tensor(sample["label"], dtype=torch.long)
        return text, label

    def collate_fn(self, batch):
        """Use this as DataLoader collate_fn for text batches."""
        texts, labels = zip(*batch)
        return list(texts), torch.stack(labels)


# ── Parquet Dataset ───────────────────────────────────────────────────────────

class ShelbyParquetDataset(ShelbyBaseDataset):
    """
    Tabular or embedding dataset stored as Parquet shards.

    Expected shard layout (TAR containing):
        data.parquet    — any Parquet file
                          specify feature_cols and label_col at init

    Good for:
        - Tabular ML datasets
        - Pre-computed embeddings
        - Feature vectors
    """

    def __init__(self, *args, feature_cols: Optional[List[str]] = None,
                 label_col: str = "label", **kwargs):
        self.feature_cols = feature_cols
        self.label_col = label_col
        super().__init__(*args, **kwargs)

    def _index_shard(self, shard: Dict[str, Any], shard_dir: Path) -> None:
        import pandas as pd
        parquet_path = shard_dir / "data.parquet"
        df = pd.read_parquet(parquet_path)

        cols = self.feature_cols or [c for c in df.columns if c != self.label_col]
        for _, row in df.iterrows():
            self.samples.append({
                "shard_index": shard["index"],
                "features": row[cols].values.tolist(),
                "label": row.get(self.label_col, -1),
            })

    def __getitem__(self, idx: int):
        import numpy as np
        sample = self.samples[idx]
        features = torch.tensor(
            np.array(sample["features"], dtype=np.float32),
            dtype=torch.float32,
        )
        label = torch.tensor(sample["label"], dtype=torch.long)
        return features, label


# ── Audio Dataset ─────────────────────────────────────────────────────────────

class ShelbyAudioDataset(ShelbyBaseDataset):
    """
    Audio dataset stored as TAR shards.

    Expected shard layout:
        labels.csv      — columns: filename, label
        audio/
            clip_001.wav
            clip_002.wav

    Good for:
        - Speech classification
        - Sound event detection
        - Music genre classification
    """

    def __init__(self, *args, sample_rate: int = 16000,
                 max_duration_sec: float = 5.0, **kwargs):
        self.sample_rate = sample_rate
        self.max_samples = int(sample_rate * max_duration_sec)
        super().__init__(*args, **kwargs)

    def _index_shard(self, shard: Dict[str, Any], shard_dir: Path) -> None:
        labels_path = shard_dir / "labels.csv"
        with labels_path.open("r", newline="") as f:
            for row in csv.DictReader(f):
                self.samples.append({
                    "shard_index": shard["index"],
                    "filename": row["filename"],
                    "label": int(row["label"]),
                })

    def __getitem__(self, idx: int):
        import soundfile as sf
        import numpy as np
        sample = self.samples[idx]
        shard = self.shards_by_index[sample["shard_index"]]
        shard_dir = self._get_shard_dir(shard)
        audio_path = shard_dir / "audio" / sample["filename"]
        waveform, sr = sf.read(str(audio_path), dtype="float32")
        # Resample if needed (simple truncate/pad for MVP)
        if len(waveform) > self.max_samples:
            waveform = waveform[:self.max_samples]
        else:
            waveform = np.pad(waveform, (0, self.max_samples - len(waveform)))
        tensor = torch.tensor(waveform, dtype=torch.float32)
        label = torch.tensor(sample["label"], dtype=torch.long)
        return tensor, label


# ── Factory function ──────────────────────────────────────────────────────────

def load_dataset(manifest_path: str, **kwargs) -> ShelbyBaseDataset:
    """
    Auto-detect dataset format from manifest and return the right dataset class.

    Usage:
        dataset = load_dataset("manifest.json", client=client)
    """
    manifest = json.loads(Path(manifest_path).read_text())
    fmt = manifest.get("format", "image-tar")

    format_map = {
        "image-tar":   ShelbyImageDataset,
        "text-jsonl":  ShelbyTextDataset,
        "parquet":     ShelbyParquetDataset,
        "audio-tar":   ShelbyAudioDataset,
    }

    cls = format_map.get(fmt)
    if cls is None:
        raise ValueError(
            f"Unknown dataset format: '{fmt}'. "
            f"Supported: {list(format_map.keys())}"
        )

    return cls(manifest_path, **kwargs)
