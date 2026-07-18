#!/usr/bin/env python3
r"""
Xona DBD Dataset Optimizer

Creates a new optimized copy of the dataset without modifying the originals.

Default behavior:
- Removes exact duplicate Full_Negative images.
- Removes exact duplicate Full_Positive images while keeping the matching crop
  for each retained full-positive image.
- Excludes cropped positives that do not have a matching full-positive image.
- Does NOT automatically remove near-duplicates.
- Writes manifests explaining every kept/skipped file.

Input:
C:\Users\Justx\OneDrive\Documents\Helios Stuff\Dataset

Output:
C:\Users\Justx\OneDrive\Documents\Helios Stuff\Dataset_Optimized
"""

from __future__ import annotations

import csv
import hashlib
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image, ImageOps
except ImportError:
    raise SystemExit(
        "Pillow is required.\n"
        "Run: py -m pip install pillow\n"
        "Then run this tool again."
    )


DATASET_ROOT = Path(r"C:\Users\Justx\OneDrive\Documents\Helios Stuff\Dataset")
OUTPUT_ROOT = Path(r"C:\Users\Justx\OneDrive\Documents\Helios Stuff\Dataset_Optimized")

FULL_POSITIVE = DATASET_ROOT / "Full_Positive"
CROPPED_POSITIVE = DATASET_ROOT / "Cropped_Positive"
FULL_NEGATIVE = DATASET_ROOT / "Full_Negative"

OUT_FULL_POSITIVE = OUTPUT_ROOT / "Full_Positive"
OUT_CROPPED_POSITIVE = OUTPUT_ROOT / "Cropped_Positive"
OUT_FULL_NEGATIVE = OUTPUT_ROOT / "Full_Negative"
REPORT_DIR = OUTPUT_ROOT / "Optimization_Report"

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class FileInfo:
    path: Path
    stem: str
    sha256: str
    width: int
    height: int
    size_bytes: int


def list_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        [
            p for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ],
        key=lambda p: str(p).lower(),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_image(path: Path) -> FileInfo:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image.load()
        width, height = image.size

    return FileInfo(
        path=path,
        stem=path.stem.lower(),
        sha256=sha256_file(path),
        width=width,
        height=height,
        size_bytes=path.stat().st_size,
    )


