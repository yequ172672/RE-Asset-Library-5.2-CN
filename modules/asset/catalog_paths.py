"""Pure helpers for resource-path based asset catalog categories.

The asset add-on stores catalog paths with forward slashes, as required by
Blender's asset catalog format.  Keeping the path and legacy-category rules
here lets the Blender operator and the standalone library migration tool use
the same behavior without importing ``bpy`` from a command-line process.
"""

from __future__ import annotations

from typing import Iterable


EMPTY_CATALOG_UUID = "00000000-0000-0000-0000-000000000000"


# These names mirror the automatic categories historically emitted by
# REToolListFileToREAssetCatalogAndGameInfo.  The comparison is intentionally
# exact: a user category that merely ends in " Files" must remain untouched.
LEGACY_FILE_TYPE_DISPLAY_NAMES = {
    "mesh": "Mesh Files",
    "chain": "Chain Files",
    "chain2": "Chain2 Files",
    "efx": "EFX Files",
    "pfb": "Prefab Files",
    "user": "UserData Files",
    "scn": "Scene Files",
    "fbxskel": "FBXSkel Files",
}

# Mesh-like entries were deliberately left uncategorized by the old
# generator.  Empty categories are also treated as automatic during migration
# so those entries can acquire their resource-directory category.
LEGACY_EMPTY_CATEGORY_EXTENSIONS = {"mesh", "chain", "chain2", "fbxskel"}


def normalize_resource_path(file_path: str) -> str:
    """Return a resource path in Blender's forward-slash form.

    Resource paths are relative game paths.  Empty and ``.`` segments are
    discarded, while ordinary segment spelling and case are retained because
    those are part of the game's path inventory.
    """

    parts = [part for part in str(file_path).replace("\\", "/").split("/") if part not in ("", ".")]
    return "/".join(parts)


def category_for_resource_path(file_path: str) -> str:
    """Return the directory containing ``file_path`` as a catalog path."""

    normalized = normalize_resource_path(file_path)
    if "/" not in normalized:
        return ""
    return normalized.rsplit("/", 1)[0]


def resource_extension(file_path: str) -> str:
    """Return the lower-case resource extension used by the old generator."""

    name = normalize_resource_path(file_path).rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def legacy_auto_category(file_path: str) -> str:
    """Return the exact automatic category for a legacy catalog row."""

    extension = resource_extension(file_path)
    if extension in LEGACY_EMPTY_CATEGORY_EXTENSIONS:
        return ""
    return LEGACY_FILE_TYPE_DISPLAY_NAMES.get(extension, extension.upper() + " Files")


def is_legacy_auto_category(file_path: str, category: str) -> bool:
    """Whether ``category`` is an automatic legacy value for this row.

    Blank categories are automatic by definition.  All other categories must
    equal the extension-specific legacy value exactly; this protects manual
    classifications from broad suffix-based matching.
    """

    current = str(category).strip()
    return current == "" or current == legacy_auto_category(file_path)


def catalog_uuid_is_unassigned(catalog_uuid: object) -> bool:
    """Return whether Blender's catalog UUID represents no assignment."""

    return str(catalog_uuid).strip().lower() in {"", EMPTY_CATALOG_UUID}


def should_preserve_catalog_assignment(
    file_path: str,
    catalog_uuid: object,
    current_category: str | None,
    desired_category: str,
) -> bool:
    """Whether an existing asset catalog assignment is a manual choice.

    ``None`` means the UUID is not present in the adjacent catalog definition
    file.  A non-empty unknown UUID must remain untouched: it can point at a
    catalog definition that is managed outside the staged TSV.  The all-zero
    UUID is Blender's unassigned value and may be migrated.
    """

    if catalog_uuid_is_unassigned(catalog_uuid):
        return False
    if current_category is None:
        return True
    if current_category == desired_category:
        return False
    return not is_legacy_auto_category(file_path, current_category)


def migrate_category(file_path: str, category: str) -> tuple[str, bool]:
    """Return ``(category, changed)`` for a legacy catalog row."""

    if is_legacy_auto_category(file_path, category):
        migrated = category_for_resource_path(file_path)
        return migrated, migrated != str(category)
    return str(category), False


def catalog_paths_with_parents(category_names: Iterable[str]) -> list[str]:
    """Return unique non-empty catalog paths, including every parent path."""

    paths: set[str] = set()
    for raw_name in category_names:
        name = normalize_resource_path(raw_name)
        if not name:
            continue
        segments = name.split("/")
        paths.update("/".join(segments[:index]) for index in range(1, len(segments) + 1))
    return sorted(paths, key=lambda value: (value.count("/"), value))


def catalog_display_name(catalog_path: str) -> str:
    """Return a readable leaf name for a newly-created Blender catalog."""

    return normalize_resource_path(catalog_path).rsplit("/", 1)[-1]
