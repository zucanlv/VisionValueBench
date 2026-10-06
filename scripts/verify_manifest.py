"""Verify release assets and the original material archive using only Python 3."""

from pathlib import Path
import hashlib
import json
import sys


def verify(root, records):
    for record in records:
        path = root / record["file"]
        if not path.is_file():
            raise ValueError(f"Missing file: {path.relative_to(ROOT)}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record["sha256"]:
            raise ValueError(f"Hash mismatch: {path.relative_to(ROOT)}")


ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    try:
        release = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
        materials = json.loads((ROOT / "materials/manifest.json").read_text())
        verify(ROOT, release["files"])
        verify(ROOT / "materials", materials["files"])
    except (OSError, ValueError, KeyError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    print(f"Verified {len(release['files'])} release files and "
          f"{len(materials['files'])} original material hashes.")
