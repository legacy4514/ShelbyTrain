from pathlib import Path
import time
from typing import Optional

import requests
from requests import RequestException


def _short_blob(blob_name: str) -> str:
    if len(blob_name) <= 72:
        return blob_name
    return f"{blob_name[:34]}...{blob_name[-34:]}"


def format_request_error(exc: Exception, action: str, blob_name: str) -> str:
    blob = _short_blob(blob_name)
    if isinstance(exc, requests.Timeout):
        return (
            f"Shelby RPC timed out while {action} {blob}. "
            "Check network/Shelby RPC availability and retry."
        )
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status == 404:
            return f"Shelby blob not found while {action} {blob}. Re-upload the dataset."
        return f"Shelby returned HTTP {status} while {action} {blob}."
    if isinstance(exc, RequestException):
        return (
            f"Shelby RPC request failed while {action} {blob}. "
            "Check network/Shelby RPC availability and retry."
        )
    return str(exc)


class ShelbyHTTPClient:
    """Minimal HTTP client for downloading Shelby blobs.

    This is intentionally simple for MVP testing. It can later be replaced
    with a dedicated Shelby Python SDK when available.
    """

    def __init__(
        self,
        account: str,
        rpc_base_url: str = "https://api.shelbynet.shelby.xyz/shelby",
        api_key: Optional[str] = None,
        retries: int = 3,
        timeout: int = 60,
    ):
        if not account:
            raise ValueError("Shelby account address is required")
        self.account = account
        self.rpc_base_url = rpc_base_url.rstrip("/")
        self.api_key = api_key
        self.retries = retries
        self.timeout = timeout

    def blob_url(self, blob_name: str) -> str:
        return f"{self.rpc_base_url}/v1/blobs/{self.account}/{blob_name}"

    def blob_available(self, blob_name: str, expected_size: int | None = None) -> tuple[bool, str | None]:
        """Return whether a blob is readable from Shelby without downloading it."""
        url = self.blob_url(blob_name)
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = requests.head(url, headers=headers, timeout=min(self.timeout, 15))
            if response.status_code != 200:
                if response.status_code == 404:
                    return False, f"Shelby blob not found: {_short_blob(blob_name)}"
                return False, f"Shelby returned HTTP {response.status_code} for {_short_blob(blob_name)}"

            content_length = response.headers.get("content-length")
            if expected_size is not None and content_length and int(content_length) != expected_size:
                return False, (
                    f"size mismatch for {_short_blob(blob_name)}: "
                    f"expected {expected_size}, got {content_length}"
                )

            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, format_request_error(exc, "checking", blob_name)

    def download_blob(self, blob_name: str, out_path: str) -> str:
        url = self.blob_url(blob_name)
        print(f"📥 Downloading {blob_name} from Shelby...")
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                with requests.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=self.timeout,
                ) as response:
                    response.raise_for_status()

                    out = Path(out_path)
                    out.parent.mkdir(parents=True, exist_ok=True)

                    temp = out.with_suffix(out.suffix + ".partial")
                    with temp.open("wb") as f:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)

                    temp.replace(out)
                    return str(out)

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(
                    f"Download failed attempt {attempt}/{self.retries}: "
                    f"{format_request_error(exc, 'downloading', blob_name)}"
                )
                time.sleep(2 * attempt)

        if last_error:
            raise RuntimeError(format_request_error(last_error, "downloading", blob_name))
        raise RuntimeError(f"Failed to download {_short_blob(blob_name)}")
