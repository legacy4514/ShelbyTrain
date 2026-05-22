from pathlib import Path
import tarfile
import csv
import hashlib
import json
import math
import time
from typing import Any, Dict


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_image_shards(
    dataset_dir: str,
    output_dir: str,
    shard_size: int = 1000,
    dataset_name: str = "mnist-demo",
) -> Dict[str, Any]:
    """Create TAR shards from an image dataset.

    Expected input layout:
        dataset_dir/
          images/
            000001.png
          labels.csv

    labels.csv must contain:
        filename,label
    """
    dataset_path = Path(dataset_dir)
    image_dir = dataset_path / "images"
    labels_path = dataset_path / "labels.csv"

    if not image_dir.exists():
        raise FileNotFoundError(f"Missing image directory: {image_dir}")
    if not labels_path.exists():
        raise FileNotFoundError(f"Missing labels file: {labels_path}")

    out = Path(output_dir)
    shards_dir = out / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    with labels_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError("labels.csv contains no samples")

    total = len(rows)
    shard_count = math.ceil(total / shard_size)

    manifest: Dict[str, Any] = {
        "name": dataset_name,
        "format": "image-tar",
        "version": "0.2.0",
        "created_at": int(time.time()),
        "integrity": "sha256",
        "total_samples": total,
        "shard_size": shard_size,
        "shards": [],
    }

    for shard_idx in range(shard_count):
        start = shard_idx * shard_size
        end = min(start + shard_size, total)
        shard_rows = rows[start:end]

        shard_name = f"shard-{shard_idx:05d}.tar"
        shard_path = shards_dir / shard_name
        temp_labels = out / f"labels-{shard_idx:05d}.csv"

        with temp_labels.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["filename", "label"])
            for row in shard_rows:
                writer.writerow([row["filename"], row["label"]])

        with tarfile.open(shard_path, "w") as tar:
            tar.add(temp_labels, arcname="labels.csv")
            for row in shard_rows:
                img_path = image_dir / row["filename"]
                if not img_path.exists():
                    raise FileNotFoundError(f"Missing image: {img_path}")
                tar.add(img_path, arcname=f"images/{row['filename']}")

        temp_labels.unlink()

        manifest["shards"].append(
            {
                "index": shard_idx,
                "file": shard_name,
                "samples": len(shard_rows),
                "local_path": str(shard_path),
                "blob_name": f"{dataset_name}/{shard_name}",
                "size_bytes": shard_path.stat().st_size,
                "sha256": sha256_file(shard_path),
            }
        )

        print(f"Created {shard_name} with {len(shard_rows)} samples")

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest saved to {manifest_path}")
    return manifest


def create_text_shards(
    jsonl_path: str,
    output_dir: str,
    shard_size: int = 10000,
    dataset_name: str = "text-dataset",
    text_field: str = "text",
    label_field: str = "label",
) -> Dict[str, Any]:
    """Create TAR shards from a JSONL text dataset.

    Expected input:
        jsonl_path — path to a .jsonl file, one JSON object per line
                     each line must have a text_field and optional label_field

    Example line:
        {"text": "The movie was great", "label": 1}
    """
    import json as _json

    jsonl = Path(jsonl_path)
    if not jsonl.exists():
        raise FileNotFoundError(f"Missing JSONL file: {jsonl}")

    out = Path(output_dir)
    shards_dir = out / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    with jsonl.open("r") as f:
        rows = [line.strip() for line in f if line.strip()]

    if not rows:
        raise ValueError("JSONL file contains no samples")

    total = len(rows)
    shard_count = math.ceil(total / shard_size)

    manifest: Dict[str, Any] = {
        "name": dataset_name,
        "format": "text-jsonl",
        "version": "0.2.0",
        "created_at": int(time.time()),
        "integrity": "sha256",
        "total_samples": total,
        "shard_size": shard_size,
        "text_field": text_field,
        "label_field": label_field,
        "shards": [],
    }

    for shard_idx in range(shard_count):
        start = shard_idx * shard_size
        end = min(start + shard_size, total)
        shard_rows = rows[start:end]

        shard_name = f"shard-{shard_idx:05d}.tar"
        shard_path = shards_dir / shard_name
        temp_jsonl = out / f"data-{shard_idx:05d}.jsonl"

        temp_jsonl.write_text("\n".join(shard_rows))

        with tarfile.open(shard_path, "w") as tar:
            tar.add(temp_jsonl, arcname="data.jsonl")

        temp_jsonl.unlink()

        manifest["shards"].append({
            "index": shard_idx,
            "file": shard_name,
            "samples": len(shard_rows),
            "local_path": str(shard_path),
            "blob_name": f"{dataset_name}/{shard_name}",
            "size_bytes": shard_path.stat().st_size,
            "sha256": sha256_file(shard_path),
        })
        print(f"Created {shard_name} with {len(shard_rows)} samples")

    manifest_path = out / "manifest.json"
    manifest_path.write_text(_json.dumps(manifest, indent=2))
    print(f"Manifest saved to {manifest_path}")
    return manifest


