#!/usr/bin/env python3
"""
Xona DBD Dataset Validator

Scans:
- Full_Positive
- Cropped_Positive
- Full_Negative

Creates a Dataset_Report folder containing:
- summary.txt
- image_inventory.csv
- missing_crops.csv
- orphan_crops.csv
- exact_duplicates.csv
- near_duplicate_candidates.csv
- corrupt_or_unreadable.csv

Nothing is deleted or modified.
"""

from __future__ import annotations

import csv
import hashlib
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable

try:
    from PIL import Image, ImageOps
except ImportError:
    raise SystemExit(
        "Pillow is required.\n"
        "Run: py -m pip install pillow imagehash\n"
        "Then launch this script again."
    )

try:
    import imagehash
except ImportError:
    imagehash = None


ROOT = Path(r"C:\Users\Justx\OneDrive\Documents\Helios Stuff\Dataset")
FULL_POSITIVE = ROOT / "Full_Positive"
CROPPED_POSITIVE = ROOT / "Cropped_Positive"
FULL_NEGATIVE = ROOT / "Full_Negative"
REPORT_DIR = ROOT / "Dataset_Report"

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
NEAR_DUPLICATE_DISTANCE = 3


@dataclass
class ImageRecord:
    category: str
    path: Path
    filename: str
    stem: str
    extension: str
    width: int
    height: int
    mode: str
    file_size: int
    sha256: str
    phash: str


def list_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS],
        key=lambda p: str(p).lower(),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_image(category: str, path: Path) -> ImageRecord:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image.load()
        width, height = image.size
        mode = image.mode
        phash = str(imagehash.phash(image.convert("RGB"))) if imagehash else ""

    return ImageRecord(
        category=category,
        path=path,
        filename=path.name,
        stem=path.stem.lower(),
        extension=path.suffix.lower(),
        width=width,
        height=height,
        mode=mode,
        file_size=path.stat().st_size,
        sha256=sha256_file(path),
        phash=phash,
    )


