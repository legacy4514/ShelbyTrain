from __future__ import annotations

import json
import os
import re
import shutil
import copy
import hashlib
import subprocess
import socket
import time
import uuid
from pathlib import Path
from typing import Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from shelbytrain.lifecycle import (
    READY_STATES,
    load_state,
    merge_shard_state,
    set_shard_status,
    set_upload_prefix,
    state_summary,
)

load_dotenv()
runs: Dict[str, Dict[str, Any]] = {}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
BENCHMARK_HISTORY_PATH = Path("data") / "benchmark_history.json"
WALLET_ROOT = Path("data") / "wallets"
TRANSIENT_SHELBY_CLI_ERRORS = (
    "connect timeout",
    "timed out",
    "eai_again",
    "getaddrinfo",
    "session closed without receiving a settings frame",
    "settings frame",
    "connection reset",
    "connection refused",
    "failed to complete multipart upload",
    "internal server error",
    "status: 500",
    "temporary failure",
    "unexpected eof",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="ShelbyTrain API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_client(account: str | None = None):
    from shelbytrain.client import ShelbyHTTPClient
    account = account or os.environ.get("SHELBY_ACCOUNT")
    if not account:
        raise HTTPException(status_code=400, detail="Shelby account not available")
    return ShelbyHTTPClient(
        account=account,
        api_key=os.getenv("SHELBY_API_KEY"),
        rpc_base_url=os.getenv("SHELBY_RPC_BASE_URL", "https://api.shelbynet.shelby.xyz/shelby"),
    )

def compact_error(message: str, limit: int = 700) -> str:
    message = ANSI_RE.sub("", message or "").strip()
    message = re.sub(r"https://api\.shelbynet\.shelby\.xyz/shelby/v1/blobs/[^\s]+", "Shelby blob URL", message)
    message = re.sub(r"\s+", " ", message)
    if len(message) <= limit:
        return message
    return f"{message[:limit].rstrip()}..."

def is_transient_shelby_cli_error(message: str) -> bool:
    lower = compact_error(message, 1200).lower()
    return any(pattern in lower for pattern in TRANSIENT_SHELBY_CLI_ERRORS)

def format_shelby_cli_error(output: str, fallback: str, attempts: int | None = None) -> str:
    cleaned = compact_error(output or fallback)
    lower = cleaned.lower()
    suffix = f" after {attempts} attempts" if attempts else ""
    if "connect timeout" in lower or "timed out" in lower:
        return (
            f"Shelby CLI timed out while contacting api.shelbynet.shelby.xyz{suffix}. "
            "The dataset was not fully uploaded, so Shelby benchmarks cannot run yet. "
            "Use Resume Upload to retry only unfinished shards."
        )
    if "eai_again" in lower or "getaddrinfo" in lower:
        return (
            f"Shelby CLI could not resolve api.shelbynet.shelby.xyz{suffix}. "
            "This is a DNS/network issue between this machine and Shelby RPC. "
            "ShelbyTrain will retry transient failures; use Resume Upload if the run stops."
        )
    if "settings frame" in lower:
        return (
            f"Shelby CLI session closed while opening the Shelby RPC connection{suffix}. "
            "This is usually a transient HTTP/2/RPC issue, not a dataset problem. "
            "Use Resume Upload to retry only unfinished shards."
        )
    if "failed to complete multipart upload" in lower or "internal server error" in lower or "status: 500" in lower:
        return (
            f"Shelby RPC failed while completing the multipart upload{suffix}. "
            "This is a Shelby-side 500 error after the upload started. "
            "ShelbyTrain retries this automatically; use Resume Upload if the run stops."
        )
    if "already exists" in lower:
        return (
            "A Shelby blob with this name already exists. Retry the upload; ShelbyTrain now creates "
            "a fresh upload prefix for each run, so this usually means an older job is still being reused."
        )
    return f"shelby CLI error: {cleaned}"

def model_payload(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()

def safe_wallet_id(wallet: str | None) -> str | None:
    if not wallet:
        return None
    return re.sub(r"[^a-zA-Z0-9_-]", "_", wallet.lower())

def wallet_workspace(wallet: str | None) -> Path:
    safe_wallet = safe_wallet_id(wallet)
    if not safe_wallet:
        return Path("data")
    return WALLET_ROOT / safe_wallet

def wallet_data_root(wallet: str | None) -> Path:
    return wallet_workspace(wallet) / "datasets" if wallet else Path("data")

def wallet_uploads_root(wallet: str | None) -> Path:
    return wallet_workspace(wallet) / "uploads" if wallet else Path("data") / "uploads"

def wallet_cache_dir(wallet: str | None) -> Path:
    return wallet_workspace(wallet) / ".shelby-cache" if wallet else Path(".shelby-cache")

def wallet_benchmark_history_path(wallet: str | None) -> Path:
    return wallet_workspace(wallet) / "benchmark_history.json" if wallet else BENCHMARK_HISTORY_PATH

def wallet_result_path(wallet: str | None, run_id: str) -> Path:
    if wallet:
        return wallet_workspace(wallet) / f"benchmark-results-{run_id[:8]}.json"
    return Path(f"benchmark-results-{run_id[:8]}.json")

def scoped_output_dir(output_dir: str, wallet: str | None) -> str:
    if not wallet:
        return output_dir
    return str(wallet_data_root(wallet) / Path(output_dir).name)

def shelby_diagnostics() -> Dict[str, Any]:
    rpc_base_url = os.getenv("SHELBY_RPC_BASE_URL", "https://api.shelbynet.shelby.xyz/shelby")
    host = rpc_base_url.replace("https://", "").replace("http://", "").split("/", 1)[0]
    account = os.getenv("SHELBY_ACCOUNT", "")
    api_key = os.getenv("SHELBY_API_KEY", "")
    checks: Dict[str, Any] = {
        "env": {
            "shelby_account_set": bool(account),
            "shelby_account_suffix": account[-8:] if account else None,
            "shelby_api_key_set": bool(api_key),
            "shelby_rpc_base_url": rpc_base_url,
        }
    }

    try:
        checks["dns"] = {
            "ok": True,
            "host": host,
            "addresses": sorted({info[4][0] for info in socket.getaddrinfo(host, 443)})[:5],
        }
    except Exception as exc:
        checks["dns"] = {"ok": False, "host": host, "error": compact_error(str(exc), 300)}

    try:
        import requests
        response = requests.head(rpc_base_url, timeout=10)
        checks["rpc"] = {
            "ok": response.status_code < 500,
            "status_code": response.status_code,
            "reachable": True,
        }
    except Exception as exc:
        checks["rpc"] = {"ok": False, "reachable": False, "error": compact_error(str(exc), 300)}

    try:
        version = subprocess.run(["shelby", "--version"], check=True, capture_output=True, text=True, timeout=10)
        checks["cli"] = {"ok": True, "version": version.stdout.strip()}
    except Exception as exc:
        checks["cli"] = {"ok": False, "error": compact_error(str(exc), 300)}

    auth_probe = {"checked": False}
    try:
        uploaded = next((m for m in find_manifests() if m.get("uploaded_path")), None)
        if uploaded:
            manifest = json.loads(Path(uploaded["uploaded_path"]).read_text())
            shard = next((s for s in manifest.get("shards", []) if s.get("blob_name")), None)
            if shard:
                available, reason = get_client().blob_available(shard["blob_name"], shard.get("size_bytes"))
                auth_probe = {
                    "checked": True,
                    "ok": available,
                    "reason": reason,
                    "blob": shard["blob_name"],
                }
    except Exception as exc:
        auth_probe = {"checked": True, "ok": False, "reason": compact_error(str(exc), 300)}
    checks["auth_probe"] = auth_probe

    if checks["auth_probe"].get("reason"):
        reason = str(checks["auth_probe"]["reason"]).lower()
        checks["api_key_possible"] = "401" in reason or "403" in reason or "unauthorized" in reason or "forbidden" in reason
    else:
        checks["api_key_possible"] = False

    return checks

def check_uploaded_shards(uploaded_manifest_path: str, max_shards: int, account: str | None = None) -> list[str]:
    uploaded_path = Path(uploaded_manifest_path)
    manifest_path = uploaded_path.parent / "manifest.json"
    manifest = json.loads(uploaded_path.read_text())
    shards = manifest.get("shards", [])[:max_shards]
    state = load_state(manifest_path if manifest_path.exists() else uploaded_path, manifest)
    client = get_client(account)
    unavailable = []

    for shard in shards:
        entry = state.get("shards", {}).get(str(shard.get("index")), {})
        status = entry.get("status", "local_created")
        if status not in READY_STATES and status not in {"local_created", "uploaded"}:
            unavailable.append(
                f"{shard.get('file', shard.get('index', '?'))}: lifecycle state is "
                f"{status}, not verified"
            )
            continue

        blob_name = shard.get("blob_name")
        if not blob_name:
            unavailable.append(f"shard {shard.get('index', '?')} has no blob_name")
            continue

        available, reason = client.blob_available(blob_name, shard.get("size_bytes"))
        if not available:
            unavailable.append(f"{blob_name}: {compact_error(reason or 'unavailable', 260)}")
            set_shard_status(manifest_path if manifest_path.exists() else uploaded_path, shard, "failed", error=reason)
        elif entry.get("status") != "cached":
            set_shard_status(manifest_path if manifest_path.exists() else uploaded_path, shard, "verified")

    return unavailable

def mark_cached_shards(uploaded_manifest_path: str, max_shards: int, wallet: str | None = None) -> None:
    uploaded_path = Path(uploaded_manifest_path)
    manifest_path = uploaded_path.parent / "manifest.json"
    manifest = json.loads(uploaded_path.read_text())
    target_manifest_path = manifest_path if manifest_path.exists() else uploaded_path
    cache_index_path = wallet_cache_dir(wallet) / "index.json"
    if not cache_index_path.exists():
        return
    try:
        cache_index = json.loads(cache_index_path.read_text())
    except Exception:
        return

    cache_entries = cache_index.get("shards", {})
    for shard in manifest.get("shards", [])[:max_shards]:
        blob_name = shard.get("blob_name")
        if not blob_name:
            continue
        cache_key = blob_name.replace("/", "__")
        if cache_entries.get(cache_key, {}).get("valid"):
            set_shard_status(target_manifest_path, shard, "cached")

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def ensure_manifest_integrity(manifest: Dict[str, Any]) -> Dict[str, Any]:
    manifest.setdefault("version", "0.2.0")
    manifest.setdefault("integrity", "sha256")
    for shard in manifest.get("shards", []):
        local_path = Path(shard.get("local_path", ""))
        if local_path.exists():
            shard["size_bytes"] = local_path.stat().st_size
            shard.setdefault("sha256", sha256_file(local_path))
    return manifest

def attach_dataset_metrics(result: Dict[str, Any], dataset: Any, init_sec: float) -> Dict[str, Any]:
    metrics = dict(getattr(dataset, "metrics", {}) or {})
    metrics["dataset_init_sec"] = round(init_sec, 6)
    result["dataset_metrics"] = metrics
    for key in [
        "cache_hits",
        "cache_misses",
        "downloads",
        "download_sec",
        "verify_sec",
        "extract_sec",
        "index_sec",
        "bytes_downloaded",
    ]:
        if key in metrics:
            result[key] = metrics[key]
    return result

def benchmark_speedup(results: Dict[str, Any]) -> Dict[str, Any]:
    cached = results.get("shelby_cached") or {}
    cold = results.get("shelby_cold") or {}
    local = results.get("local") or {}
    speedups = {}
    if cached.get("time_to_first_batch_sec") and cold.get("time_to_first_batch_sec"):
        speedups["cache_init_speedup"] = round(
            cold["time_to_first_batch_sec"] / cached["time_to_first_batch_sec"],
            4,
        )
    if cached.get("samples_per_sec") and local.get("samples_per_sec"):
        speedups["cached_vs_local_throughput"] = round(
            cached["samples_per_sec"] / local["samples_per_sec"],
            4,
        )
    return speedups

def load_benchmark_history(wallet: str | None = None) -> list[Dict[str, Any]]:
    history_path = wallet_benchmark_history_path(wallet)
    if not history_path.exists():
        return []
    try:
        data = json.loads(history_path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_benchmark_history(history: list[Dict[str, Any]], wallet: str | None = None) -> None:
    history_path = wallet_benchmark_history_path(wallet)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history[:100], indent=2))

def record_benchmark_history(entry: Dict[str, Any], wallet: str | None = None) -> None:
    history = load_benchmark_history(wallet)
    history = [item for item in history if item.get("run_id") != entry.get("run_id")]
    history.insert(0, entry)
    save_benchmark_history(history, wallet)

def pipeline_summary(wallet: str | None = None) -> Dict[str, Any]:
    datasets = find_manifests(wallet)
    total_shards = sum(d.get("shard_count", 0) for d in datasets)
    ready_shards = sum(d.get("ready_shards", 0) for d in datasets)
    failed_shards = sum(d.get("failed_shards", 0) for d in datasets)
    lifecycle_counts: Dict[str, int] = {}
    for dataset in datasets:
        for status, count in (dataset.get("state_counts") or {}).items():
            lifecycle_counts[status] = lifecycle_counts.get(status, 0) + count

    cache = cache_stats_for_wallet(wallet)
    history = load_benchmark_history(wallet)
    latest = history[0] if history else None
    successful = [run for run in history if run.get("status") == "done"]
    failed = [run for run in history if run.get("status") == "error"]

    return {
        "datasets": datasets,
        "dataset_count": len(datasets),
        "total_shards": total_shards,
        "ready_shards": ready_shards,
        "failed_shards": failed_shards,
        "readiness_pct": round((ready_shards / total_shards) * 100, 1) if total_shards else 0,
        "lifecycle_counts": lifecycle_counts,
        "cache": cache,
        "benchmark_runs": len(history),
        "successful_benchmark_runs": len(successful),
        "failed_benchmark_runs": len(failed),
        "latest_benchmark": latest,
        "recent_benchmarks": history[:8],
    }

def get_wallet_address(request: Request) -> str | None:
    """Extract wallet address from request header."""
    return request.headers.get("X-Wallet-Address")


def require_wallet(request: Request) -> str:
    """Require wallet address or raise 401."""
    addr = get_wallet_address(request)
    if not addr:
        raise HTTPException(
            status_code=401,
            detail="Wallet not connected. Please connect your Aptos wallet to continue."
        )
    return addr


def find_manifests(wallet: str | None = None):
    data_root = wallet_data_root(wallet)
    manifests = []
    if not data_root.exists():
        return manifests
    for p in data_root.rglob("manifest.json"):
        try:
            m = json.loads(p.read_text())
            uploaded = p.parent / "manifest.uploaded.json"
            summary = state_summary(p, m)
            manifests.append({
                "id": p.parent.name,
                "path": str(p),
                "uploaded_path": str(uploaded) if uploaded.exists() else None,
                "name": m.get("name", p.parent.name),
                "format": m.get("format", "unknown"),
                "total_samples": m.get("total_samples", 0),
                "shard_count": len(m.get("shards", [])),
                "shard_size": m.get("shard_size", 0),
                "uploaded": uploaded.exists(),
                **summary,
            })
        except Exception:
            continue
    return manifests

def find_manifest_path(dataset_id: str, wallet: str | None = None) -> Path | None:
    for m in find_manifests(wallet):
        if m["id"] == dataset_id:
            return Path(m["path"])
    return None

class ClientUploadedShard(BaseModel):
    index: int
    blob_name: str

class ClientUploadCompleteRequest(BaseModel):
    dataset_id: str
    upload_prefix: str
    shards: list[ClientUploadedShard]

def upload_dataset_job(req: UploadRequest, job_id: str, *, resume: bool, wallet: str | None = None) -> None:
    manifest_path = find_manifest_path(req.dataset_id, wallet)
    if not manifest_path:
        runs[job_id] = {"status": "error", "error": "Dataset not found", "job_id": job_id}
        return

    manifest = ensure_manifest_integrity(json.loads(manifest_path.read_text()))
    manifest_path.write_text(json.dumps(manifest, indent=2))
    state = load_state(manifest_path, manifest)

    if resume:
        upload_prefix = state.get("upload_prefix") or f"{manifest.get('name', req.dataset_id)}-{job_id[:8]}"
    else:
        upload_prefix = f"{manifest.get('name', req.dataset_id)}-{job_id[:8]}"
    set_upload_prefix(manifest_path, upload_prefix)

    upload_manifest = copy.deepcopy(manifest)
    state = load_state(manifest_path, manifest)
    state_shards = state.get("shards", {})
    ready_statuses = READY_STATES
    target_shards = []
    verified_count = 0

    for shard in upload_manifest["shards"]:
        entry = state_shards.get(str(shard.get("index")), {})
        existing_blob = entry.get("blob_name")
        shard["blob_name"] = existing_blob if resume and existing_blob else f"{upload_prefix}/{shard['file']}"

        if resume and entry.get("status") in ready_statuses:
            verified_count += 1
            continue
        target_shards.append(shard)

    runs[job_id].update({
        "total": len(upload_manifest["shards"]),
        "uploaded": verified_count,
        "skipped": verified_count,
        "pending": len(target_shards),
        "upload_prefix": upload_prefix,
    })

    current_shard = None
    try:
        client = get_client()
        max_attempts = max(1, int(os.getenv("SHELBY_UPLOAD_RETRIES", "5")))
        for shard in target_shards:
            current_shard = shard
            if resume and shard.get("blob_name"):
                available, reason = client.blob_available(shard["blob_name"], shard.get("size_bytes"))
                if available:
                    verified_count += 1
                    runs[job_id]["uploaded"] = verified_count
                    set_shard_status(manifest_path, shard, "verified")
                    continue
                set_shard_status(manifest_path, shard, "failed", error=reason)

            set_shard_status(manifest_path, shard, "uploading")
            last_cli_output = ""
            for attempt in range(1, max_attempts + 1):
                runs[job_id].update({
                    "current_shard": shard.get("file"),
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                })
                try:
                    subprocess.run(
                        ["shelby", "upload", shard["local_path"], shard["blob_name"],
                         "-e", req.expiration, "--assume-yes"],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    last_cli_output = ""
                    break
                except subprocess.CalledProcessError as e:
                    stdout = e.stdout.decode(errors="replace") if e.stdout else ""
                    stderr = e.stderr.decode(errors="replace") if e.stderr else ""
                    last_cli_output = "\n".join(part for part in [stderr.strip(), stdout.strip()] if part)

                    available, reason = client.blob_available(shard["blob_name"], shard.get("size_bytes"))
                    if available:
                        last_cli_output = ""
                        break

                    message = format_shelby_cli_error(last_cli_output, str(e), attempt)
                    set_shard_status(
                        manifest_path,
                        shard,
                        "uploading" if attempt < max_attempts and is_transient_shelby_cli_error(last_cli_output) else "failed",
                        error=message,
                        extra={"attempt": attempt, "max_attempts": max_attempts},
                    )
                    runs[job_id]["last_error"] = message

                    if attempt < max_attempts and is_transient_shelby_cli_error(last_cli_output):
                        time.sleep(min(2 ** attempt, 10))
                        continue
                    raise

            if last_cli_output:
                raise RuntimeError(format_shelby_cli_error(last_cli_output, last_cli_output, max_attempts))

            set_shard_status(manifest_path, shard, "uploaded")

            available, reason = client.blob_available(shard["blob_name"], shard.get("size_bytes"))
            if not available:
                set_shard_status(manifest_path, shard, "failed", error=reason)
                raise RuntimeError(
                    "Shelby upload completed for a shard, but it is not readable yet. "
                    f"{shard['blob_name']}: {compact_error(reason or 'unavailable', 260)}"
                )

            verified_count += 1
            runs[job_id]["uploaded"] = verified_count
            set_shard_status(manifest_path, shard, "verified")

        uploaded_path = manifest_path.parent / "manifest.uploaded.json"
        uploaded_path.write_text(json.dumps(upload_manifest, indent=2))
        runs[job_id].update({
            "status": "done",
            "step": "uploaded",
            "uploaded_manifest": str(uploaded_path),
            "uploaded": len(upload_manifest["shards"]),
            "pending": 0,
        })
    except subprocess.CalledProcessError as e:
        stdout = e.stdout.decode(errors="replace") if e.stdout else ""
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        output = "\n".join(part for part in [stderr.strip(), stdout.strip()] if part)
        attempts = runs.get(job_id, {}).get("max_attempts")
        message = format_shelby_cli_error(output, str(e), attempts)
        if current_shard:
            set_shard_status(manifest_path, current_shard, "failed", error=message)
        runs[job_id] = {
            "status": "error",
            "error": message,
            "job_id": job_id,
            "uploaded": runs.get(job_id, {}).get("uploaded", verified_count),
            "total": len(upload_manifest["shards"]),
            "upload_prefix": upload_prefix,
        }
    except Exception as e:
        message = compact_error(str(e))
        if current_shard:
            set_shard_status(manifest_path, current_shard, "failed", error=message)
        runs[job_id] = {
            "status": "error",
            "error": message,
            "job_id": job_id,
            "uploaded": runs.get(job_id, {}).get("uploaded", verified_count),
            "total": len(upload_manifest["shards"]),
            "upload_prefix": upload_prefix,
        }

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/api/system/diagnostics")
def system_diagnostics():
    return shelby_diagnostics()

@app.get("/api/datasets")
def list_datasets(request: Request):
    return {"datasets": find_manifests(require_wallet(request))}

@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: str, request: Request):
    wallet = require_wallet(request)
    for m in find_manifests(wallet):
        if m["id"] == dataset_id:
            manifest = json.loads(Path(m["path"]).read_text())
            shards = manifest.get("shards", [])
            if m.get("uploaded_path"):
                try:
                    uploaded_manifest = json.loads(Path(m["uploaded_path"]).read_text())
                    uploaded_by_index = {s.get("index"): s for s in uploaded_manifest.get("shards", [])}
                    shards = [{**s, **uploaded_by_index.get(s.get("index"), {})} for s in shards]
                except Exception:
                    pass
            m["shards"] = merge_shard_state(m["path"], shards)
            return m
    raise HTTPException(status_code=404, detail="Dataset not found")

@app.get("/api/datasets/{dataset_id}/shards")
def list_shards(dataset_id: str, request: Request):
    wallet = require_wallet(request)
    for m in find_manifests(wallet):
        if m["id"] == dataset_id:
            manifest = json.loads(Path(m["path"]).read_text())
            return {"shards": merge_shard_state(m["path"], manifest.get("shards", []))}
    raise HTTPException(status_code=404, detail="Dataset not found")

@app.get("/api/datasets/{dataset_id}/shards/{shard_index}/download")
def download_shard(dataset_id: str, shard_index: int, request: Request):
    wallet = require_wallet(request)
    manifest_path = find_manifest_path(dataset_id, wallet)
    if not manifest_path:
        raise HTTPException(status_code=404, detail="Dataset not found")

    manifest = json.loads(manifest_path.read_text())
    shard = next((s for s in manifest.get("shards", []) if int(s.get("index", -1)) == shard_index), None)
    if not shard:
        raise HTTPException(status_code=404, detail="Shard not found")

    shard_path = Path(shard.get("local_path", "")).resolve()
    dataset_dir = manifest_path.parent.resolve()
    if dataset_dir not in [shard_path.parent, *shard_path.parents]:
        raise HTTPException(status_code=403, detail="Shard path is outside dataset workspace")
    if not shard_path.exists():
        raise HTTPException(status_code=404, detail="Shard file not found")

    return FileResponse(
        shard_path,
        media_type="application/x-tar",
        filename=shard.get("file") or shard_path.name,
    )

@app.post("/api/upload/shelby/client-complete")
def complete_client_upload(req: ClientUploadCompleteRequest, request: Request):
    wallet = require_wallet(request)
    manifest_path = find_manifest_path(req.dataset_id, wallet)
    if not manifest_path:
        raise HTTPException(status_code=404, detail="Dataset not found")

    manifest = ensure_manifest_integrity(json.loads(manifest_path.read_text()))
    uploaded_by_index = {shard.index: shard.blob_name for shard in req.shards}
    missing = [
        shard.get("index")
        for shard in manifest.get("shards", [])
        if shard.get("index") not in uploaded_by_index
    ]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing uploaded shards: {missing}")

    set_upload_prefix(manifest_path, req.upload_prefix)
    uploaded_manifest = copy.deepcopy(manifest)
    for shard in uploaded_manifest.get("shards", []):
        shard["blob_name"] = uploaded_by_index[shard["index"]]
        set_shard_status(manifest_path, shard, "verified")

    uploaded_path = manifest_path.parent / "manifest.uploaded.json"
    uploaded_path.write_text(json.dumps(uploaded_manifest, indent=2))
    return {
        "status": "done",
        "dataset_id": req.dataset_id,
        "uploaded_manifest": str(uploaded_path),
        "uploaded": len(uploaded_manifest.get("shards", [])),
    }

@app.get("/api/datasets/{dataset_id}/preview")
def preview_dataset(dataset_id: str, request: Request, rows: int = 10):
    wallet = require_wallet(request)
    for m in find_manifests(wallet):
        if m["id"] == dataset_id:
            manifest = json.loads(Path(m["path"]).read_text())
            shards = manifest.get("shards", [])
            if not shards:
                return {"samples": []}
            shard = shards[0]
            local_path = Path(shard.get("local_path", ""))
            if not local_path.exists():
                return {"samples": [], "note": "Local shard not found"}
            import tarfile, csv, io
            samples = []
            with tarfile.open(local_path, "r") as tar:
                try:
                    labels_file = tar.extractfile("labels.csv")
                    if labels_file:
                        content = labels_file.read().decode("utf-8")
                        reader = csv.DictReader(io.StringIO(content))
                        for i, row in enumerate(reader):
                            if i >= rows:
                                break
                            samples.append(row)
                except Exception as e:
                    return {"samples": [], "error": str(e)}
            return {"samples": samples, "shard": shard["file"]}
    raise HTTPException(status_code=404, detail="Dataset not found")

class ShardRequest(BaseModel):
    dataset_dir: str
    output_dir: str
    shard_size: int = 1000
    dataset_name: str = "mnist-demo"
    format: str = "image-tar"  # image-tar | text-jsonl | parquet | audio-tar

class UploadRequest(BaseModel):
    dataset_id: str
    expiration: str = "in 7 days"

class BenchmarkRequest(BaseModel):
    dataset_id: str
    modes: list[str] = ["local", "shelby_cold", "shelby_cached"]
    batch_size: int = 32
    batches: int = 50
    max_shards: int = 5

@app.post("/api/upload/shard")
def shard_dataset(req: ShardRequest, background_tasks: BackgroundTasks, request: Request):
    wallet = require_wallet(request)
    job_id = str(uuid.uuid4())
    runs[job_id] = {"status": "running", "step": "sharding", "job_id": job_id}
    output_dir = scoped_output_dir(req.output_dir, wallet)

    def _shard():
        try:
            fmt = req.format or "image-tar"
            if fmt == "image-tar":
                from shelbytrain.sharder import create_image_shards
                manifest = create_image_shards(
                    dataset_dir=req.dataset_dir,
                    output_dir=output_dir,
                    shard_size=req.shard_size,
                    dataset_name=req.dataset_name,
                )
            elif fmt == "text-jsonl":
                from shelbytrain.sharder import create_text_shards
                manifest = create_text_shards(
                    jsonl_path=req.dataset_dir,
                    output_dir=output_dir,
                    shard_size=req.shard_size,
                    dataset_name=req.dataset_name,
                )
            elif fmt == "parquet":
                from shelbytrain.sharder import create_parquet_shards
                manifest = create_parquet_shards(
                    parquet_path=req.dataset_dir,
                    output_dir=output_dir,
                    shard_size=req.shard_size,
                    dataset_name=req.dataset_name,
                )
            elif fmt == "audio-tar":
                from shelbytrain.sharder import create_audio_shards
                manifest = create_audio_shards(
                    dataset_dir=req.dataset_dir,
                    output_dir=output_dir,
                    shard_size=req.shard_size,
                    dataset_name=req.dataset_name,
                )
            else:
                raise ValueError(f"Unknown format: {fmt}")
            manifest_path = Path(output_dir) / "manifest.json"
            load_state(manifest_path, manifest)
            runs[job_id] = {
                "status": "done",
                "step": "sharded",
                "job_id": job_id,
                "manifest": manifest,
                "shard_count": len(manifest["shards"]),
                "dataset_id": Path(output_dir).name,
            }
        except Exception as e:
            runs[job_id] = {"status": "error", "error": str(e), "job_id": job_id}

    background_tasks.add_task(_shard)
    return {"job_id": job_id, "status": "running"}

@app.post("/api/upload/shelby")
def upload_to_shelby(req: UploadRequest, background_tasks: BackgroundTasks, request: Request):
    wallet = require_wallet(request)
    job_id = str(uuid.uuid4())
    runs[job_id] = {"status": "running", "step": "uploading", "job_id": job_id,
                    "uploaded": 0, "total": 0, "resume": False}

    def _upload():
        upload_dataset_job(req, job_id, resume=False, wallet=wallet)

    background_tasks.add_task(_upload)
    return {"job_id": job_id, "status": "running"}

@app.post("/api/upload/shelby/resume")
def resume_upload_to_shelby(req: UploadRequest, background_tasks: BackgroundTasks, request: Request):
    wallet = require_wallet(request)
    job_id = str(uuid.uuid4())
    runs[job_id] = {"status": "running", "step": "resuming", "job_id": job_id,
                    "uploaded": 0, "total": 0, "resume": True}

    def _resume():
        upload_dataset_job(req, job_id, resume=True, wallet=wallet)

    background_tasks.add_task(_resume)
    return {"job_id": job_id, "status": "running"}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in runs:
        raise HTTPException(status_code=404, detail="Job not found")
    return runs[job_id]

@app.post("/api/benchmark/run")
def run_benchmark(req: BenchmarkRequest, background_tasks: BackgroundTasks, request: Request):
    wallet = require_wallet(request)
    run_id = str(uuid.uuid4())
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    runs[run_id] = {
        "status": "running",
        "run_id": run_id,
        "dataset_id": req.dataset_id,
        "started_at": started_at,
        "results": {},
        "errors": {},
        "current_mode": None,
        "requested_modes": req.modes,
    }

    def _benchmark():
        try:
            from shelbytrain.dataset import load_dataset
            from shelbytrain.benchmark import benchmark_loader

            manifest_path = None
            uploaded_manifest_path = None
            dataset_name = req.dataset_id
            cache_dir = str(wallet_cache_dir(wallet))
            for m in find_manifests(wallet):
                if m["id"] == req.dataset_id:
                    manifest_path = m["path"]
                    uploaded_manifest_path = m.get("uploaded_path")
                    dataset_name = m.get("name", req.dataset_id)
                    break

            if not manifest_path:
                runs[run_id]["status"] = "error"
                runs[run_id]["error"] = "Dataset not found"
                completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                record_benchmark_history({
                    "run_id": run_id,
                    "dataset_id": req.dataset_id,
                    "dataset_name": req.dataset_id,
                    "status": "error",
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "config": model_payload(req),
                    "results": {},
                    "errors": {"dataset": "Dataset not found"},
                    "speedups": {},
                }, wallet)
                return

            shelby_modes = [mode for mode in req.modes if mode.startswith("shelby_")]
            if shelby_modes and not uploaded_manifest_path:
                errors = {
                    mode: "Dataset does not have manifest.uploaded.json"
                    for mode in shelby_modes
                }
                runs[run_id]["status"] = "error"
                runs[run_id]["error"] = (
                    "Shelby benchmark modes require this dataset to be uploaded first. "
                    "Run Upload -> Upload to Shelby, then benchmark again."
                )
                runs[run_id]["errors"] = errors
                completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                record_benchmark_history({
                    "run_id": run_id,
                    "dataset_id": req.dataset_id,
                    "dataset_name": dataset_name,
                    "status": "error",
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "config": model_payload(req),
                    "results": {},
                    "errors": errors,
                    "speedups": {},
                }, wallet)
                return

            if shelby_modes and uploaded_manifest_path:
                unavailable = check_uploaded_shards(uploaded_manifest_path, req.max_shards, wallet)
                if unavailable:
                    message = (
                        "Shelby benchmark modes require uploaded shards to be readable. "
                        "The current manifest.uploaded.json is stale or the Shelby upload is not finalized. "
                        "Run Upload -> Upload to Shelby again after fixing the Shelby RPC/CLI upload error."
                    )
                    runs[run_id]["status"] = "error"
                    runs[run_id]["error"] = message
                    detail = "; ".join(unavailable[:3])
                    errors = {mode: compact_error(detail, 700) for mode in shelby_modes}
                    runs[run_id]["errors"] = errors
                    completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    record_benchmark_history({
                        "run_id": run_id,
                        "dataset_id": req.dataset_id,
                        "dataset_name": dataset_name,
                        "status": "error",
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "config": model_payload(req),
                        "results": {},
                        "errors": errors,
                        "error": message,
                        "speedups": {},
                    }, wallet)
                    return

            results = {}
            mode_errors = {}

            if "local" in req.modes:
                runs[run_id]["current_mode"] = "local"
                try:
                    init_start = time.perf_counter()
                    dataset = load_dataset(
                        manifest_path,
                        client=None,
                        max_shards=req.max_shards,
                    )
                    init_sec = time.perf_counter() - init_start
                    result = benchmark_loader(dataset, batch_size=req.batch_size, batches=req.batches)
                    result = attach_dataset_metrics(result, dataset, init_sec)
                    results["local"] = result
                    runs[run_id]["results"]["local"] = result
                except Exception as e:
                    message = compact_error(str(e))
                    mode_errors["local"] = message
                    runs[run_id]["errors"]["local"] = message

            if "shelby_cold" in req.modes and uploaded_manifest_path:
                runs[run_id]["current_mode"] = "shelby_cold"
                try:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    client = get_client(wallet)
                    init_start = time.perf_counter()
                    dataset = load_dataset(
                        uploaded_manifest_path,
                        client=client,
                        cache_dir=cache_dir,
                        max_shards=req.max_shards,
                    )
                    init_sec = time.perf_counter() - init_start
                    result = benchmark_loader(dataset, batch_size=req.batch_size, batches=req.batches)
                    result = attach_dataset_metrics(result, dataset, init_sec)
                    mark_cached_shards(uploaded_manifest_path, req.max_shards, wallet)
                    results["shelby_cold"] = result
                    runs[run_id]["results"]["shelby_cold"] = result
                except Exception as e:
                    message = compact_error(str(e))
                    mode_errors["shelby_cold"] = message
                    runs[run_id]["errors"]["shelby_cold"] = message

            if "shelby_cached" in req.modes and uploaded_manifest_path:
                runs[run_id]["current_mode"] = "shelby_cached"
                try:
                    client = get_client(wallet)
                    init_start = time.perf_counter()
                    dataset = load_dataset(
                        uploaded_manifest_path,
                        client=client,
                        cache_dir=cache_dir,
                        max_shards=req.max_shards,
                    )
                    init_sec = time.perf_counter() - init_start
                    result = benchmark_loader(dataset, batch_size=req.batch_size, batches=req.batches)
                    result = attach_dataset_metrics(result, dataset, init_sec)
                    mark_cached_shards(uploaded_manifest_path, req.max_shards, wallet)
                    results["shelby_cached"] = result
                    runs[run_id]["results"]["shelby_cached"] = result
                except Exception as e:
                    message = compact_error(str(e))
                    mode_errors["shelby_cached"] = message
                    runs[run_id]["errors"]["shelby_cached"] = message

            out_path = wallet_result_path(wallet, run_id)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(results, indent=2))
            completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            history_entry = {
                "run_id": run_id,
                "dataset_id": req.dataset_id,
                "dataset_name": dataset_name,
                "status": "error" if mode_errors else "done",
                "started_at": started_at,
                "completed_at": completed_at,
                "config": model_payload(req),
                "results": results,
                "errors": mode_errors,
                "speedups": benchmark_speedup(results),
                "results_file": str(out_path),
            }
            record_benchmark_history(history_entry, wallet)
            if mode_errors:
                runs[run_id].update({
                    "status": "error",
                    "current_mode": None,
                    "error": "Some benchmark modes failed",
                    "results_file": str(out_path),
                    "completed_at": completed_at,
                })
            else:
                runs[run_id].update({
                    "status": "done",
                    "current_mode": None,
                    "results_file": str(out_path),
                    "completed_at": completed_at,
                })

        except Exception as e:
            runs[run_id]["status"] = "error"
            runs[run_id]["error"] = compact_error(str(e))
            runs[run_id]["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            record_benchmark_history({
                "run_id": run_id,
                "dataset_id": req.dataset_id,
                "dataset_name": req.dataset_id,
                "status": "error",
                "started_at": started_at,
                "completed_at": runs[run_id]["completed_at"],
                "config": model_payload(req),
                "results": runs[run_id].get("results", {}),
                "errors": runs[run_id].get("errors", {}),
                "error": runs[run_id]["error"],
                "speedups": {},
            }, wallet)

    background_tasks.add_task(_benchmark)
    return {"run_id": run_id, "status": "running"}

