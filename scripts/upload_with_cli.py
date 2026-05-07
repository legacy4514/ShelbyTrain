import json
import subprocess
from pathlib import Path

MANIFEST_PATH = Path("data/shelbytrain_mnist/manifest.json")


def run(cmd: list[str]) -> None:
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("Run scripts/create_shards.py first")

    manifest = json.loads(MANIFEST_PATH.read_text())

    for shard in manifest["shards"]:
        local_path = shard["local_path"]
        blob_name = shard["blob_name"]

        run(
            [
                "shelby",
                "upload",
                local_path,
                blob_name,
                "-e",
                "in 7 days",
                "--assume-yes",
            ]
        )

    updated_path = MANIFEST_PATH.parent / "manifest.uploaded.json"
    updated_path.write_text(json.dumps(manifest, indent=2))
    print(f"Saved uploaded manifest to {updated_path}")


if __name__ == "__main__":
    main()
