# OWOTS / Blender 5.2 acceptance

Validated on the local Blender 5.2.0 LTS build with the adapted Asset Library 0.25.1, Mesh Editor 0.66.1 and Chain Editor 14.0.1. Game archives remained read-only throughout.

## LOD and texture quality

The `ch001_00_00.mesh.260209350` body contains six LODs:

| LOD | Source vertices |
| --- | ---: |
| 0 | 48,909 |
| 1 | 26,342 |
| 2 | 16,643 |
| 3 | 10,437 |
| 4 | 6,048 |
| 5 | 3,366 |

The default import produces LOD0: 22 mesh objects, 48,909 vertices and 63,145 Blender polygons. It does not select the lowest LOD. An all-LOD test produces 111,745 vertices across 129 mesh objects; that combined number must not be presented as a single LOD's geometry.

The initial blurry appearance was caused by using the base TEX files. The main cloth ALBD is 256 x 256 in the base path, but its real PAK entry under `natives/stm/streaming/` is 2048 x 2048. The supplied path list does not enumerate that high-resolution path. Check candidate paths against the PAK hash index rather than treating the list as a complete inventory.

Streaming path construction now handles `stm` / `STM` consistently and does not mistake the unchanged base path for a streaming match. Dependency extraction also uses each dependency's own path when finding its streaming counterpart.

For the body material, 57 streaming counterparts were found among 73 distinct TEX references. Their headers include 2048, 1024, 512 and 256 square textures. Some small generic/null textures have no streaming counterpart and retain their original dimensions. No texture was upscaled to pass the test.

The final live scene uses 18 images at 2048 x 2048, one at 1024 x 1024 and four small generic images at 8 x 8. The main cloth ALBD is explicitly checked at 2048 x 2048 with texture-cache reload forced.

## Automatic asset import

The local library contains 6,250 marked asset placeholders and a 103,048-row resource catalog. Its cache indexes 141,976 effective resource entries across the base, patch and two DLC archives.

The primary agent tested the installed add-ons in the running Blender MCP session, starting a new scene and appending `ch001_00_00.mesh` from the generated library. The add-on automatically extracted the mesh, patch material and texture dependencies into the configured separate extraction directory. The deferred importer produced LOD0 geometry, 317 bones and the 2048 cloth ALBD. The placement object was removed and the callback queue became empty.

Automated checks also exercise two asset appends to catch callback capture and placement-cleanup errors. In this custom Blender build, interactive editor operators invoked from a background append callback can crash Blender; unattended append/dispatch and importer tests are therefore separate. The running desktop session provides the actual combined import acceptance above.

## Materials and physics

- The real MDF 51 variant contains 14 materials and 364 texture bindings. Full and fast readers agree on material names, binding types and paths. Ordinary MDF 51 remains covered by a regression test.
- A second character imported with 569 bones and 85,301 vertices across its LODs. A separate item mesh also imported successfully.
- Chain2 17's real header ends at byte 112 for the tested sample. Its first settings offset is 112; reading the older trailing header fields would consume settings data.
- Live Chain2 import with unknown hashes preserved creates 22 groups, 82 nodes and 10 links without Blender 5.2 Geometry Nodes property errors.
- The body-only skeleton lacks hashes `1399493213` and `4148580869`. Those chains remain as unbound data with warnings when **Import Unknown Hashes** is enabled; they require the matching complete skeleton for correct binding. OWOTS asset imports default to preserving these entries.

Game-engine export behavior, animation fidelity and every model/meshlet in the game have not been exhaustively validated. The supported acceptance here is resource extraction and Blender import of representative real assets.

## Repeatable checks

Use the tools documented in `tools/AGENTS.md`:

- `test_pak_chunk_reader.py` and `validate_owots_pak.py` verify normal and multi-block resource reads, cache/worker agreement and failure propagation.
- `test_owots_formats.py` covers mesh registration, MDF variants and TEX decoding.
- `headless_validate.py --highest-lod-only --load-materials --require-armature --require-weights --require-texture-pattern cloth_top_mat_albd --require-texture-min-size 2048 2048 --strict` verifies geometry, skinning and texture fidelity when supplied the real asset paths and add-on directories.
- The companion Chain Editor `tools/validate_chain2_blender.py` verifies actual chain objects with explicit unknown-hash handling.

Installable ZIPs must be validated after fresh extraction, not only from the source checkouts. Runtime updater directories and TextureCache are excluded; required updater Python modules are retained.

## Official Blender package acceptance (2026-09-08)

The three installable ZIPs were regenerated and extracted into a new isolated
directory, then tested with official Blender 5.2 release build `fbe6228777e7`.
Strict highest-LOD import passed with 22 mesh objects, 48,909 vertices,
63,145 polygons and 317 bones. The cloth ALBD decoded to 2048 x 2048 from
the extracted streaming resources; no prior texture cache was reused.
The report contains no missing-texture warnings, import errors or strict
failures, and Blender exited with code 0.

Local evidence: `_validation/official_package_accept_20260908.json` and
the matching `.log`. Before packaging, runtime Python files in the three
source checkouts were also compared with the installed add-ons and matched.