@app.get("/api/benchmark/results/all")
def all_results(request: Request):
    wallet = require_wallet(request)
    history = load_benchmark_history(wallet)
    if history:
        return {
            "results": [
                {
                    "file": item.get("results_file"),
                    "run_id": item.get("run_id"),
                    "dataset_id": item.get("dataset_id"),
                    "dataset_name": item.get("dataset_name"),
                    "status": item.get("status"),
                    "created_at": item.get("completed_at") or item.get("started_at"),
                    "data": item.get("results", {}),
                    "errors": item.get("errors", {}),
                    "speedups": item.get("speedups", {}),
                }
                for item in history
            ],
            "history": history,
        }
    if wallet:
        return {"results": [], "history": []}

    results = []
    search_root = wallet_workspace(wallet) if wallet else Path(".")
    for p in search_root.glob("benchmark-results-*.json"):
        try:
            data = json.loads(p.read_text())
            results.append({
                "file": p.name,
                "run_id": p.stem.replace("benchmark-results-", ""),
                "created_at": p.stat().st_mtime,
                "data": data,
            })
        except Exception:
            continue
    results = sorted(results, key=lambda x: x.get("created_at", 0), reverse=True)
    canonical = Path("benchmark-results.json")
    if canonical.exists():
        try:
            results.insert(0, {"file": "benchmark-results.json", "run_id": "canonical",
                                "data": json.loads(canonical.read_text())})
        except Exception:
            pass
    return {"results": results}

