import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable


READY_STATES = {"verified", "cached"}
TERMINAL_FAILURE_STATES = {"failed", "expired"}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def state_path_for_manifest(manifest_path: str | Path) -> Path:
    return Path(manifest_path).parent / "shelby_state.json"


def shard_key(shard: Dict[str, Any]) -> str:
    if "index" in shard:
        return str(shard["index"])
    return str(shard.get("file", shard.get("blob_name", "unknown")))


def build_shard_entry(shard: Dict[str, Any], status: str = "local_created") -> Dict[str, Any]:
    return {
        "index": shard.get("index"),
        "file": shard.get("file"),
        "local_path": shard.get("local_path"),
        "blob_name": shard.get("blob_name"),
        "size_bytes": shard.get("size_bytes"),
        "sha256": shard.get("sha256"),
        "status": status,
        "last_error": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def _load_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_state(manifest_path: str | Path, state: Dict[str, Any]) -> Dict[str, Any]:
    state["updated_at"] = utc_now()
    path = state_path_for_manifest(manifest_path)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))
    return state


def load_state(manifest_path: str | Path, manifest: Dict[str, Any] | None = None) -> Dict[str, Any]:
    path = state_path_for_manifest(manifest_path)
    state = _load_json(path) or {
        "version": "0.1.0",
        "dataset_id": Path(manifest_path).parent.name,
        "dataset_name": (manifest or {}).get("name", Path(manifest_path).parent.name),
        "upload_prefix": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "shards": {},
    }

    state.setdefault("version", "0.1.0")
    state.setdefault("dataset_id", Path(manifest_path).parent.name)
    state.setdefault("dataset_name", (manifest or {}).get("name", Path(manifest_path).parent.name))
    state.setdefault("upload_prefix", None)
    state.setdefault("created_at", utc_now())
    state.setdefault("updated_at", utc_now())
    state.setdefault("shards", {})

    if manifest:
        changed = False
        for shard in manifest.get("shards", []):
            key = shard_key(shard)
            entry = state["shards"].get(key)
            if not entry:
                state["shards"][key] = build_shard_entry(shard)
                changed = True
                continue

            for field in ["index", "file", "local_path", "blob_name", "size_bytes", "sha256"]:
                value = shard.get(field)
                if value is not None and entry.get(field) != value:
                    entry[field] = value
                    changed = True
            entry.setdefault("status", "local_created")
            entry.setdefault("last_error", None)
            entry.setdefault("created_at", utc_now())
            entry.setdefault("updated_at", utc_now())

        if changed:
            save_state(manifest_path, state)

    return state


def set_upload_prefix(manifest_path: str | Path, upload_prefix: str) -> Dict[str, Any]:
    state = load_state(manifest_path)
    state["upload_prefix"] = upload_prefix
    return save_state(manifest_path, state)


def set_shard_status(
    manifest_path: str | Path,
    shard: Dict[str, Any],
    status: str,
    *,
    error: str | None = None,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = load_state(manifest_path)
    key = shard_key(shard)
    entry = state["shards"].get(key) or build_shard_entry(shard, status)

    for field in ["index", "file", "local_path", "blob_name", "size_bytes", "sha256"]:
        value = shard.get(field)
        if value is not None:
            entry[field] = value

    entry["status"] = status
    entry["updated_at"] = utc_now()
    entry["last_error"] = error
    if status == "uploading":
        entry["upload_started_at"] = entry["updated_at"]
    elif status == "uploaded":
        entry["uploaded_at"] = entry["updated_at"]
    elif status == "verified":
        entry["verified_at"] = entry["updated_at"]
    elif status == "cached":
        entry["cached_at"] = entry["updated_at"]
    elif status in TERMINAL_FAILURE_STATES:
        entry["failed_at"] = entry["updated_at"]

    if extra:
        entry.update(extra)

    state["shards"][key] = entry
    return save_state(manifest_path, state)


def merge_shard_state(manifest_path: str | Path, shards: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    state = load_state(manifest_path)
    merged = []
    for shard in shards:
        entry = state.get("shards", {}).get(shard_key(shard), {})
        merged.append({
            **shard,
            "lifecycle_status": entry.get("status", "local_created"),
            "last_error": entry.get("last_error"),
            "uploaded_at": entry.get("uploaded_at"),
            "verified_at": entry.get("verified_at"),
            "cached_at": entry.get("cached_at"),
        })
    return merged


def state_summary(manifest_path: str | Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state(manifest_path, manifest)
    counts: Dict[str, int] = {}
    for entry in state.get("shards", {}).values():
        status = entry.get("status", "local_created")
        counts[status] = counts.get(status, 0) + 1

    shard_count = len(manifest.get("shards", []))
    ready_count = sum(counts.get(status, 0) for status in READY_STATES)
    failed_count = sum(counts.get(status, 0) for status in TERMINAL_FAILURE_STATES)
    if shard_count and ready_count == shard_count:
        overall = "ready"
    elif failed_count:
        overall = "attention"
    elif counts.get("uploading") or counts.get("uploaded"):
        overall = "syncing"
    else:
        overall = "local"

    return {
        "state_path": str(state_path_for_manifest(manifest_path)),
        "lifecycle_status": overall,
        "state_counts": counts,
        "ready_shards": ready_count,
        "failed_shards": failed_count,
        "upload_prefix": state.get("upload_prefix"),
    }
