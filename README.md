# ShelbyTrain

**Streaming Dataset Shards from Shelby into ML Workflows**

ShelbyTrain is an experimental ML data pipeline built to evaluate Shelby as a high-performance dataset storage and delivery layer for AI training workflows.

The project demonstrates how image datasets can be:

1. prepared locally,
2. converted into dataset shards,
3. uploaded to Shelby,
4. downloaded and cached,
5. streamed into PyTorch,
6. benchmarked against local storage performance.
It is a developer/research layer built on top of Shelby to test how Shelby performs under repeated ML dataset access workloads.

---

# Project Goal

The goal of this MVP is to answer a simple question:

> Can Shelby function as a practical remote dataset layer for machine learning workflows?

The project focuses specifically on:

- repeated dataset access,
- caching efficiency,
- initialization latency,
- throughput during training,
- and integration into PyTorch pipelines.

---

# Current MVP Features

- MNIST image dataset preparation
- Dataset sharding system
- Manifest generation
- Shelby blob upload/download
- Local shard caching
- PyTorch dataset integration
- Benchmarking system
- Cold vs cached performance comparison

---

# Architecture Overview

```text
Images
   ↓
Dataset Shards (.tar)
   ↓
Manifest.json
   ↓
Upload to Shelby
   ↓
Shelby Blob Storage
   ↓
Download + Cache
   ↓
PyTorch Dataset Loader
   ↓
Benchmark + Training Workflow
```

---

# Project Structure

```text
ShelbyTrain/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── shelbytrain/
│   ├── __init__.py
│   ├── benchmark.py
│   ├── cache.py
│   ├── client.py
│   ├── dataset.py
│   └── sharder.py
│
├── scripts/
│   ├── benchmark.py
│   ├── create_shards.py
│   ├── prepare_sample_dataset.py
│   ├── test_loader.py
│   ├── test_loader_shelby.py
│   └── upload_with_cli.py
│
└── data/
```

---

# System Requirements

Recommended environment:

- Ubuntu / WSL / Linux / macOS
- Python 3.9+
- Node.js 20+
- npm
- Git
- Shelby CLI

Install required system packages:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git curl unzip -y
```

---

# Python Packages

Create `requirements.txt`:

```txt
torch
torchvision
pillow
requests
tqdm
python-dotenv
```

---

# Environment Setup

Clone the repository:

```bash
git clone YOUR_REPO_URL
cd ShelbyTrain
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate the environment:

```bash
source .venv/bin/activate
```

Upgrade pip:

```bash
pip install --upgrade pip
```

Install dependencies:

```bash
pip install -r requirements.txt
```

If PyTorch install fails:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install pillow requests tqdm python-dotenv
```

Verify installation:

```bash
python -c "import torch; import torchvision; print('OK')"
```

---

# Fix Python Import Path

If you encounter:

```text
ModuleNotFoundError: No module named 'shelbytrain'
```

Run:

```bash
export PYTHONPATH=$PWD
```

Optional permanent fix:

```bash
echo 'export PYTHONPATH=$PWD' >> ~/.bashrc
source ~/.bashrc
```

---

# Shelby CLI Setup

ShelbyTrain uses Shelby CLI to upload dataset shards.

## Install Node.js 20 using NVM

Install NVM:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
```

Install Node.js:

```bash
nvm install 20
nvm use 20
nvm alias default 20
```

Verify:

```bash
node -v
npm -v
```

---

## Install Shelby CLI

```bash
npm i -g @shelby-protocol/cli
```

Verify installation:

```bash
shelby --version
```

Initialize Shelby:

```bash
shelby init
```

Recommended context:

```text
shelbynet
```

Verify contexts:

```bash
shelby context list
```

Verify account:

```bash
shelby account balance
```

---

# Environment Variables

Create `.env`:

```bash
touch .env
```

Add:

```env
SHELBY_ACCOUNT=0xyour_account_address
SHELBY_API_KEY=your_api_key_here
```

Create `.env.example`:

```env
SHELBY_ACCOUNT=0xyour_account_address
SHELBY_API_KEY=your_api_key_here
```

---

# Run Local Test

Prepare sample dataset:

```bash
python scripts/prepare_sample_dataset.py
```

Create shards:

```bash
python scripts/create_shards.py
```