@app.get("/api/benchmark/history")
def benchmark_history(request: Request):
    return {"history": load_benchmark_history(require_wallet(request))}

@app.get("/api/dashboard/pipeline")
def dashboard_pipeline(request: Request):
    return pipeline_summary(require_wallet(request))

@app.get("/api/benchmark/{run_id}")
def get_benchmark(run_id: str):
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return runs[run_id]

def cache_stats_for_wallet(wallet: str | None = None):
    cache_dir = wallet_cache_dir(wallet)
    if not cache_dir.exists():
        return {"exists": False, "shard_count": 0, "total_bytes": 0, "total_mb": 0.0, "shards": []}
    index = {"shards": {}}
    index_path = cache_dir / "index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text())
        except Exception:
            index = {"shards": {}}

    shards = []
    total_bytes = 0
    for f in cache_dir.iterdir():
        if f.suffix == ".tar":
            size = f.stat().st_size
            total_bytes += size
            metadata = index.get("shards", {}).get(f.name, {})
            shards.append({
                "key": f.name,
                "size_bytes": size,
                "size_mb": round(size / 1024 / 1024, 2),
                "modified": f.stat().st_mtime,
                "blob_name": metadata.get("blob_name"),
                "sha256": metadata.get("sha256"),
                "valid": metadata.get("valid", False),
                "cache_hits": metadata.get("cache_hits", 0),
                "cache_misses": metadata.get("cache_misses", 0),
                "downloads": metadata.get("downloads", 0),
                "download_sec": metadata.get("download_sec", 0),
                "extract_sec": metadata.get("extract_sec", 0),
                "last_accessed": metadata.get("last_accessed", f.stat().st_mtime),
                "errors": metadata.get("errors", []),
            })
    return {
        "exists": True,
        "shard_count": len(shards),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1024 / 1024, 2),
        "shards": sorted(shards, key=lambda x: x["last_accessed"], reverse=True),
    }

