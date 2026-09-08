# Adaptation evidence

## Key Files
| File | Purpose |
| --- | --- |
| `onimusha-pak-validation.md` | Archive format, chunk-offset and extraction verification |
| `onimusha-quality-validation.md` | LOD, texture fidelity, live asset import and Chain2 acceptance boundaries |
| `asset-catalog-path-migration.md` | Path-based catalog behavior, safe existing-library migration and isolated validation commands |
| `localization.md` | Blender 5.2 Simplified Chinese translation workflow and isolated lifecycle validation |
| `reengine-browser.md` | Custom browser and LOD2/base-color preview behavior, setup and user-run acceptance |

## Common Patterns
- Distinguish header/index parsing, extracted bytes, Blender object creation and visual fidelity.
- Record representative real-file evidence without copying game assets into this repository.
- Keep known limitations visible; do not equate an operator's FINISHED result with successful import.
