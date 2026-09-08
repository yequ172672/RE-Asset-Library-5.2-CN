# modules/asset

## Key Files

| Path | Purpose |
| --- | --- |
| `blender_re_asset.py` | Asset-browser path discovery, deferred import dispatch and editor operator status handling |
| `catalog_paths.py` | Pure path-category and legacy automatic-category migration helpers |
| `re_asset_utils.py` | Game metadata, catalog paths and asset-library path helpers |
| `re_asset_operators.py` | Library creation, catalog and asset-browser operators |
| `browser_resources.py` | Catalog index, stable resource IDs and shared extraction/path resolution |
| `native_browser.py` | Loopback tree service, provider-scoped controls and original Mesh import dispatch |
| `preview_data.py` | Active Mesh Editor parser reuse, LOD selection and base-color RGBA decoding |
| `gpu_preview.py` | Asynchronous preview lifecycle, GPU batches and direct texture upload |

## Common Patterns

- `blend_import_post` must only discover the asset, extract missing files and enqueue editor operators. Calling Mesh/Chain operators directly from the post handler can re-enter Blender's append operation.
- `run_in_main_thread` schedules queue work through a Blender timer; queue callbacks return explicit success/failure and cleanup runs after the deferred import attempt.
- Import dispatchers return `True` for `FINISHED` or `RUNNING_MODAL`, and `False` for missing paths, cancelled operators or exceptions. OWOTS chain imports pass `importUnknowns=True`; other games keep the editor default.
- Chunk paths point at the extracted `natives/<platform>` directory. PAK extraction may discover both ordinary and `streaming/` sidecar files.
- New catalog generation derives categories from the resource directory and creates explicit Blender catalog parents. Existing catalog UUIDs and custom simple names are retained by full catalog path.
- Existing-library migration treats only blank categories or an exact extension-specific legacy automatic category as movable; manual categories are preserved.
- Blend migration preserves non-empty catalog UUIDs that are absent from the staged catalog definition, clears legacy automatic assignments when the target resource directory is the catalog root, and uses Blender's all-zero UUID for an unassigned asset.
- `reengine` preview selects LOD2, then LOD1, then LOD0 when a level is missing or empty. This preview-specific rule does not change complete Mesh imports or their quality settings.
- Preview shading only uses basic base color; do not expand it into full MDF rendering. Reuse the active Mesh Editor's parsers and bundled texture conversion rather than duplicating RE format/version tables.
- HTTP handlers consume catalog data without `bpy`; GPU objects, UI changes and editor operators belong on Blender's main thread. Cancelled or superseded requests must not restore an old preview.
- Extension Browser panels belong in `CHANNELS`, scoped to `EXTENSIONS` and provider `reengine`; `TOOLS` is hidden in this mode. Register operators before the provider and unregister the provider before releasing preview/server state.

## Validation

Use Blender 5.2 in isolated preferences. Run `tools/headless_validate.py` against an extracted OWOTS mesh for the real editor import; asset-browser append tests should verify append-triggered extraction and queue dispatch separately because background Blender cannot safely run the interactive editor operator from an append callback.