@app.get("/api/cache/stats")
def cache_stats(request: Request):
    return cache_stats_for_wallet(require_wallet(request))

@app.delete("/api/cache/evict/{shard_key}")
def evict_shard(shard_key: str, request: Request):
    path = wallet_cache_dir(require_wallet(request)) / shard_key
    if not path.exists():
        raise HTTPException(status_code=404, detail="Shard not found in cache")
    path.unlink()
    index_path = path.parent / "index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text())
            index.get("shards", {}).pop(shard_key, None)
            index_path.write_text(json.dumps(index, indent=2, sort_keys=True))
        except Exception:
            pass
    return {"evicted": shard_key}

@app.delete("/api/cache/clear")
def clear_cache(request: Request):
    cache_dir = wallet_cache_dir(require_wallet(request))
    if cache_dir.exists():
        count = len(list(cache_dir.glob("*.tar")))
        shutil.rmtree(cache_dir)
        cache_dir.mkdir()
        return {"cleared": True, "shards_removed": count}
    return {"cleared": False, "shards_removed": 0}


# ── File Upload ───────────────────────────────────────────────────────────────

from fastapi import UploadFile, File, Form

IMAGE_UPLOAD_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
TEXT_UPLOAD_EXTS = {".txt", ".md", ".jsonl", ".json", ".csv", ".pdf", ".docx"}

