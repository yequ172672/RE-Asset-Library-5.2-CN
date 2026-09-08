# Onimusha: Way of the Sword PAK validation

The installed Steam sample was read from `D:\gametest\steamapps\common\OnimushaWotS` without modifying the game files. The two main archives use PAK version 4.2 and feature `0x28`: encrypted entry tables plus a chunk content table.

| Archive | Entries | Chunk records | Per-entry encryption |
| --- | ---: | ---: | ---: |
| `re_chunk_000.pak` | 133381 | 45491 | 0 |
| `re_chunk_000.pak.patch_001.pak` | 15733 | 4335 | 0 |
| `re_dlc_stm_3932690.pak` | 42 | 0 | 0 |
| `re_dlc_stm_3935640.pak` | 83 | 0 | 0 |

For feature `0x28`, bit 5 means `HasChunkContentTable`. Each chunk record is two little-endian uint32 values. The first is the low offset; the second packs the physical chunk size in bits 10–31 and the high 32-bit offset overflow in bits 0–9:

```text
physicalOffset = offset + ((attributes & 0x3ff) << 32)
chunkSize      = attributes >> 10
```

This differs from the older `REE.PAK.Tool/PakChunks.cs` logic, which infers high bits by accumulating offset decreases. On the installed base PAK, record 7609 resolves to `21,343,806,316` with the per-record overflow, versus `12,753,871,724` with cumulative wrap counting. Record 44369 resolves to `51,782,241,645` versus `43,192,307,053`. Record 45490 resolves to `52,901,295,001` versus `44,311,360,409`. The per-record interpretation is also the layout used by `REE-Content-Editor/RE-Engine-Lib/REE-Lib/Pak/PakFile.cs`.

Chunk entries use the entry offset as a chunk-table index. Full raw blocks are copied directly; smaller blocks are individual Zstandard frames. The concatenated result is trimmed to the entry decompressed size because compressed frames can expand to the block size even when the resource ends earlier.

## Direct, cache and MP comparison

Run this from the asset-library repository. The script uses the bundled `libzstd.dll` when the current Python does not have the `zstandard` package:

```powershell
python tools/validate_owots_pak.py `
  --game-dir D:\gametest\steamapps\common\OnimushaWotS `
  --output-dir D:\temp\owots_pak_validation\pak_entry_validation
```

The selected multi-block chunked sample is:

```text
natives/stm/art/stage/st203/ground/texturetree/st203_ground_n1p0_tree.gtl.251111121
```

The validation run found it in `re_chunk_000.pak`, TOC entry index `536`, pointing at chunk-table index `42583`. It has compressed size `431075`, decompressed size `3429620`, and **7 Zstandard chunks**. The chunk sizes are `27864, 60725, 41718, 45830, 148719, 65677, 40542`; all seven are non-raw blocks. Each Zstandard frame reports 524288 decompressed bytes, so the concatenated frame output is 3670016 bytes and the reader trims it to the declared 3429620 bytes. Every chunk uses overflow `11`; the first physical offset is `47,479,323,680` and the last is `47,479,714,213`. The output starts with the GTL magic `47 54 4c 0a d1 a6 f7 0e` and all three readers produced 3,429,620 bytes with this SHA256:

```text
afb3f4ed57d2c7004ed8db8326bf90794a32818fd77d0e5cb15669d142823c9a
```

Run it with:

```powershell
python tools/validate_owots_pak.py `
  --game-dir D:\gametest\steamapps\common\OnimushaWotS `
  --path natives/stm/art/stage/st203/ground/texturetree/st203_ground_n1p0_tree.gtl.251111121 `
  --output-dir D:\temp\owots_pak_validation\gtl_entry_validation
```

The small chunked sample below is retained as a focused overflow check:

```text
natives/stm/gui/ui_tips/movie/tips_movie_024.mov.1
```

The validation run found it in `re_chunk_000.pak`, TOC entry index `489`, pointing at chunk-table index `45422`. Its compressed size is 62 bytes, decompressed size is 38 bytes, and chunk record `attributes=63500` gives `overflow=12`, physical offset `52,901,271,454` (>4 GiB), and chunk size 62. Direct, cache-backed, and MP-worker outputs were all 38 bytes with this SHA256:

```text
4a1346f7f41df9207332bf5518982359d09e73b5fbecacbdc8dd31a68e6112d0
```

The cache is written as v3 and stores the original chunk index, decompressed size and content-table type. Existing v2 caches are rejected and regenerated.

For a real streaming sidecar check, run the same validator with the base texture and `--check-streaming`:

```powershell
python tools/validate_owots_pak.py `
  --game-dir D:\gametest\steamapps\common\OnimushaWotS `
  --path natives/stm/art/model/character/ch0/ch001_00/00/textures/ch001_00_00_cloth_top_mat_albd.tex.251111100 `
  --check-streaming `
  --output-dir D:\temp\owots_pak_validation\tex_pair_validation
```

The ordinary TEX output was 48,776B with SHA256 `238896270577e12b4b55a5249c00cbce9823141febaf91883119be0742f1bbb4`; its discovered streaming sidecar was 2,801,336B with SHA256 `6c066e134b803225cf0ee5e860328d6e6f648201b7f6f21753ae36825e2f1b18`. Both start with TEX magic `54 45 58 00`. The sidecar was found by hash even though the original OWOTS path list does not contain that streaming path.

## Archive priority

`scanForPakFiles` reports load order from low to high priority:

```text
re_chunk_000.pak
re_chunk_000.pak.patch_001.pak
re_dlc_stm_3932690.pak
re_dlc_stm_3935640.pak
```

Cache creation reverses this list so the first matching hash wins in high-to-low priority order:

```text
re_dlc_stm_3935640.pak
re_dlc_stm_3932690.pak
re_chunk_000.pak.patch_001.pak
re_chunk_000.pak
```

The observed hash overlaps are: base/patch 7209, base/DLC 3932690 13, base/DLC 3935640 0, patch/DLC 3932690 27, patch/DLC 3935640 27, and the two DLC archives 0. This confirms patch and DLC entries are covered by the cache order; the later-sorted DLC archive is selected where the two DLC archives overlap.

## Regression commands

The synthetic and failure-path reader tests cover raw full blocks, real bundled Zstandard frames, final-size trimming, overflow offsets, unsupported compression/content types, truncated data, missing chunk tables, inconsistent lengths, cache v3 round-trip, and MP-worker success/failure behavior:

```powershell
python tools/test_pak_chunk_reader.py -v
python -m py_compile modules/pak/file_re_pak.py modules/pak/re_pak_utils.py modules/pak/re_pak_extract_mp.py
```

No game assets or generated caches belong in the repository; use an external output directory such as `D:\temp\owots_pak_validation`.
