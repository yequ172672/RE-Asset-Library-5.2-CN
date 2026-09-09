# modules/asset

## Key Files

| Path | Purpose |
| --- | --- |
| `blender_re_asset.py` | Asset-browser path discovery, deferred import dispatch and editor operator status handling |
| `catalog_paths.py` | Pure path-category and legacy automatic-category migration helpers |
| `re_asset_utils.py` | Game metadata, catalog paths and asset-library path helpers |
| `re_asset_operators.py` | Library creation, catalog and asset-browser operators |
| `browser_resources.py` | Catalog index, stable resource IDs and shared extraction/path resolution |
| `native_browser.py` | Loopback tree service, provider-scoped controls and Mesh/Chain2/MDF2 import dispatch |
| `preview_data.py` | Active Mesh Editor parser reuse, LOD selection and base-color RGBA decoding |
| `preview_source.py` | Read-only, patch-prioritized PAK resource access and local fallback; no game-file extraction |
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
- Exercise the real TEX-to-DDS-to-TGA decode path in preview checks; texture lookup and mocked material records alone cannot establish successful decoding. Translation helpers accept the source message positionally so `{message}` remains available as a formatting field.
- HTTP handlers consume catalog data without `bpy`; GPU objects, UI changes and editor operators belong on Blender's main thread. Cancelled or superseded requests must not restore an old preview.
- Preview actions capture metadata only on the main thread and never call the full-import resolver or inherit `forceExtract`. Workers read only Mesh, optional streaming Mesh, MDF and chosen base-color TEX entries into memory; DDS/TGA intermediates are private temporary conversion files, not extracted game resources.
- Publish geometry before materials are decoded. Preview selects a mip near 512 pixels, uses NumPy channel conversion, and shares each texture across material sections. Full imports retain original highest-quality options and extraction behavior.
- CPU preview/texture caches each have a 128 MiB accounting budget; file/PAK/GameInfo identities and refresh invalidate results. Refresh/unregister clear preview caches. Cache payloads are immutable inputs to normalization.
- Extension Browser panels belong in `CHANNELS`, scoped to `EXTENSIONS` and provider `reengine`; `TOOLS` is hidden in this mode. Register operators before the provider and unregister the provider before releasing preview/server state.

## Validation

Use Blender 5.2 in isolated preferences. Run `tools/headless_validate.py` against an extracted OWOTS mesh for the real editor import; asset-browser append tests should verify append-triggered extraction and queue dispatch separately because background Blender cannot safely run the interactive editor operator from an append callback.

- Native browser full-import icons cover MESH, CHAIN2 and MDF2; only MESH has GPU preview. Dispatch through the respective editor operators, preserving Chain2 asset game metadata while finding a matching armature. MDF2 imports editable MDF collections through `re_mdf.importfile`.
