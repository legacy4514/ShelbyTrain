from pathlib import Path
import json
from typing import Any, Dict


def load_manifest(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text())


def save_manifest(manifest: Dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(manifest, indent=2))
