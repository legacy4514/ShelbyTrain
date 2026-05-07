from pathlib import Path
import json
import tarfile
import csv
import tempfile
from typing import Any, Dict, Optional

from PIL import Image
import torch
from torch.utils.data import Dataset
from torchvision import transforms

from .cache import ShelbyCache


class ShelbyImageDataset(Dataset):
    """PyTorch Dataset that reads image shards from local files or Shelby.

    For the MVP, each shard is downloaded as a whole TAR file, extracted into
    a temporary directory, indexed, and served to PyTorch.
    """

    def __init__(
        self,
        manifest_path: str,
        client: Optional[Any] = None,
        cache_dir: str = ".shelby-cache",
        transform: Optional[Any] = None,
        max_shards: Optional[int] = None,
    ):
        self.manifest = json.loads(Path(manifest_path).read_text())
        self.client = client
        self.cache = ShelbyCache(cache_dir)
        self.transform = transform or transforms.Compose(
            [
                transforms.Grayscale(),
                transforms.ToTensor(),
            ]
        )

        self.shards = self.manifest["shards"]
        if max_shards:
            self.shards = self.shards[:max_shards]

        self.samples: list[Dict[str, Any]] = []
        self.extracted_dirs: dict[int, Path] = {}
        self.shards_by_index = {shard["index"]: shard for shard in self.shards}

        self._index_shards()

    def _ensure_shard_cached(self, shard: Dict[str, Any]) -> Path:
        blob_name = shard["blob_name"]
        cached_path = self.cache.get(blob_name)

        if cached_path.exists():
            return cached_path

        local_path = Path(shard.get("local_path", ""))
        if self.client is None:
            if local_path.exists():
                return local_path
            raise RuntimeError("No Shelby client provided and local shard not found")

        self.client.download_blob(blob_name, str(cached_path))
        return cached_path

    def _extract_shard(self, shard: Dict[str, Any]) -> Path:
        shard_index = shard["index"]
        if shard_index in self.extracted_dirs:
            return self.extracted_dirs[shard_index]

        shard_path = self._ensure_shard_cached(shard)
        extract_dir = Path(tempfile.mkdtemp(prefix=f"shelbytrain-{shard_index}-"))

        with tarfile.open(shard_path, "r") as tar:
            tar.extractall(extract_dir)

        self.extracted_dirs[shard_index] = extract_dir
        return extract_dir

    def _index_shards(self) -> None:
        for shard in self.shards:
            extract_dir = self._extract_shard(shard)
            labels_path = extract_dir / "labels.csv"

            with labels_path.open("r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.samples.append(
                        {
                            "shard_index": shard["index"],
                            "filename": row["filename"],
                            "label": int(row["label"]),
                        }
                    )

        print(f"Indexed {len(self.samples)} samples")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        sample = self.samples[idx]
        shard = self.shards_by_index[sample["shard_index"]]
        extract_dir = self._extract_shard(shard)

        img_path = extract_dir / "images" / sample["filename"]
        img = Image.open(img_path).convert("RGB")

        if self.transform:
            img = self.transform(img)

        label = torch.tensor(sample["label"], dtype=torch.long)
        return img, label
