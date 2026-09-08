# Repository guide

## Key Files
| File | Purpose |
| --- | --- |
| `__init__.py` | Blender add-on registration, preferences, game selection and asset import dispatch |
| `translations.py` | Blender 5.2 Simplified Chinese translation registry and context-aware UI/report helpers |
| `README.md` | Installation and user documentation |
| `addon_updater.py` | Upstream update implementation |
| `addon_updater_ops.py` | Blender integration for the updater |
| `LICENSE.GPL` | Project license |
| `modules/asset/blender_re_asset.py` | Asset-browser import dispatch and editor operator status handling |
| `modules/asset/native_browser.py` | Custom Blender API v1 `reengine` provider, local catalog service and action routing |
| `docs/reengine-browser.md` | Lightweight preview scope, installation and other-machine acceptance checklist |
| `tools/test_owots_formats.py` | OWOTS mesh, MDF and texture regression checks |
| `tools/test_pak_chunk_reader.py` | PAK v4.2 reader, cache v3 and MP failure regression tests |
| `tools/validate_owots_pak.py` | Direct/cache/MP real PAK comparison and priority report |
| `tools/test_asset_browser_dispatch.py` | Headless append, extraction and deferred import dispatch check |
| `tools/migrate_asset_library_catalog.py` | Existing-library path-category migration without PAK rebuild or extraction |
| `tools/update_asset_library_blend.py` | Existing-blend catalog-ID update that preserves asset objects and metadata |

## Subdirectories
| Directory | Purpose |
| --- | --- |
| `modules` | Asset catalog, PAK extraction, material and resource-reference readers |
| `Resources` | Blender templates, thumbnail resources and initialization/render scripts |
| `compatibility` | Reproducible companion editor patches and pinned upstream bases |
| `tools` | Reproducible Blender validation tooling |
| `docs` | Reproducible Onimusha PAK and format validation notes |

## Dependencies
- Blender 5.2 is the target for the Onimusha: Way of the Sword adaptation.
- RE Mesh Editor imports meshes and materials; RE Chain Editor imports physics chains. Their game enums and format support must match the asset library.
- The optional `reengine` browser requires custom `_remote_asset_browser` API v1; GPU previews additionally require `gpu.texture.from_bytes()`. The ordinary Asset Browser remains available in official Blender.
- Python dependencies used by the add-on include `zstandard` and `requests`; Blender supplies `bpy` and `mathutils`.
- Local reference repositories are siblings, not bundled dependencies: `REE.PAK.Tool` and `REE-Content-Editor` (including `RE-Engine-Lib`).

## Common Patterns
- Use `OWOTS` for Onimusha: Way of the Sword. `ONI2` identifies a different game.
- Keep Chinese UI text in `translations.py`; preserve operator IDs, RNA property names, file extensions and game identifiers in source/data.
- Register both `zh_HANS` and the `zh_CN` compatibility alias through `bpy.app.translations`; use context-aware helpers for dynamic labels and reports.
- Keep GameInfo, asset catalog paths, extraction caches and dependency editor game identifiers consistent.
- Validate PAK decoding through both direct and cached/batch extraction. A readable index does not prove correct resource extraction.
- Shared extension numbers do not guarantee identical layouts: WotS has a distinct MDF 51 variant.

## For AI Agents
- Preserve the user's fork as `origin`; adaptation work is on `feat/onimusha-wots`.
- Treat installed game files as read-only. Put test extracts and generated libraries outside tracked source files; never commit game assets.
- Verify real samples in Blender 5.2, including a skinned mesh, material/texture dependencies and Chain2 when claiming their support. Registration or a nearest-version fallback alone is insufficient.
- Use isolated Blender preferences for automated checks. Coordinate access to the live Blender MCP session through the primary agent.
- Update the relevant AGENTS.md files for structural changes, preserving content enclosed by `<!-- MANUAL -->` markers.
