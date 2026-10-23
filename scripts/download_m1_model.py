"""Download the pretrained M1 road-damage detector and record its provenance.

Source: Hugging Face dronefreak/rdd2022-yolo26s (YOLO26s fine-tuned on RDD2022, AGPL-3.0).
The weights stay out of git (*.pt is ignored); size + SHA-256 + source are written to
models/README.md so the checkpoint can be verified later.

    python scripts/download_m1_model.py            # download if missing, else re-hash
    python scripts/download_m1_model.py --force    # re-download
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://huggingface.co/dronefreak/rdd2022-yolo26s/resolve/main/best.pt"
MODEL_PAGE = "https://huggingface.co/dronefreak/rdd2022-yolo26s"
DEST = ROOT / "models" / "road-damage-yolo26s.pt"
README = ROOT / "models" / "README.md"
BEGIN = "<!-- m1-attribution:begin -->"
END = "<!-- m1-attribution:end -->"
CHUNK = 1 << 20


def download(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "thniyetna-m1-download"})
    with urllib.request.urlopen(req, timeout=60) as resp, part.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(CHUNK):
            fh.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 1e6:7.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()
    part.replace(dest)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def attribution(size: int, digest: str) -> str:
    return f"""{BEGIN}
## Attribution — road-damage-yolo26s.pt

| Field | Value |
|---|---|
| File | `models/road-damage-yolo26s.pt` (not versioned) |
| Source | {URL} |
| Model page | {MODEL_PAGE} |
| Author | dronefreak (Hugging Face) |
| Architecture | Ultralytics YOLO26s, fine-tuned on RDD2022 (4 classes) |
| License (weights) | AGPL-3.0 |
| Training images | RDD2022, CC BY-SA 4.0 |
| Size | {size} bytes ({size / 1024 / 1024:.2f} MiB) |
| SHA-256 | `{digest}` |
| Recorded | {date.today().isoformat()} by `scripts/download_m1_model.py` |

Citations: Arya et al., *RDD2022: A multi-national image dataset for automatic road damage detection*,
arXiv:2209.08538 (2022); Ultralytics YOLO26. Metrics and limits: `docs/M1_MODEL_CARD.md`.
{END}"""


def write_readme(size: int, digest: str) -> None:
    text = README.read_text(encoding="utf-8")
    block = attribution(size, digest)
    pattern = re.compile(re.escape(BEGIN) + ".*?" + re.escape(END), re.S)
    text = pattern.sub(lambda _: block, text) if pattern.search(text) else text.rstrip() + "\n\n" + block + "\n"
    README.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-download even if the file exists")
    args = ap.parse_args()

    if args.force or not DEST.exists():
        print(f"Downloading {URL}\n  -> {DEST}")
        download(URL, DEST)
    else:
        print(f"{DEST} exists, hashing only (use --force to re-download)")

    size = DEST.stat().st_size
    digest = sha256(DEST)
    print(f"size   : {size} bytes ({size / 1024 / 1024:.2f} MiB)")
    print(f"sha256 : {digest}")
    write_readme(size, digest)
    print(f"recorded in {README.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
