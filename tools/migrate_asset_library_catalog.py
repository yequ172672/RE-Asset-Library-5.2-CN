"""Migrate an existing RE Asset Library TSV to path-based catalog categories.

The input file is never changed.  Rows with a blank category or the exact
legacy automatic category for their resource extension receive the directory
containing the resource (for example ``art/model/character/ch0``).  A
non-matching category is treated as a manual classification and is copied
unchanged, including display name, tags, platform and language columns.

This script only rewrites the TSV.  It does not read PAK files, extract game
resources or open a Blender file.  Run ``update_asset_library_blend.py``
after placing the output beside the existing library blend.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import shlex
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.asset.catalog_paths import (  # noqa: E402
    category_for_resource_path,
    migrate_category,
)


CATALOG_HEADER = [
    "File Path",
    "Display Name",
    "Category (Forward Slash Separated)",
    "Tags (Comma Separated)",
    "Platform Extension",
    "Language Extension",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-tsv", required=True, type=Path, help="Existing REAssetCatalog_XXXX.tsv")
    parser.add_argument("--output-tsv", required=True, type=Path, help="Path for the migrated TSV")
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Optional JSON summary; useful for an auditable migration run",
    )
    parser.add_argument(
        "--blend",
        type=Path,
        help="Existing REAssetLibrary_XXXX.blend; prints the Blender update command",
    )
    parser.add_argument(
        "--asset-addon",
        type=Path,
        default=REPO_ROOT,
        help="RE Asset Library add-on directory used by the update command",
    )
    parser.add_argument(
        "--blender",
        default="blender",
        help="Blender executable used in the printed update command",
    )
    return parser.parse_args()


def migrate_catalog(input_path: Path, output_path: Path) -> dict:
    """Write a migrated TSV and return auditable row/category counts."""

    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"input TSV not found: {input_path}")
    if input_path == output_path:
        raise ValueError("output TSV must differ from input TSV; use a staged file and replace it after backup")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    changed_rows = 0
    path_rows = 0
    already_path_rows = 0
    manual_rows = 0
    empty_directory_rows = 0
    categories: set[str] = set()

    with input_path.open("r", encoding="utf-8", newline="") as source, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as destination:
        reader = csv.reader(source, delimiter="\t", quotechar='"')
        writer = csv.writer(destination, delimiter="\t", quotechar='"', lineterminator="\n")
        header = next(reader, None)
        if header is None:
            raise ValueError(f"input TSV is empty: {input_path}")
        writer.writerow(header)

        for row in reader:
            if not row:
                writer.writerow(row)
                continue
            total_rows += 1
            if len(row) < 3:
                writer.writerow(row)
                manual_rows += 1
                continue
            original_category = row[2]
            migrated_category, changed = migrate_category(row[0], original_category)
            if changed:
                changed_rows += 1
                path_rows += 1
                if not category_for_resource_path(row[0]):
                    empty_directory_rows += 1
            elif str(original_category).strip() == category_for_resource_path(row[0]):
                already_path_rows += 1
            elif str(original_category).strip() != "":
                manual_rows += 1
            row[2] = migrated_category
            categories.add(migrated_category.strip())
            writer.writerow(row)

    return {
        "inputTsv": str(input_path),
        "outputTsv": str(output_path),
        "rows": total_rows,
        "changedRows": changed_rows,
        "pathCategoryRows": path_rows,
        "alreadyPathRows": already_path_rows,
        "preservedManualRows": manual_rows,
        "emptyDirectoryRows": empty_directory_rows,
        "nonEmptyCategories": len({category for category in categories if category}),
    }


def update_command(blend_path: Path, asset_addon: Path, blender: str) -> str:
    """Return the command that updates the existing blend in place."""

    update_script = REPO_ROOT / "tools" / "update_asset_library_blend.py"
    parts = [
        blender,
        "--background",
        "--factory-startup",
        "-noaudio",
        "--python",
        str(update_script),
        "--",
        "--asset-addon",
        str(asset_addon.expanduser().resolve()),
        "--blend",
        str(blend_path.expanduser().resolve()),
    ]
    if os.name == "nt":
        # The printed command is intended for PowerShell on the supported
        # Windows development host.  Single-quoted PowerShell strings escape
        # an embedded quote by doubling it, and `&` invokes a quoted exe.
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        return "& " + " ".join(quote(part) for part in parts)
    return shlex.join(str(part) for part in parts)


def main() -> int:
    args = parse_args()
    report = migrate_catalog(args.input_tsv, args.output_tsv)
    if args.blend:
        report["updateBlendCommand"] = update_command(args.blend, args.asset_addon, args.blender)
    if args.report_json:
        report_path = args.report_json.expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report["reportJson"] = str(report_path)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("ASSET_CATALOG_MIGRATION " + json.dumps(report, ensure_ascii=False, sort_keys=True))
    if args.blend:
        print("UPDATE_BLEND_COMMAND " + report["updateBlendCommand"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
