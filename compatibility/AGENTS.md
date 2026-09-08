# Companion compatibility patches

## Key Files
| File | Purpose |
| --- | --- |
| `README.md` | Exact upstream bases and patch/install instructions |
| `re-mesh-editor-owots.patch` | RE Mesh Editor runtime changes against the documented base |
| `re-chain-editor-owots.patch` | RE Chain Editor runtime changes against the documented base |

## Common Patterns
- Regenerate patches from the sibling repositories after their runtime changes are finalized.
- Include new runtime files when generating a patch; do not include game files, texture caches, `.git`, or machine-specific preferences.
- Verify `git apply --check` against each exact clean upstream base before delivery.
- Keep source changes and the installable packages synchronized.