def write_csv(path: Path, headers: list[str], rows: Iterable[Iterable[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def clear_output_folders() -> None:
    if OUTPUT_ROOT.exists():
        print(f"Removing previous optimized output:\n{OUTPUT_ROOT}")
        shutil.rmtree(OUTPUT_ROOT)

    for folder in (
        OUT_FULL_POSITIVE,
        OUT_CROPPED_POSITIVE,
        OUT_FULL_NEGATIVE,
        REPORT_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def copy_unique(source: Path, destination_folder: Path) -> Path:
    destination = destination_folder / source.name

    # Prevent accidental filename collisions from subfolders.
    if destination.exists():
        counter = 2
        while True:
            candidate = destination_folder / f"{source.stem}__{counter}{source.suffix}"
            if not candidate.exists():
                destination = candidate
                break
            counter += 1

    shutil.copy2(source, destination)
    return destination


def build_crop_lookup(crop_infos: list[FileInfo]) -> dict[str, list[FileInfo]]:
    lookup: dict[str, list[FileInfo]] = defaultdict(list)
    for info in crop_infos:
        lookup[info.stem].append(info)
    return lookup


def choose_crop(candidates: list[FileInfo]) -> FileInfo:
    # A matching stem should normally have one crop. If multiple exist,
    # choose the largest file as a stable, quality-preserving rule.
    return sorted(
        candidates,
        key=lambda item: (item.size_bytes, item.width * item.height, str(item.path).lower()),
        reverse=True,
    )[0]


def main() -> int:
    print("=" * 76)
    print("Xona DBD Dataset Optimizer")
    print("=" * 76)
    print("Original images will not be changed, moved, renamed, or deleted.")
    print(f"\nInput:\n{DATASET_ROOT}")
    print(f"\nOutput:\n{OUTPUT_ROOT}\n")

    required = [FULL_POSITIVE, CROPPED_POSITIVE, FULL_NEGATIVE]
    missing_folders = [folder for folder in required if not folder.exists()]
    if missing_folders:
        print("ERROR: The following required folders are missing:")
        for folder in missing_folders:
            print(f"  - {folder}")
        return 1

    clear_output_folders()

    categories = {
        "full_positive": list_images(FULL_POSITIVE),
        "cropped_positive": list_images(CROPPED_POSITIVE),
        "full_negative": list_images(FULL_NEGATIVE),
    }

    print("Scanning images...")
    inspected: dict[str, list[FileInfo]] = {}

    for category, paths in categories.items():
        records: list[FileInfo] = []
        print(f"\n{category}: {len(paths)} file(s)")
        for index, path in enumerate(paths, start=1):
            try:
                records.append(inspect_image(path))
            except Exception as exc:
                print(f"WARNING: skipped unreadable image: {path}\n  {exc}")

            if index % 250 == 0 or index == len(paths):
                print(f"  inspected {index}/{len(paths)}")
        inspected[category] = records

    positives = inspected["full_positive"]
    crops = inspected["cropped_positive"]
    negatives = inspected["full_negative"]
    crop_lookup = build_crop_lookup(crops)

    kept_positive_rows = []
    skipped_positive_rows = []
    kept_crop_stems: set[str] = set()

    # Exact-positive deduplication uses the full screenshot hash.
    # The crop matching the retained screenshot is copied with it.
    positive_hash_owner: dict[str, FileInfo] = {}

    print("\nOptimizing paired positives...")
    for positive in positives:
        crop_candidates = crop_lookup.get(positive.stem, [])

        if not crop_candidates:
            skipped_positive_rows.append(
                (
                    "missing_matching_crop",
                    str(positive.path),
                    "",
                    positive.sha256,
                    "",
                )
            )
            continue

        if positive.sha256 in positive_hash_owner:
            owner = positive_hash_owner[positive.sha256]
            skipped_positive_rows.append(
                (
                    "exact_duplicate_full_positive",
                    str(positive.path),
                    str(owner.path),
                    positive.sha256,
                    positive.stem,
                )
            )
            continue

        crop = choose_crop(crop_candidates)
        positive_hash_owner[positive.sha256] = positive

        copied_positive = copy_unique(positive.path, OUT_FULL_POSITIVE)
        copied_crop = copy_unique(crop.path, OUT_CROPPED_POSITIVE)
        kept_crop_stems.add(crop.stem)

        kept_positive_rows.append(
            (
                str(positive.path),
                str(copied_positive),
                positive.sha256,
                str(crop.path),
                str(copied_crop),
                crop.sha256,
                f"{positive.width}x{positive.height}",
                f"{crop.width}x{crop.height}",
            )
        )

    orphan_crop_rows = []
    positive_stems = {item.stem for item in positives}
    for crop in crops:
        if crop.stem not in positive_stems:
            orphan_crop_rows.append(
                (
                    "no_matching_full_positive",
                    str(crop.path),
                    crop.sha256,
                    f"{crop.width}x{crop.height}",
                )
            )
        elif crop.stem not in kept_crop_stems:
            # This includes crops attached only to a removed exact-positive duplicate.
            orphan_crop_rows.append(
                (
                    "not_needed_after_positive_deduplication",
                    str(crop.path),
                    crop.sha256,
                    f"{crop.width}x{crop.height}",
                )
            )

    print("Optimizing negatives...")
    kept_negative_rows = []
    skipped_negative_rows = []
    negative_hash_owner: dict[str, FileInfo] = {}

    for negative in negatives:
        if negative.sha256 in negative_hash_owner:
            owner = negative_hash_owner[negative.sha256]
            skipped_negative_rows.append(
                (
                    "exact_duplicate_full_negative",
                    str(negative.path),
                    str(owner.path),
                    negative.sha256,
                    f"{negative.width}x{negative.height}",
                )
            )
            continue

        negative_hash_owner[negative.sha256] = negative
        copied_negative = copy_unique(negative.path, OUT_FULL_NEGATIVE)
        kept_negative_rows.append(
            (
                str(negative.path),
                str(copied_negative),
                negative.sha256,
                f"{negative.width}x{negative.height}",
            )
        )

    write_csv(
        REPORT_DIR / "kept_positive_pairs.csv",
        [
            "source_full_positive",
            "optimized_full_positive",
            "full_positive_sha256",
            "source_crop",
            "optimized_crop",
            "crop_sha256",
            "full_resolution",
            "crop_resolution",
        ],
        kept_positive_rows,
    )

    write_csv(
        REPORT_DIR / "skipped_full_positives.csv",
        ["reason", "skipped_path", "retained_equivalent", "sha256", "filename_stem"],
        skipped_positive_rows,
    )

    write_csv(
        REPORT_DIR / "excluded_crops.csv",
        ["reason", "crop_path", "sha256", "resolution"],
        orphan_crop_rows,
    )

    write_csv(
        REPORT_DIR / "kept_full_negatives.csv",
        ["source_path", "optimized_path", "sha256", "resolution"],
        kept_negative_rows,
    )

    write_csv(
        REPORT_DIR / "skipped_full_negatives.csv",
        ["reason", "skipped_path", "retained_equivalent", "sha256", "resolution"],
        skipped_negative_rows,
    )

    summary = [
        "Xona DBD Dataset Optimization Summary",
        "=" * 44,
        "",
        f"Input root:  {DATASET_ROOT}",
        f"Output root: {OUTPUT_ROOT}",
        "",
        "ORIGINAL COUNTS",
        f"Full positive:    {len(positives)}",
        f"Cropped positive: {len(crops)}",
        f"Full negative:    {len(negatives)}",
        "",
        "OPTIMIZED COUNTS",
        f"Paired full positives kept: {len(kept_positive_rows)}",
        f"Matching crops kept:        {len(kept_positive_rows)}",
        f"Unique full negatives kept: {len(kept_negative_rows)}",
        "",
        "REMOVED / EXCLUDED FROM OPTIMIZED COPY",
        f"Full positives skipped: {len(skipped_positive_rows)}",
        f"Crops excluded:          {len(orphan_crop_rows)}",
        f"Exact negative copies skipped: {len(skipped_negative_rows)}",
        "",
        "POLICY",
        "- Original dataset was not modified.",
        "- Exact duplicates were removed only from the optimized copy.",
        "- Full-positive/crop pairing was preserved.",
        "- Near-duplicates were intentionally retained.",
        "- Orphan crops were excluded from the optimized copy.",
        "",
        "NEXT STEP",
        "Use Dataset_Optimized for model preparation and evaluation.",
        "Keep the original Dataset folder as the untouched archive.",
    ]

    summary_path = REPORT_DIR / "summary.txt"
    summary_path.write_text("\n".join(summary), encoding="utf-8")

    print("\n" + "=" * 76)
    print("\n".join(summary))
    print("=" * 76)
    print(f"\nDone. Open:\n{OUTPUT_ROOT}")
    print("\nUpload the Optimization_Report folder or its ZIP when finished.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
