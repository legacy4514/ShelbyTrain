"""ShelbyTrain: decentralized AI dataset pipeline built on Shelby Protocol."""

__version__ = "0.2.0"

from .dataset import (
    ShelbyBaseDataset,
    ShelbyImageDataset,
    ShelbyTextDataset,
    ShelbyParquetDataset,
    ShelbyAudioDataset,
    load_dataset,
)
from .client import ShelbyHTTPClient
from .cache import ShelbyCache
from .manifest import load_manifest, save_manifest
from .sharder import (
    create_image_shards,
    create_text_shards,
    create_parquet_shards,
    create_audio_shards,
)

__all__ = [
    "ShelbyBaseDataset",
    "ShelbyImageDataset",
    "ShelbyTextDataset",
    "ShelbyParquetDataset",
    "ShelbyAudioDataset",
    "load_dataset",
    "ShelbyHTTPClient",
    "ShelbyCache",
    "load_manifest",
    "save_manifest",
    "create_image_shards",
    "create_text_shards",
    "create_parquet_shards",
    "create_audio_shards",
]
