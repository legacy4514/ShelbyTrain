import json
import subprocess
import time
from pathlib import Path
from shelbytrain.lifecycle import set_shard_status, set_upload_prefix, utc_now

MANIFEST_PATH = Path("data/shelbytrain_mnist/manifest.json")
MAX_RETRIES = 3
RETRY_DELAY = 10


def run_with_retry(cmd: list[str], retries: int = MAX_RETRIES) -> bool:
    print(" ".join(cmd))
    for attempt in range(1, retries + 1):
        try:
            subprocess.run(cmd, check=True)
            return True
        except subprocess.CalledProcessError:
            if attempt < retries:
                print(f"  ✖ Attempt {attempt}/{retries} failed. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  ✖ All {retries} attempts failed.")
                return False
    return False


def main():
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("Run scripts/create_shards.py first")

    manifest = json.loads(MANIFEST_PATH.read_text())

    # Generate upload prefix from timestamp
    upload_prefix = time.strftime("%Y%m%d-%H%M%S")
    set_upload_prefix(MANIFEST_PATH, upload_prefix)
    print(f"Upload prefix: {upload_prefix}")

    # Update blob names in manifest to use new prefix
    for shard in manifest["shards"]:
        shard["blob_name"] = f"{upload_prefix}/{shard['file']}"

    failed = []

    for shard in manifest["shards"]:
        local_path = shard["local_path"]
        blob_name = shard["blob_name"]

        # Mark as uploading
        set_shard_status(MANIFEST_PATH, shard, "uploading")

        success = run_with_retry([
            "shelby", "upload",
            local_path, blob_name,
            "-e", "in 7 days",
            "--assume-yes",
        ])

        if success:
            # Mark as verified after successful upload
            set_shard_status(MANIFEST_PATH, shard, "verified")
        else:
            set_shard_status(MANIFEST_PATH, shard, "failed",
                           error="Upload failed after max retries")
            failed.append(blob_name)

    # Save updated manifest with new blob names
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

    uploaded_path = MANIFEST_PATH.parent / "manifest.uploaded.json"
    uploaded_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nSaved uploaded manifest to {uploaded_path}")

    if failed:
        print(f"\n⚠ {len(failed)} shards failed:")
        for f in failed:
            print(f"  - {f}")
        print("Re-run this script to retry.")
    else:
        print(f"\n✓ All {len(manifest['shards'])} shards uploaded and verified!")


if __name__ == "__main__":
    main()