def write_csv(path: Path, headers: list[str], rows: Iterable[Iterable[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{value} B"


def resolution_summary(records: list[ImageRecord]) -> str:
    if not records:
        return "none"

    counts = Counter((r.width, r.height) for r in records)
    most_common = ", ".join(
        f"{w}x{h} ({count})" for (w, h), count in counts.most_common(5)
    )
    widths = [r.width for r in records]
    heights = [r.height for r in records]
    return (
        f"median {int(median(widths))}x{int(median(heights))}; "
        f"most common: {most_common}"
    )


def find_near_duplicates(records: list[ImageRecord]) -> list[tuple]:
    if imagehash is None:
        return []

    # Compare only inside the same category to avoid expected positive/crop similarity.
    output = []
    by_category: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        if record.phash:
            by_category[record.category].append(record)

    for category, items in by_category.items():
        hashes = [(record, imagehash.hex_to_hash(record.phash)) for record in items]

        # Dataset is small enough for pairwise comparison.
        for i in range(len(hashes)):
            record_a, hash_a = hashes[i]
            for j in range(i + 1, len(hashes)):
                record_b, hash_b = hashes[j]

                # Exact byte duplicates are reported separately.
                if record_a.sha256 == record_b.sha256:
                    continue

                distance = hash_a - hash_b
                if distance <= NEAR_DUPLICATE_DISTANCE:
                    output.append(
                        (
                            category,
                            distance,
                            str(record_a.path),
                            str(record_b.path),
                            f"{record_a.width}x{record_a.height}",
                            f"{record_b.width}x{record_b.height}",
                        )
                    )

    return sorted(output, key=lambda row: (row[0], row[1], row[2], row[3]))


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    folders = {
        "full_positive": FULL_POSITIVE,
        "cropped_positive": CROPPED_POSITIVE,
        "full_negative": FULL_NEGATIVE,
    }

    print("=" * 70)
    print("Xona DBD Dataset Validator")
    print("=" * 70)
    print(f"Dataset root: {ROOT}")
    print("Nothing will be deleted or modified.\n")

    all_records: list[ImageRecord] = []
    corrupt_rows: list[tuple[str, str, str]] = []

    for category, folder in folders.items():
        paths = list_images(folder)
        print(f"{category}: found {len(paths)} image(s)")

        for number, path in enumerate(paths, start=1):
            try:
                record = inspect_image(category, path)
                all_records.append(record)
            except Exception as exc:
                corrupt_rows.append((category, str(path), repr(exc)))

            if number % 250 == 0 or number == len(paths):
                print(f"  checked {number}/{len(paths)}")

    records_by_category = {
        category: [r for r in all_records if r.category == category]
        for category in folders
    }

    full_positive_stems = {r.stem for r in records_by_category["full_positive"]}
    cropped_positive_stems = {r.stem for r in records_by_category["cropped_positive"]}

    missing_crop_stems = sorted(full_positive_stems - cropped_positive_stems)
    orphan_crop_stems = sorted(cropped_positive_stems - full_positive_stems)

    full_positive_by_stem = defaultdict(list)
    crop_by_stem = defaultdict(list)

    for record in records_by_category["full_positive"]:
        full_positive_by_stem[record.stem].append(record)
    for record in records_by_category["cropped_positive"]:
        crop_by_stem[record.stem].append(record)

    missing_crop_rows = [
        (stem, str(full_positive_by_stem[stem][0].path))
        for stem in missing_crop_stems
    ]
    orphan_crop_rows = [
        (stem, str(crop_by_stem[stem][0].path))
        for stem in orphan_crop_stems
    ]

    exact_groups = defaultdict(list)
    for record in all_records:
        exact_groups[(record.category, record.sha256)].append(record)

    exact_duplicate_rows = []
    for (category, sha256), group in exact_groups.items():
        if len(group) > 1:
            first = str(group[0].path)
            for duplicate in group[1:]:
                exact_duplicate_rows.append(
                    (
                        category,
                        sha256,
                        first,
                        str(duplicate.path),
                        duplicate.file_size,
                    )
                )

    print("\nFinding near-duplicate candidates...")
    if imagehash is None:
        print("imagehash is not installed; near-duplicate scan skipped.")
        near_duplicate_rows = []
    else:
        near_duplicate_rows = find_near_duplicates(all_records)
        print(f"Found {len(near_duplicate_rows)} near-duplicate candidate pair(s).")

    write_csv(
        REPORT_DIR / "image_inventory.csv",
        [
            "category",
            "filename",
            "full_path",
            "width",
            "height",
            "mode",
            "extension",
            "file_size_bytes",
            "sha256",
            "perceptual_hash",
        ],
        [
            (
                r.category,
                r.filename,
                str(r.path),
                r.width,
                r.height,
                r.mode,
                r.extension,
                r.file_size,
                r.sha256,
                r.phash,
            )
            for r in all_records
        ],
    )

    write_csv(
        REPORT_DIR / "missing_crops.csv",
        ["filename_stem", "full_positive_path"],
        missing_crop_rows,
    )

    write_csv(
        REPORT_DIR / "orphan_crops.csv",
        ["filename_stem", "cropped_positive_path"],
        orphan_crop_rows,
    )

    write_csv(
        REPORT_DIR / "exact_duplicates.csv",
        ["category", "sha256", "original_path", "duplicate_path", "file_size_bytes"],
        exact_duplicate_rows,
    )

    write_csv(
        REPORT_DIR / "near_duplicate_candidates.csv",
        [
            "category",
            "phash_distance",
            "image_a",
            "image_b",
            "resolution_a",
            "resolution_b",
        ],
        near_duplicate_rows,
    )

    write_csv(
        REPORT_DIR / "corrupt_or_unreadable.csv",
        ["category", "path", "error"],
        corrupt_rows,
    )

    total_size = sum(r.file_size for r in all_records)

    summary_lines = [
        "Xona DBD Dataset Validation Report",
        "=" * 42,
        "",
        f"Dataset root: {ROOT}",
        "",
        "COUNTS",
        f"Full positive:       {len(records_by_category['full_positive'])}",
        f"Cropped positive:    {len(records_by_category['cropped_positive'])}",
        f"Full negative:       {len(records_by_category['full_negative'])}",
        f"Total readable:      {len(all_records)}",
        f"Unreadable/corrupt:  {len(corrupt_rows)}",
        f"Total readable size: {format_bytes(total_size)}",
        "",
        "PAIRING",
        f"Full positives missing a crop: {len(missing_crop_rows)}",
        f"Crops without a full positive: {len(orphan_crop_rows)}",
        "",
        "DUPLICATES",
        f"Exact duplicate copies:        {len(exact_duplicate_rows)}",
        f"Near-duplicate candidate pairs: {len(near_duplicate_rows)}",
        f"Near-duplicate pHash threshold: {NEAR_DUPLICATE_DISTANCE}",
        "",
        "RESOLUTIONS",
        f"Full positive:    {resolution_summary(records_by_category['full_positive'])}",
        f"Cropped positive: {resolution_summary(records_by_category['cropped_positive'])}",
        f"Full negative:    {resolution_summary(records_by_category['full_negative'])}",
        "",
        "IMPORTANT",
        "- No image was deleted, renamed, moved, resized, or overwritten.",
        "- Near-duplicate results are candidates only; visually review before removing anything.",
        "- Different file extensions are paired by filename stem.",
        "",
        "FILES CREATED",
        "- image_inventory.csv",
        "- missing_crops.csv",
        "- orphan_crops.csv",
        "- exact_duplicates.csv",
        "- near_duplicate_candidates.csv",
        "- corrupt_or_unreadable.csv",
    ]

    summary_path = REPORT_DIR / "summary.txt"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    print("\n" + "=" * 70)
    print("\n".join(summary_lines))
    print("=" * 70)
    print(f"\nReport saved to:\n{REPORT_DIR}")
    print("\nYou can send me the Dataset_Report folder afterward for review.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