def create_parquet_shards(
    parquet_path: str,
    output_dir: str,
    shard_size: int = 50000,
    dataset_name: str = "parquet-dataset",
) -> Dict[str, Any]:
    """Create TAR shards from a Parquet file.

    Expected input:
        parquet_path — path to a .parquet file

    Good for:
        - Tabular datasets
        - Pre-computed embeddings
        - Feature vectors
    """
    import json as _json
    import pandas as pd

    parquet = Path(parquet_path)
    if not parquet.exists():
        raise FileNotFoundError(f"Missing Parquet file: {parquet}")

    out = Path(output_dir)
    shards_dir = out / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(parquet)
    total = len(df)
    shard_count = math.ceil(total / shard_size)

    manifest: Dict[str, Any] = {
        "name": dataset_name,
        "format": "parquet",
        "version": "0.2.0",
        "created_at": int(time.time()),
        "integrity": "sha256",
        "total_samples": total,
        "shard_size": shard_size,
        "columns": list(df.columns),
        "shards": [],
    }

    for shard_idx in range(shard_count):
        start = shard_idx * shard_size
        end = min(start + shard_size, total)
        shard_df = df.iloc[start:end]

        shard_name = f"shard-{shard_idx:05d}.tar"
        shard_path = shards_dir / shard_name
        temp_parquet = out / f"data-{shard_idx:05d}.parquet"

        shard_df.to_parquet(temp_parquet, index=False)

        with tarfile.open(shard_path, "w") as tar:
            tar.add(temp_parquet, arcname="data.parquet")

        temp_parquet.unlink()

        manifest["shards"].append({
            "index": shard_idx,
            "file": shard_name,
            "samples": len(shard_df),
            "local_path": str(shard_path),
            "blob_name": f"{dataset_name}/{shard_name}",
            "size_bytes": shard_path.stat().st_size,
            "sha256": sha256_file(shard_path),
        })
        print(f"Created {shard_name} with {len(shard_df)} samples")

    manifest_path = out / "manifest.json"
    manifest_path.write_text(_json.dumps(manifest, indent=2))
    print(f"Manifest saved to {manifest_path}")
    return manifest


def create_audio_shards(
    dataset_dir: str,
    output_dir: str,
    shard_size: int = 500,
    dataset_name: str = "audio-dataset",
) -> Dict[str, Any]:
    """Create TAR shards from an audio dataset.

    Expected input layout:
        dataset_dir/
          audio/
            clip_001.wav
            clip_002.wav
          labels.csv

    labels.csv must contain:
        filename,label
    """
    import json as _json

    dataset_path = Path(dataset_dir)
    audio_dir = dataset_path / "audio"
    labels_path = dataset_path / "labels.csv"

    if not audio_dir.exists():
        raise FileNotFoundError(f"Missing audio directory: {audio_dir}")
    if not labels_path.exists():
        raise FileNotFoundError(f"Missing labels file: {labels_path}")

    out = Path(output_dir)
    shards_dir = out / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    with labels_path.open("r", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("labels.csv contains no samples")

    total = len(rows)
    shard_count = math.ceil(total / shard_size)

    manifest: Dict[str, Any] = {
        "name": dataset_name,
        "format": "audio-tar",
        "version": "0.2.0",
        "created_at": int(time.time()),
        "integrity": "sha256",
        "total_samples": total,
        "shard_size": shard_size,
        "shards": [],
    }

    for shard_idx in range(shard_count):
        start = shard_idx * shard_size
        end = min(start + shard_size, total)
        shard_rows = rows[start:end]

        shard_name = f"shard-{shard_idx:05d}.tar"
        shard_path = shards_dir / shard_name
        temp_labels = out / f"labels-{shard_idx:05d}.csv"

        with temp_labels.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["filename", "label"])
            for row in shard_rows:
                writer.writerow([row["filename"], row["label"]])

        with tarfile.open(shard_path, "w") as tar:
            tar.add(temp_labels, arcname="labels.csv")
            for row in shard_rows:
                audio_path = audio_dir / row["filename"]
                if not audio_path.exists():
                    raise FileNotFoundError(f"Missing audio file: {audio_path}")
                tar.add(audio_path, arcname=f"audio/{row['filename']}")

        temp_labels.unlink()

        manifest["shards"].append({
            "index": shard_idx,
            "file": shard_name,
            "samples": len(shard_rows),
            "local_path": str(shard_path),
            "blob_name": f"{dataset_name}/{shard_name}",
            "size_bytes": shard_path.stat().st_size,
            "sha256": sha256_file(shard_path),
        })
        print(f"Created {shard_name} with {len(shard_rows)} samples")

    manifest_path = out / "manifest.json"
    manifest_path.write_text(_json.dumps(manifest, indent=2))
    print(f"Manifest saved to {manifest_path}")
    return manifest