def safe_upload_name(name: str) -> str:
    stem = Path(name).stem or "upload"
    suffix = Path(name).suffix.lower()
    safe_stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._-") or "upload"
    return f"{safe_stem}{suffix}"

def text_rows_from_upload(filename: str, content: bytes, text_field: str, label_field: str) -> list[dict[str, Any]]:
    ext = Path(filename).suffix.lower()

    if ext in (".txt", ".md"):
        lines = content.decode("utf-8", errors="ignore").splitlines()
        return [
            {text_field: line.strip(), label_field: -1, "source": filename}
            for line in lines
            if line.strip()
        ]

    if ext in (".jsonl", ".json"):
        rows = []
        for line in content.decode("utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    rows.append({text_field: json.dumps(value), label_field: -1, "source": filename})
            except json.JSONDecodeError:
                rows.append({text_field: line, label_field: -1, "source": filename})
        return rows

    if ext == ".csv":
        import csv as _csv
        import io
        reader = _csv.DictReader(io.StringIO(content.decode("utf-8", errors="ignore")))
        return list(reader)

    if ext == ".pdf":
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        rows = []
        for idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                rows.append({text_field: text, label_field: -1, "source": filename, "page": idx + 1})
        return rows

    if ext == ".docx":
        import zipfile
        import xml.etree.ElementTree as ET
        import io
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        rows = []
        for para in root.findall(".//w:p", ns):
            text = "".join(node.text or "" for node in para.findall(".//w:t", ns)).strip()
            if text:
                rows.append({text_field: text, label_field: -1, "source": filename})
        return rows

    raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

def upload_response(
    *,
    status: str,
    fmt: str,
    safe_name: str,
    dataset_dir: Path,
    wallet: str,
    shard_size: int,
    samples: int,
):
    return {
        "status": status,
        "format": fmt,
        "dataset_name": safe_name,
        "dataset_dir": str(dataset_dir),
        "output_dir": str(wallet_data_root(wallet) / f"shelbytrain_{safe_name}"),
        "shard_size": shard_size,
        "samples": samples,
    }

@app.post("/api/upload/file")
async def upload_file(request: Request,
    file: UploadFile = File(...),
    dataset_name: str = Form(...),
    text_field: str = Form(default="text"),
    label_field: str = Form(default="label"),
):
    """Accept a single raw file upload from the browser and save it ready for sharding."""
    return await upload_files(
        request=request,
        files=[file],
        dataset_name=dataset_name,
        text_field=text_field,
        label_field=label_field,
    )

@app.post("/api/upload/files")
async def upload_files(request: Request,
    files: list[UploadFile] = File(...),
    dataset_name: str = Form(...),
    text_field: str = Form(default="text"),
    label_field: str = Form(default="label"),
):
    """Accept browser files and save them as an image or text dataset ready for sharding."""
    wallet = require_wallet(request)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    uploads_dir = wallet_uploads_root(wallet)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = dataset_name.replace(" ", "_").replace("/", "_")
    out_dir = uploads_dir / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)

    uploads = []
    for file in files:
        filename = file.filename or "upload"
        content = await file.read()
        uploads.append((filename, Path(filename).suffix.lower(), content))

    image_uploads = [item for item in uploads if item[1] in IMAGE_UPLOAD_EXTS]
    text_uploads = [item for item in uploads if item[1] in TEXT_UPLOAD_EXTS]
    unsupported = [item[1] or "(none)" for item in uploads if item[1] not in IMAGE_UPLOAD_EXTS | TEXT_UPLOAD_EXTS]

    if unsupported:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type(s): {', '.join(sorted(set(unsupported)))}. "
                "Supported: .png, .jpg, .jpeg, .webp, .bmp, .gif, .txt, .md, .jsonl, .json, .csv, .pdf, .docx"
            ),
        )

    if image_uploads and text_uploads:
        raise HTTPException(status_code=400, detail="Upload either images or text/document files, not both.")

    if image_uploads:
        import csv as _csv
        images_dir = out_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_path = out_dir / "labels.csv"
        seen: set[str] = set()
        rows = []
        for idx, (filename, _ext, content) in enumerate(image_uploads):
            safe_file = safe_upload_name(filename)
            if safe_file in seen:
                safe_file = f"{Path(safe_file).stem}_{idx}{Path(safe_file).suffix}"
            seen.add(safe_file)
            (images_dir / safe_file).write_bytes(content)
            rows.append({"filename": safe_file, "label": -1})

        with labels_path.open("w", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=["filename", "label"])
            writer.writeheader()
            writer.writerows(rows)

        return upload_response(
            status="ok",
            fmt="image-tar",
            safe_name=safe_name,
            dataset_dir=out_dir,
            wallet=wallet,
            shard_size=1000,
            samples=len(rows),
        )

    rows = []
    for filename, _ext, content in text_uploads:
        rows.extend(text_rows_from_upload(filename, content, text_field, label_field))
    if not rows:
        raise HTTPException(status_code=400, detail="No text could be extracted from the uploaded file(s).")

    jsonl_path = out_dir / "data.jsonl"
    with jsonl_path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    return upload_response(
        status="ok",
        fmt="text-jsonl",
        safe_name=safe_name,
        dataset_dir=jsonl_path,
        wallet=wallet,
        shard_size=10000,
        samples=len(rows),
    )