Test local loader:

```bash
python scripts/test_loader.py
```

Expected output:

```text
Indexed 5000 samples
Images shape: torch.Size([32, 1, 28, 28])
Labels shape: torch.Size([32])
```

---

# Upload Shards to Shelby

Upload dataset shards:

```bash
python scripts/upload_with_cli.py
```

Verify uploaded blobs:

```bash
shelby account blobs
```

---

# Test Shelby Loader

Run Shelby-backed loader:

```bash
python scripts/test_loader_shelby.py
```

First run:
- downloads shards from Shelby

Second run:
- uses local cache

---

# Run Benchmark

Clear cache before cold benchmark:

```bash
rm -rf .shelby-cache
```

Run benchmark:

```bash
python scripts/benchmark.py
```

View benchmark results:

```bash
cat benchmark-results.json
```

---

# Benchmark Results

Example benchmark from MVP test:

```json
{
  "local": {
    "batches": 50,
    "batch_size": 32,
    "samples": 1600,
    "time_to_first_batch_sec": 0.1105,
    "total_time_sec": 0.6918,
    "samples_per_sec": 2312.66
  },
  "shelby_cold": {
    "batches": 50,
    "batch_size": 32,
    "samples": 1600,
    "time_to_first_batch_sec": 0.0196,
    "total_time_sec": 0.7025,
    "samples_per_sec": 2277.53,
    "dataset_init_download_sec": 16.4761
  },
  "shelby_cached": {
    "batches": 50,
    "batch_size": 32,
    "samples": 1600,
    "time_to_first_batch_sec": 0.0139,
    "total_time_sec": 0.6019,
    "samples_per_sec": 2658.17,
    "dataset_init_cache_sec": 1.7567
  }
}
```

---

# Benchmark Interpretation

| Mode | Init Time | Time to First Batch | Samples/sec |
|---|---:|---:|---:|
| Local | ~0s | 0.1105s | 2312.66 |
| Shelby Cold | 16.48s | 0.0196s | 2277.53 |
| Shelby Cached | 1.76s | 0.0139s | 2658.17 |

---

# Key Findings

- Shelby cold start introduced a ~16.48 second initialization cost.
- Cached startup reduced initialization time by ~9x.
- Cached throughput exceeded Shelby cold throughput by ~16.7%.
- Cached throughput exceeded local throughput by ~14.9% in this experiment.

---

# Conclusion

Shelby behaves like a remote dataset layer with a one-time initialization cost.

Once shards are downloaded and cached locally, training throughput becomes comparable to or faster than local dataset reads.

This makes Shelby particularly promising for:

- repeated training workflows,
- reusable AI datasets,
- distributed dataset delivery,
- and large-scale media/data pipelines.

---

# Limitations

This project is currently an MVP prototype intended for benchmarking and architectural validation.

Current limitations include:

- Uses MNIST-scale image datasets only
- Dataset loader downloads full shards before training begins
- No true range-based or partial sample loading implemented
- Cold-start performance varies with network conditions and shard count
- Not optimized for distributed or multi-node training workloads
- No parallel shard prefetching pipeline
- No GPU-specific optimization or acceleration
- Benchmark scope currently focused on repeated-read training scenarios

---

# Recommended Next Improvements

- Add range-request based loading
- Add concurrent shard downloading
- Add retry/failure analytics
- Add larger dataset benchmarks
- Add distributed training support
- Add dataset metadata indexing
- Add benchmark visualization dashboard
- Add CLI commands:
  - `shelbytrain prepare`
  - `shelbytrain shard`
  - `shelbytrain upload`
  - `shelbytrain benchmark`

---

# Contribution Summary

ShelbyTrain is an experimental ML integration layer built on top of Shelby.

It extends Shelby’s AI use case by adding:

- dataset sharding,
- manifest generation,
- PyTorch integration,
- caching,
- benchmarking,
- and ML workflow validation.

The project demonstrates how Shelby can function as a reusable dataset layer for repeated AI training workloads.

---

# Future Direction

The next stage of ShelbyTrain is a lightweight dashboard/dApp that will allow users to:

- upload datasets,
- visualize shards,
- monitor benchmarks,
- preview samples,
- and test dataset delivery performance directly from the browser.

---

# License

MIT