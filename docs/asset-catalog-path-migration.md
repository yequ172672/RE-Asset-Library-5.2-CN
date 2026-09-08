# Path-based asset catalogs

The asset catalog category for a newly generated library is the resource's
directory, expressed with forward slashes. A resource such as
`art/model/character/ch0/ch001_00/00/ch001_00_00.mesh` is assigned to
`art/model/character/ch0/ch001_00/00`. The file name is not part of the
catalog path. Blender catalog definitions include every parent path, so `art`,
`art/model`, and the intermediate folders are selectable as well.

`tools/migrate_asset_library_catalog.py` performs the same change for an
existing TSV without touching game files. It writes a separate output file and
changes a row only when its old category is blank or exactly matches the
extension-specific automatic category previously emitted by the add-on (for
example `UserData Files` for `.user` or `TEX Files` for `.tex`). A category that
does not match that row's automatic value is treated as manual, even if its
text ends in ` Files`. Display name, tags, platform extension and language
extension columns are copied unchanged.

After a backup outside the library directory, replace the normal TSV with the
staged output and run the command printed by the migration tool. The Blender
update script matches the TSV's whitelist rows to the existing asset objects,
refuses missing or extra objects, creates only the required catalogs and
parents, then changes `asset_data.catalog_id`. Existing UUIDs and custom simple
names are retained by catalog path; a custom catalog currently assigned to an
asset remains assigned unless it is an exact legacy automatic category.

For a pure-Python check:

```powershell
python -m unittest tools.test_catalog_path_migration -v
```

For an isolated Blender catalog check, use Blender 5.2 with temporary user
configuration and output directories:

```powershell
$env:BLENDER_USER_CONFIG = "D:\CODE\re\_validation\blender-catalog-config"
$env:BLENDER_USER_SCRIPTS = "D:\CODE\re\_validation\blender-catalog-scripts"
blender --background --factory-startup -noaudio `
  --python tools/test_blender_catalog_hierarchy.py -- `
  --asset-addon D:\CODE\re\RE-Asset-Library-cn `
  --output-dir D:\CODE\re\_validation\blender-catalog-output
```

The migration and blend update do not rebuild PAK caches, read game archives,
or extract resources.

## Verified OWOTS result and custom-build limitation

The existing OWOTS library was migrated in place after an external backup:
6,250 asset objects, 103,048 TSV rows, and 2,813 catalogs including parents.
The non-category TSV columns remained identical. Catalog paths have no
duplicates and every parent exists. Repeating the update changes zero IDs.

A separate two-object fixture at `_validation/catalog-update-fixture` verified
the edge cases in the Blender 5.2 updater. A legacy automatic `TEX Files`
assignment migrated to a resource-root row was cleared to Blender's all-zero
unassigned UUID, while an unknown non-empty UUID was preserved. The updater
reported one changed ID and one preserved catalog, and both asset tag sets
survived the save and reopen check.

The local custom Blender 5.2 builds `9b2b49a30e1c` and `8658f783eacc` hide the
native Asset Browser source region at 1 x 1 pixels even with factory startup
and Source List enabled. This is independent of the catalog data. The local
official 5.2 release build `fbe6228777e7` displays the source region normally.
In that build, the primary agent expanded
`art/model/character/ch0/ch001_00` and selected its `00` child; the browser
correctly showed only `ch001_00_00.mesh` and `ch001_00_00.chain2`.

The local launcher `_validation/Open_OWOTS_Catalogs.cmd` opens that official
build against the same library in an independent, clean session. It does not
close the existing custom Blender session. Opening the custom work-file copy
in the official build caused a compatibility crash, so this launcher uses
`--library-only` rather than loading that copy. The original session and its
saved backup are retained. This workaround does not claim to patch the custom
Blender executable itself.
