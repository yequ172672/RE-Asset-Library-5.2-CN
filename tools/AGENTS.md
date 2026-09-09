# tools

## Key Files

| Path | Purpose |
| --- | --- |
| `headless_validate.py` | Runs isolated Blender registration, enum, catalog generation, and optional mesh import checks. |
| `validate_localization.py` | Enables all three add-ons twice in isolated Blender, checking Chinese translations, English fallback and unregistration. |
| `package_addons.ps1` | Creates installable Asset/Mesh/Chain ZIPs with development-only files excluded. |
| `build_local_library.py` | Builds a local catalog, placeholder blend, ExtractInfo, and PAK cache without writing user preferences or game files. |
| `migrate_asset_library_catalog.py` | Rewrites an existing catalog's automatic categories to resource-directory paths while preserving manual rows and non-category fields. |
| `update_asset_library_blend.py` | Updates only existing asset objects' catalog IDs from a staged TSV; it does not reimport, extract, or rebuild PAK data. |
| `test_catalog_path_migration.py` | Lightweight pure-Python tests for migration and parent-path rules. |
| `test_blender_catalog_hierarchy.py` | Isolated Blender check for explicit parent catalogs and existing UUID/simple-name preservation. |
| `test_owots_formats.py` | Regression checks for OWOTS mesh mapping, MDF v51 variants, real mesh parsing and 2048px streaming texture quality. |
| `test_pak_chunk_reader.py` | Regression tests for v4.2 PAK chunk offsets, raw/ZSTD blocks, and final-size trimming. |
| `validate_owots_pak.py` | Compares direct, cache-backed and MP-worker reads of a real chunked OWOTS entry. |
| `test_asset_browser_dispatch.py` | Headless Blender append test for PAK extraction and deferred asset import dispatch. |
| `test_reengine_browser.py` | Pure tests for catalog paths/IDs, resource resolution, import handoff and provider rollback. |
| `test_reengine_preview_data.py` | Pure tests for LOD2 fallback, material ranges, base-color TEX selection and RGBA decoding. |
| `test_reengine_gpu_preview.py` | CPU-to-GPU contract and preview lifecycle checks with Blender/GPU stubs. |
| `test_preview_source.py` | Archive priority, read-only byte access, chunk-table reuse and local file invalidation checks. |

## Common Patterns

- For the custom browser static gate, use Blender's bundled Python (NumPy required): `python -m unittest tools.test_reengine_browser tools.test_reengine_preview_data tools.test_preview_source tools.test_catalog_path_migration tools.test_pak_chunk_reader -v` and separately `python tools/test_reengine_gpu_preview.py`. These do not establish real shader output or game-file fidelity; follow `docs/reengine-browser.md` on the game machine.

- Run the validator inside Blender 5.2 with `--background --factory-startup -noaudio`.
- Set `BLENDER_USER_CONFIG` and `BLENDER_USER_SCRIPTS` to a temporary directory before launching Blender.
- Pass add-on paths with `--asset-addon`, `--mesh-addon`, and `--chain-addon`; the validator enables those packages by their real directory names in the isolated preferences, so cross-add-on preference discovery is exercised.
- Unknown mesh extensions are skipped unless `--allow-unsupported-mesh` is explicitly supplied; heuristic imports are reported separately.
- `--strict` fails when the target game is absent from both enums, cross-add-on discovery fails, or a requested mesh import has errors or no vertices.
- Add `--require-armature --require-weights` for character samples; the report then includes armature/bone, vertex-group, weighted/unweighted vertex, maximum weight, and shape-key counts with strict assertions.
- `--highest-lod-only` selects source LOD0, matching the Mesh Editor default; without it the validator imports all LODs. The report includes per-LOD source vertex/polygon counts and strict mode compares imported totals with the selected mode.
- Strict material validation automatically forces texture cache reload; `--reload-cached-textures` can also be supplied explicitly. Conversion errors and bounds failures from importer output are treated as errors.
- The report lists every file-backed image's name, path, width, and height. Pair repeatable `--require-texture-pattern` with `--require-texture-min-size WIDTH HEIGHT` to enforce a real source resolution during strict material validation.
- Run `package_addons.ps1` with explicit source and output paths; it preserves each add-on's canonical internal directory name, excludes generated TextureCache/TEMP/_validation and updater directories, and writes `package_manifest.json` beside the ZIPs.
- Package filenames use the fork's `-5.2-CN.zip` suffix while internal add-on module directories retain `-main` for preference compatibility.
- Run `build_local_library.py` inside Blender with explicit add-on, list, executable, and output paths; it creates an empty extraction root and only indexes the game PAKs.
- `build_local_library.py` also requires explicit mesh/chain add-ons and an extraction directory; it enables add-ons only in the isolated Blender process, never calls `save_userpref`, and validates placeholder paths against the generated catalog.
- `migrate_asset_library_catalog.py` writes to a separate output TSV. Back up the library outside its scan directory before replacing the original, then run the printed PowerShell Blender command.
- `update_asset_library_blend.py` matches TSV rows to the existing whitelist asset objects, refuses missing or extra objects, preserves manual catalog assignments, and writes only `asset_data.catalog_id` before saving.
