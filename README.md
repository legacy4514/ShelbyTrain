# ShelbyTrain

ShelbyTrain is a decentralized dataset pipeline for AI training.

It helps you take a dataset, split it into training-friendly shards, upload those shards to Shelby decentralized storage, and load them later from anywhere using PyTorch.

The simple idea:

```text
dataset -> shards -> Shelby storage -> manifest -> PyTorch DataLoader
```

## Install

```bash
pip install shelbytrain
```

The Python package provides the sharding, manifest, cache, Shelby download client, and PyTorch dataset loader pieces. The web app in this repository builds on top of those same ideas to make upload, benchmark, and reconstruction easier from a browser.

## The Problem

AI datasets are often hard to share and reproduce.

Teams pass around zip files, cloud drive links, private buckets, or local folders that only work on one machine. That creates a few real problems:

- Training data is not portable.
- Large files are expensive to move repeatedly.
- A model run can silently depend on a local folder nobody else has.
- Sharing data with another researcher or team usually means copying the whole dataset again.
- Re-running experiments wastes time downloading the same data over and over.

ShelbyTrain solves this by making the dataset addressable through a manifest.

Instead of sending someone the whole dataset, you send them a small `manifest.uploaded.json`. That manifest tells ShelbyTrain where the dataset shards live on Shelby and how to load them.

## What This Project Provides

ShelbyTrain has two parts:

1. **A web app**

   The app lets users connect a wallet, upload datasets, shard them, push them to Shelby, benchmark local vs Shelby loading, and reconstruct uploaded data from a manifest.

2. **A Python/PyTorch loader**

   The Python package reads a manifest, downloads shards from Shelby when needed, caches them locally, and exposes the data as a PyTorch dataset.

If you are installing from PyPI, the main thing you need is the Python loader/sharder API. If you are using the full repository, you also get the browser app.

## Why Shelby?

Shelby provides decentralized storage for data blobs. ShelbyTrain uses that storage layer for dataset shards.

The goal is not just to upload files. The goal is to make datasets easier to:

- share,
- verify,
- cache,
- reload,
- benchmark,
- and use in training workflows.

## Real World Use Cases

ShelbyTrain is useful for:

- AI researchers sharing reproducible training datasets.
- Small teams that do not want every member manually downloading the same large dataset.
- Hackathon and demo projects that need portable AI data.
- Open dataset publishing where the dataset should be accessible by manifest.
- Benchmarking local disk loading vs decentralized cold/cached loading.
- Reconstructing a dataset from a manifest someone sent you.

## Current Features

- Wallet-gated app experience.
- User-owned uploads through the Shelby browser SDK.
- Dataset sharding before upload.
- Manifest generation.
- Manifest sharing.
- PyTorch-compatible dataset loading.
- Local shard cache for faster repeat runs.
- Benchmark page for local, Shelby cold, and Shelby cached loading.
- Reconstruct page for rebuilding data from a sent manifest.
- Support for image, text, CSV, JSONL, JSON, PDF, DOCX, Parquet, and audio-oriented dataset flows.

## Supported Dataset Formats

| Format | Use case | Output |
| --- | --- | --- |
| `image-tar` | Image datasets | TAR shards with `images/` and `labels.csv` |
| `text-jsonl` | Text, CSV, PDF, DOCX, JSONL | TAR shards with `data.jsonl` |
| `parquet` | Tabular data or embeddings | TAR shards with Parquet data |
| `audio-tar` | Audio datasets | TAR shards with audio files and `labels.csv` |

For PDF and DOCX files, ShelbyTrain extracts the text and stores it as JSONL. Reconstructing those uploads returns extracted text, not the original binary PDF or DOCX file.

## How The App Works

1. Connect an Aptos/Shelby-compatible wallet.
2. Upload a dataset or select a dataset format.
3. ShelbyTrain creates local shards.
4. The browser uploads shards to Shelby using the connected wallet.
5. The backend writes a `manifest.uploaded.json`.
6. Anyone with the manifest and the Shelby account/API access can load or reconstruct the dataset.

The connected wallet is the upload authority.

## Manifest Example

```json
{
  "name": "bitcoinos",
  "format": "text-jsonl",
  "version": "0.2.0",
  "total_samples": 615,
  "shard_size": 10000,
  "text_field": "text",
  "label_field": "label",
  "shards": [
    {
      "index": 0,
      "file": "shard-00000.tar",
      "samples": 615,
      "blob_name": "bitcoinos-mpinvn45/shard-00000.tar",
      "size_bytes": 92160,
      "sha256": "..."
    }
  ]
}
```

For best portability, a shared manifest should also include the Shelby owner account:

```json
{
  "shelby_account": "0x..."
}
```

If the manifest does not include `shelby_account`, the Reconstruct page lets the user enter it manually.

For PyTorch users, the owner account matters because Shelby blob URLs are resolved from:

```text
shelby_account + blob_name
```

So a manifest with `blob_name` but no owner account is not fully self-contained. It can still work, but the user must know which account owns the blobs.

## PyTorch Usage

```python
from shelbytrain import load_dataset, ShelbyHTTPClient
from torch.utils.data import DataLoader

client = ShelbyHTTPClient(
    account="0x...",      # Shelby/Aptos account that owns the blobs
    api_key="...",        # Shelby API key
)

dataset = load_dataset("manifest.uploaded.json", client=client)
loader = DataLoader(dataset, batch_size=32, shuffle=True)

for inputs, labels in loader:
    outputs = model(inputs)
    loss = criterion(outputs, labels)
    loss.backward()
    optimizer.step()
```

On the first run, ShelbyTrain downloads shards from Shelby. After that, it uses the local cache.

## Creating Local Shards

Image datasets should be arranged like this:

```text
dataset/
  images/
    sample-001.png
    sample-002.png
  labels.csv
```

`labels.csv` should contain:

```csv
filename,label
sample-001.png,0
sample-002.png,1
```

Then create shards:

```python
from shelbytrain import create_image_shards

manifest = create_image_shards(
    dataset_dir="dataset",
    output_dir="data/my_dataset",
    shard_size=1000,
    dataset_name="my-dataset",
)
```

For text datasets, use JSONL:

```json
{"text": "hello world", "label": 0}
{"text": "another sample", "label": 1}
```

The generated `manifest.json` describes local shards. After upload, `manifest.uploaded.json` should include Shelby `blob_name` values for each shard.

## Reconstructing From A Sent Manifest

Use the app’s **Reconstruct** page.

1. Upload `manifest.uploaded.json`.
2. Enter the Shelby owner account if the manifest does not include it.
3. Click **Reconstruct data**.
4. ShelbyTrain downloads the shards from Shelby and returns the reconstructed file.

Current reconstruct outputs:

| Manifest format | Downloaded output |
| --- | --- |
| `text-jsonl` | `.txt` |
| `image-tar` | `.tar.gz` |
| `parquet` | `.parquet` |

## Project Status

ShelbyTrain is an experimental dataset pipeline. The current focus is proving a practical decentralized workflow for AI data:

- user-owned upload,
- portable manifests,
- PyTorch loading,
- caching,
- benchmarking,
- and reconstruction.

Future improvements could include original-file preservation for PDFs/DOCX, richer label editing, manifest signing, public dataset pages, and a smoother manifest-first PyTorch API.