@app.get("/api/datasets/{dataset_id}/manifest")
def get_manifest(dataset_id: str, request: Request):
    """Return the uploaded manifest content for sharing."""
    wallet = require_wallet(request)
    for m in find_manifests(wallet):
        if m["id"] == dataset_id:
            uploaded_path = m.get("uploaded_path")
            local_path = m.get("path")

            if uploaded_path and Path(uploaded_path).exists():
                manifest = json.loads(Path(uploaded_path).read_text())
                return {
                    "manifest": manifest,
                    "path": uploaded_path,
                    "type": "uploaded",
                }
            elif local_path and Path(local_path).exists():
                manifest = json.loads(Path(local_path).read_text())
                return {
                    "manifest": manifest,
                    "path": local_path,
                    "type": "local",
                }
    raise HTTPException(status_code=404, detail="Dataset not found")


@app.post("/api/datasets/{dataset_id}/reconstruct")
async def reconstruct_dataset(dataset_id: str, request: Request):
    """Download all shards from Shelby and reconstruct the original data file."""
    import tarfile, io, json as _json

    wallet = require_wallet(request)

    # Find manifest
    manifest_data = None
    for m in find_manifests(wallet):
        if m["id"] == dataset_id:
            uploaded_path = m.get("uploaded_path")
            local_path = m.get("path")
            path = uploaded_path if uploaded_path and Path(uploaded_path).exists() else local_path
            if path:
                manifest_data = _json.loads(Path(path).read_text())
            break

    if not manifest_data:
        raise HTTPException(status_code=404, detail="Dataset not found")

    fmt = manifest_data.get("format", "text-jsonl")
    name = manifest_data.get("name", dataset_id)
    shards = manifest_data.get("shards", [])
    if not shards:
        raise HTTPException(status_code=400, detail="Manifest has no shards to reconstruct")

    # Get client
    account = wallet
    from shelbytrain.client import ShelbyHTTPClient
    client = ShelbyHTTPClient(
        account=account,
        api_key=os.getenv("SHELBY_API_KEY"),
        rpc_base_url=os.getenv("SHELBY_RPC_BASE_URL", "https://api.shelbynet.shelby.xyz/shelby"),
    )

    from shelbytrain.cache import ShelbyCache
    cache = ShelbyCache(str(wallet_cache_dir(wallet)))

    # Download and reconstruct
    if fmt == "text-jsonl":
        text_field = manifest_data.get("text_field", "text")
        lines = []
        for shard in shards:
            cached_path = cache.get(shard["blob_name"])
            if not cached_path.exists():
                client.download_blob(shard["blob_name"], str(cached_path))
            with tarfile.open(cached_path, "r") as tar:
                f = tar.extractfile("data.jsonl")
                if f:
                    for line in f.read().decode("utf-8").splitlines():
                        if line.strip():
                            obj = _json.loads(line)
                            text = obj.get(text_field)
                            if text is None:
                                text = obj.get("text")
                            if text is not None:
                                lines.append(str(text))
        content_bytes = "\n".join(lines).encode("utf-8")
        filename = f"{name}.txt"
        media_type = "text/plain"

    elif fmt == "image-tar":
        # Return as combined TAR
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as out_tar:
            for shard in shards:
                cached_path = cache.get(shard["blob_name"])
                if not cached_path.exists():
                    client.download_blob(shard["blob_name"], str(cached_path))
                with tarfile.open(cached_path, "r") as in_tar:
                    for member in in_tar.getmembers():
                        f = in_tar.extractfile(member)
                        if f:
                            out_tar.addfile(member, f)
        content_bytes = buf.getvalue()
        filename = f"{name}.tar.gz"
        media_type = "application/gzip"

    elif fmt == "parquet":
        import pandas as pd
        dfs = []
        for shard in shards:
            cached_path = cache.get(shard["blob_name"])
            if not cached_path.exists():
                client.download_blob(shard["blob_name"], str(cached_path))
            with tarfile.open(cached_path, "r") as tar:
                f = tar.extractfile("data.parquet")
                if f:
                    dfs.append(pd.read_parquet(io.BytesIO(f.read())))
        if dfs:
            import pandas as pd
            combined = pd.concat(dfs, ignore_index=True)
            buf = io.BytesIO()
            combined.to_parquet(buf, index=False)
            content_bytes = buf.getvalue()
        else:
            content_bytes = b""
        filename = f"{name}.parquet"
        media_type = "application/octet-stream"

    else:
        raise HTTPException(status_code=400, detail=f"Reconstruct not supported for format: {fmt}")

    from fastapi.responses import Response
    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@app.post("/api/reconstruct/manifest")
