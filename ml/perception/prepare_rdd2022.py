"""Convert RDD2022 Pascal-VOC annotations to a clean YOLO dataset.

Expected input: the extracted RDD2022 directory containing country folders,
JPEG images and XML annotations. Only the four challenge classes are kept:
D00, D10, D20 and D40.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

CLASSES = ["D00", "D10", "D20", "D40"]
CLASS_TO_ID = {name: i for i, name in enumerate(CLASSES)}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def stable_bucket(key: str) -> float:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


COUNTRY_TOKENS = {
    "japan": "Japan",
    "india": "India",
    "czech": "Czech",
    "norway": "Norway",
    "united_states": "United_States",
    "unitedstates": "United_States",
    "usa": "United_States",
    "china": "China",
}


def country_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    lowered = [part.lower().replace("-", "_").replace(" ", "_") for part in rel.parts]
    joined = "/".join(lowered)
    for token, canonical in COUNTRY_TOKENS.items():
        if token in joined:
            return canonical
    return rel.parts[0] if rel.parts else "unknown"


def build_image_index(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            index.setdefault(path.stem, []).append(path)
    return index


def find_image(xml_path: Path, image_index: dict[str, list[Path]]) -> Path | None:
    # Fast path for layouts where image and annotation share a directory.
    for ext in IMAGE_EXTS:
        candidate = xml_path.with_suffix(ext)
        if candidate.exists():
            return candidate
        candidate = xml_path.with_suffix(ext.upper())
        if candidate.exists():
            return candidate
    candidates = image_index.get(xml_path.stem, [])
    if not candidates:
        return None
    # Prefer candidates sharing the most parent-path tokens with the annotation.
    xml_parts = set(xml_path.parts)
    return max(candidates, key=lambda p: len(xml_parts.intersection(p.parts)))


def parse_voc(xml_path: Path):
    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    if size is None:
        return None
    width = float(size.findtext("width", "0"))
    height = float(size.findtext("height", "0"))
    if width <= 0 or height <= 0:
        return None
    labels = []
    for obj in root.findall("object"):
        name = (obj.findtext("name") or "").strip()
        if name not in CLASS_TO_ID:
            continue
        box = obj.find("bndbox")
        if box is None:
            continue
        xmin = max(0.0, float(box.findtext("xmin", "0")))
        ymin = max(0.0, float(box.findtext("ymin", "0")))
        xmax = min(width, float(box.findtext("xmax", "0")))
        ymax = min(height, float(box.findtext("ymax", "0")))
        if xmax <= xmin or ymax <= ymin:
            continue
        xc = ((xmin + xmax) / 2.0) / width
        yc = ((ymin + ymax) / 2.0) / height
        bw = (xmax - xmin) / width
        bh = (ymax - ymin) / height
        labels.append((CLASS_TO_ID[name], xc, yc, bw, bh))
    return labels


def choose_split(key: str, country: str, holdout_country: str | None) -> str:
    if holdout_country and country.lower() == holdout_country.lower():
        return "test"
    b = stable_bucket(key)
    if b < 0.80:
        return "train"
    if b < 0.90:
        return "val"
    return "test"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, type=Path, help="Extracted RDD2022 root")
    ap.add_argument("--out", default=Path("data/processed/rdd2022-yolo"), type=Path)
    ap.add_argument("--holdout-country", default=None, help="Optional domain-generalization test country")
    args = ap.parse_args()

    src = args.src.resolve()
    out = args.out.resolve()
    if not src.exists():
        raise SystemExit(f"Dataset root does not exist: {src}")
    if out.exists():
        shutil.rmtree(out)
    for split in ("train", "val", "test"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = Counter()
    per_class = Counter()
    xml_files = list(src.rglob("*.xml"))
    image_index = build_image_index(src)
    for xml_path in xml_files:
        labels = parse_voc(xml_path)
        if labels is None:
            stats["invalid_xml"] += 1
            continue
        image = find_image(xml_path, image_index)
        if image is None:
            stats["missing_image"] += 1
            continue
        country = country_from_path(xml_path, src)
        key = f"{country}/{image.stem}"
        split = choose_split(key, country, args.holdout_country)
        # Prefix country to prevent filename collisions across national subsets.
        safe_country = "".join(c if c.isalnum() else "_" for c in country)
        dst_stem = f"{safe_country}_{image.stem}"
        dst_image = out / "images" / split / f"{dst_stem}{image.suffix.lower()}"
        dst_label = out / "labels" / split / f"{dst_stem}.txt"
        shutil.copy2(image, dst_image)
        dst_label.write_text(
            "\n".join(f"{c} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}" for c, xc, yc, w, h in labels),
            encoding="utf-8",
        )
        stats[f"images_{split}"] += 1
        stats[f"boxes_{split}"] += len(labels)
        for c, *_ in labels:
            per_class[CLASSES[c]] += 1

    yaml = f"""path: {out.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: D00\n  1: D10\n  2: D20\n  3: D40\n"""
    (out / "dataset.yaml").write_text(yaml, encoding="utf-8")
    report = ["RDD2022 conversion complete", f"XML files scanned: {len(xml_files)}"]
    report += [f"{k}: {v}" for k, v in sorted(stats.items())]
    report += [f"class {k}: {v}" for k, v in sorted(per_class.items())]
    (out / "conversion_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    print(f"Dataset YAML: {out / 'dataset.yaml'}")


if __name__ == "__main__":
    main()
