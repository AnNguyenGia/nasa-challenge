"""Explicit promotion/rollback via atomic pointer replacement; never unpickle remote files."""
import argparse
import hashlib
import json
import os
from pathlib import Path

def promote(root, version):
    root = Path(root).resolve()
    folder = (root / version).resolve()
    if folder.parent != root:
        raise ValueError("invalid version")
    meta = json.loads((folder / "manifest.json").read_text())
    if not meta.get("approved_by_gate") or meta["version"] != version:
        raise ValueError("quality gate or version mismatch")
    artifact = (root / meta["artifact"]).resolve()
    if not artifact.is_relative_to(folder):
        raise ValueError("invalid artifact path")
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != meta["sha256"]:
        raise ValueError("checksum mismatch")
    temp = root / "current.json.tmp"
    with temp.open("w") as f:
        json.dump(meta, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, root / "current.json")
    directory_fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    print("Promoted", version)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    args = parser.parse_args()
    promote(os.getenv("MODEL_DIR", "models"), args.version)