async def reconstruct_from_manifest(
    request: Request,
    manifest_file: UploadFile = File(...),
    shelby_account: str = Form(default=""),
):
    """Reconstruct a dataset from a sent manifest.uploaded.json file."""
    import json as _json
    import tarfile, io
    from fastapi.responses import Response

    wallet = require_wallet(request)
    raw = await manifest_file.read()
    try:
        manifest_data = _json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid manifest JSON: {exc}")

    account = (
        manifest_data.get("shelby_account")
        or manifest_data.get("account")
        or manifest_data.get("owner")
        or shelby_account.strip()
        or wallet
    )
    if not account:
        raise HTTPException(status_code=400, detail="Shelby account is required for this manifest.")

    fmt = manifest_data.get("format", "text-jsonl")
    name = manifest_data.get("name", Path(manifest_file.filename or "dataset").stem)
    shards = manifest_data.get("shards", [])
    if not shards:
        raise HTTPException(status_code=400, detail="Manifest has no shards to reconstruct")

    from shelbytrain.client import ShelbyHTTPClient
    from shelbytrain.cache import ShelbyCache

    client = ShelbyHTTPClient(
        account=account,
        api_key=os.getenv("SHELBY_API_KEY"),
        rpc_base_url=os.getenv("SHELBY_RPC_BASE_URL", "https://api.shelbynet.shelby.xyz/shelby"),
    )
    cache = ShelbyCache(str(wallet_cache_dir(wallet)))

    if fmt == "text-jsonl":
        text_field = manifest_data.get("text_field", "text")
        lines = []
        for shard in shards:
            blob_name = shard.get("blob_name")
            if not blob_name:
                raise HTTPException(status_code=400, detail="Manifest shard is missing blob_name")
            cached_path = cache.get(blob_name)
            if not cached_path.exists():
                client.download_blob(blob_name, str(cached_path))
            with tarfile.open(cached_path, "r") as tar:
                f = tar.extractfile("data.jsonl")
                if f:
                    for line in f.read().decode("utf-8").splitlines():
                        if line.strip():
                            obj = _json.loads(line)
                            text = obj.get(text_field)
                            if text is None:
                                text = obj.get("text")
                            if text is not None:
                                lines.append(str(text))
        content_bytes = "\n".join(lines).encode("utf-8")
        filename = f"{name}.txt"
        media_type = "text/plain"

    elif fmt == "image-tar":
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as out_tar:
            for shard in shards:
                blob_name = shard.get("blob_name")
                if not blob_name:
                    raise HTTPException(status_code=400, detail="Manifest shard is missing blob_name")
                cached_path = cache.get(blob_name)
                if not cached_path.exists():
                    client.download_blob(blob_name, str(cached_path))
                with tarfile.open(cached_path, "r") as in_tar:
                    for member in in_tar.getmembers():
                        f = in_tar.extractfile(member)
                        if f:
                            out_tar.addfile(member, f)
        content_bytes = buf.getvalue()
        filename = f"{name}.tar.gz"
        media_type = "application/gzip"

    elif fmt == "parquet":
        import pandas as pd
        dfs = []
        for shard in shards:
            blob_name = shard.get("blob_name")
            if not blob_name:
                raise HTTPException(status_code=400, detail="Manifest shard is missing blob_name")
            cached_path = cache.get(blob_name)
            if not cached_path.exists():
                client.download_blob(blob_name, str(cached_path))
            with tarfile.open(cached_path, "r") as tar:
                f = tar.extractfile("data.parquet")
                if f:
                    dfs.append(pd.read_parquet(io.BytesIO(f.read())))
        combined = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        buf = io.BytesIO()
        combined.to_parquet(buf, index=False)
        content_bytes = buf.getvalue()
        filename = f"{name}.parquet"
        media_type = "application/octet-stream"

    else:
        raise HTTPException(status_code=400, detail=f"Reconstruct not supported for format: {fmt}")

    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
