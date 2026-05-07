from pathlib import Path
import tarfile
import csv
import json
import math
from typing import Any, Dict


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
        "version": "0.1.0",
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
            }
        )

        print(f"Created {shard_name} with {len(shard_rows)} samples")

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest saved to {manifest_path}")
    return manifest
