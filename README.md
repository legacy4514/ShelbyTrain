
# ShelbyTrain

Decentralized AI dataset pipeline built on [Shelby Protocol](https://shelby.xyz).

Upload datasets once to Shelby decentralized storage. Stream them into PyTorch from anywhere. Cache locally for instant repeated access.

## Install

```bash
pip install shelbytrain
```

## Quick Start

```python
from shelbytrain import load_dataset, ShelbyHTTPClient
from torch.utils.data import DataLoader

# Connect to Shelby
client = ShelbyHTTPClient(
    account="0x...",      # your Aptos account address
    api_key="AG-...",     # from geomi.dev
)

# Load dataset from Shelby — downloads on first run, cached after
dataset = load_dataset("manifest.uploaded.json", client=client)
loader  = DataLoader(dataset, batch_size=32, shuffle=True)

# Standard PyTorch training loop
for inputs, labels in loader:
    outputs = model(inputs)
    loss    = criterion(outputs, labels)
    loss.backward()
    optimizer.step()
```

## Supported Formats

| Format | Class | Use case |
|--------|-------|----------|
| `image-tar` | `ShelbyImageDataset` | Image classification |
| `text-jsonl` | `ShelbyTextDataset` | NLP, text classification |
| `parquet` | `ShelbyParquetDataset` | Tabular data, embeddings |
| `audio-tar` | `ShelbyAudioDataset` | Audio classification |

## Upload a Dataset

```python
from shelbytrain import create_image_shards

# Shard your dataset locally
manifest = create_image_shards(
    dataset_dir="data/my_images",
    output_dir="data/my_shards",
    shard_size=1000,
    dataset_name="my-dataset",
)

# Upload shards to Shelby using the CLI
# shelby upload data/my_shards/shards/shard-00000.tar my-dataset/shard-00000.tar -e "in 30 days"
```

## How It Works
Your dataset
↓ create_image_shards() / create_text_shards()
TAR shards + manifest.json
↓ shelby upload (Shelby CLI)
Shelby decentralized storage (Aptos blockchain)
↓ ShelbyImageDataset / load_dataset()
Local cache (.shelby-cache/)
↓ PyTorch DataLoader
Your model
**First run:** downloads shards from Shelby (~23s per shard)
**Every run after:** reads from local cache (~1.5s per shard)

## Sharing Datasets

Share your `manifest.uploaded.json` with anyone. They install ShelbyTrain, point to the manifest, and start training — no accounts, no copying files, no shared drives.

```python
# Anyone with the manifest can train on your dataset
dataset = load_dataset("manifest.uploaded.json", client=their_client)
```

## Requirements

- Python 3.10+
- PyTorch 2.0+
- A [Shelby account](https://shelby.xyz) and API key from [geomi.dev](https://geomi.dev)
- [Shelby CLI](https://docs.shelby.xyz) for uploads
