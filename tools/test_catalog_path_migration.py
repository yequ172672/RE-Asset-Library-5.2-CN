"""Lightweight tests for path-based asset catalog migration."""

from __future__ import annotations

import csv
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from modules.asset.catalog_paths import (  # noqa: E402
    EMPTY_CATALOG_UUID,
    catalog_uuid_is_unassigned,
    catalog_paths_with_parents,
    migrate_category,
    should_preserve_catalog_assignment,
)
from tools.migrate_asset_library_catalog import migrate_catalog  # noqa: E402


class CatalogPathMigrationTests(unittest.TestCase):
    def test_empty_and_exact_legacy_categories_migrate(self):
        self.assertEqual(
            migrate_category("art/model/ch0/ch001_00/00.mesh", ""),
            ("art/model/ch0/ch001_00", True),
        )
        self.assertEqual(
            migrate_category("ace/data/file.user", "UserData Files"),
            ("ace/data", True),
        )

    def test_manual_category_does_not_use_suffix_heuristic(self):
        self.assertEqual(
            migrate_category("art/model/ch0/ch001_00/00.mesh", "UserData Files"),
            ("UserData Files", False),
        )
        self.assertEqual(
            migrate_category("art/model/ch0/ch001_00/00.mesh", "Mesh Files"),
            ("Mesh Files", False),
        )

    def test_catalog_assignment_preservation_distinguishes_unknown_and_empty_uuid(self):
        resource = "root_asset.tex"
        self.assertTrue(catalog_uuid_is_unassigned(EMPTY_CATALOG_UUID.upper()))
        self.assertFalse(
            should_preserve_catalog_assignment(
                resource, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "TEX Files", ""
            )
        )
        self.assertTrue(
            should_preserve_catalog_assignment(
                resource,
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                None,
                "art",
            )
        )
        self.assertFalse(
            should_preserve_catalog_assignment(
                resource,
                "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "TEX Files",
                "art",
            )
        )

    def test_parent_paths_are_explicit_and_unique(self):
        self.assertEqual(
            catalog_paths_with_parents(["art/model/character/ch0", "art/model/ground"]),
            [
                "art",
                "art/model",
                "art/model/character",
                "art/model/ground",
                "art/model/character/ch0",
            ],
        )

    def test_migration_preserves_non_category_columns(self):
        header = [
            "File Path",
            "Display Name",
            "Category (Forward Slash Separated)",
            "Tags (Comma Separated)",
            "Platform Extension",
            "Language Extension",
        ]
        rows = [
            ["art/model/ch0/body.mesh", "Body (Steam)", "", "body.mesh", "stm", ""],
            ["art/model/ch0/body.tex", "Body texture", "Keep Me", "body.tex", "", "en"],
        ]
        with tempfile.TemporaryDirectory(prefix="catalog_path_test_") as temp_dir:
            root = Path(temp_dir)
            source = root / "input.tsv"
            target = root / "output.tsv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
                writer.writerow(header)
                writer.writerows(rows)
            report = migrate_catalog(source, target)
            self.assertEqual(report["changedRows"], 1)
            with target.open("r", encoding="utf-8", newline="") as stream:
                output_rows = list(csv.reader(stream, delimiter="\t"))
        self.assertEqual(output_rows[1], [rows[0][0], rows[0][1], "art/model/ch0", rows[0][3], rows[0][4], rows[0][5]])
        self.assertEqual(output_rows[2], rows[1])


if __name__ == "__main__":
    unittest.main()
