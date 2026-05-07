from pathlib import Path
import time
from typing import Optional

import requests


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
                print(f"Download failed attempt {attempt}/{self.retries}: {exc}")
                time.sleep(2 * attempt)

        raise RuntimeError(f"Failed to download {blob_name}: {last_error}")
