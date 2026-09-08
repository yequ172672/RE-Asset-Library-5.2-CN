# modules/pak

## Key Files

| Path | Purpose |
| --- | --- |
| `file_re_pak.py` | PAK headers, encrypted TOCs, v4.2 chunk content tables and entry metadata |
| `re_pak_utils.py` | Cache v3, shared entry reader, direct/cache extraction and archive priority |
| `re_pak_extract_mp.py` | Multiprocessing extraction worker using the shared entry reader |
| `re_pak_operators.py` | Blender extraction and cache operators |

## Common Patterns

- v4.2 feature `0x28` uses bit 5 for the chunk content table. Entry offsets with content-table type 1 are chunk indices, never byte offsets.
- Chunk records use `attributes & 0x3ff` for the high offset overflow and `attributes >> 10` for the physical chunk size. Smaller chunks are independent Zstandard frames; raw full blocks use the PAK block size directly.
- `readPakEntryData` is the single data path for direct, cache-backed, debug, mod-pak and MP extraction. It validates content/compression types, truncated reads and decompressed-size coverage.
- Cache format version 3 stores offset, compressed/decompressed sizes, compression/encryption types, content-table type and PAK index. A cache with another version must be regenerated.
- Header bit 6 remap tables are unsupported until a real sample and format definition are available; fail explicitly instead of treating a chunk index as a remap index.
- `getStreamingPath` must match the `natives/<platform>/` prefix case-insensitively; PAK hashes are case-insensitive while extracted disk paths may use either `stm` or `STM`.
- Catalog extension/category checks must normalize case before selecting streaming sidecars; `.tex` and `.TEX` represent the same resource type.

## Validation

Run from the repository root:

```powershell
python tools/test_pak_chunk_reader.py -v
python tools/validate_owots_pak.py --game-dir D:\gametest\steamapps\common\OnimushaWotS --output-dir D:\temp\owots_pak_validation\pak_entry_validation
```

The real validation keeps extracted outputs and generated caches outside the repository. See [docs/onimusha-pak-validation.md](../../docs/onimusha-pak-validation.md) for archive counts, priority overlaps and the >4 GiB chunk evidence.
