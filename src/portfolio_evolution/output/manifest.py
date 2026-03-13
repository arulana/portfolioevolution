"""Run manifest for reproducibility.

Captures run metadata, config hash, data file hashes, and environment
for audit and replay.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


def create_manifest(
    run_id: str,
    config: dict,
    data_files: list[Path],
    start_time: datetime,
    end_time: datetime | None = None,
) -> dict:
    """Create a run manifest with:

    - run_id
    - timestamp
    - config hash (SHA256 of config dict)
    - data file hashes (SHA256 of each input file)
    - engine version
    - python version
    - random seed
    """
    config_json = json.dumps(config, sort_keys=True)
    config_hash = hashlib.sha256(config_json.encode()).hexdigest()

    data_hashes: dict[str, str] = {}
    for p in data_files:
        path = Path(p)
        if path.exists() and path.is_file():
            data_hashes[str(path)] = _file_hash(path)

    manifest = {
        "run_id": run_id,
        "timestamp": start_time.isoformat(),
        "end_time": end_time.isoformat() if end_time else None,
        "config_hash": config_hash,
        "data_file_hashes": data_hashes,
        "engine_version": config.get("engine_version", "0.1.0"),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "random_seed": config.get("random_seed"),
        "config": config,
    }
    return manifest


def _file_hash(path: Path, block_size: int = 65536) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(block_size):
            h.update(chunk)
    return h.hexdigest()


def save_manifest(manifest: dict, output_dir: Path) -> Path:
    """Save manifest as JSON. Returns path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = manifest.get("run_id", "unknown")
    path = output_dir / f"manifest_{run_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return path
