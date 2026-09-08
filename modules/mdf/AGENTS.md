# Material reader

## Key Files
| File | Purpose |
| --- | --- |
| `file_re_mdf.py` | MDF binary reader/writer, including full and texture-only fast readers |
| `re_mdf_updater_utils.py` | Material compendium and updater implementation |
| `re_mdf_updater_operators.py` | Blender material updater operators |

## Common Patterns
- OWOTS shares MDF extension 51 with other games but uses a 104-byte material header instead of the ordinary 108-byte header.
- Preserve variant detection and the additional uint before textureCount in both full and fast reads and in writes.
- Test the same material and texture-reference signatures through both readers; retain ordinary v51 regression coverage.
- These updater Python files are required runtime source, not disposable updater-cache directories.
