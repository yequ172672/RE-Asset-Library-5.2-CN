# Chinese localization

The add-on keeps its runtime identifiers and file formats in English and
registers presentation text through the Blender 5.2 translation API. The
source of truth is [`translations.py`](../translations.py), which exports
`translations_dict` for `zh_HANS` and the `zh_CN` compatibility locale and
provides `tr_iface`, `tr_tip`, and `tr_report` for dynamic UI text.

When adding a visible string, keep the original English string in the
operator/property definition and add its Simplified Chinese entry to the
appropriate context table. Use `tr_iface` for dialog or panel strings and
`tr_report` for dynamic operator reports so identifiers, paths, and counts can
be formatted after translation. Do not translate operator IDs, RNA property
names, game IDs, file extensions, catalog names, or on-disk JSON keys.

Validate the registration lifecycle with an official Blender 5.2 binary in an
isolated configuration:

```powershell
$env:BLENDER_USER_CONFIG = 'D:\temp\re-asset-i18n-config'
$env:BLENDER_USER_SCRIPTS = 'D:\temp\re-asset-i18n-scripts'
blender.exe --background --factory-startup --python-exit-code 1 --python tools/validate_localization.py -- `
  --asset-addon 'D:\CODE\re\RE-Asset-Library-cn' `
  --mesh-addon 'D:\CODE\re\RE-Mesh-Editor-main' `
  --chain-addon 'D:\CODE\re\RE-Chain-Editor-main' `
  --report 'D:\temp\re-asset-i18n-report.json'
```

The validation must check enable/disable twice, Chinese interface and tooltip
lookups, and English fallback. Never write user preferences or a blend file as
part of this check.

The 5.2-CN integration also checks both translation contexts, formatted report
arguments, matching locale aliases and removal of translations after disabling
all three add-ons. Shared English message keys use consistent Chinese wording
across the three tables so enabling order does not change the interface.

Fresh package acceptance uses official Blender 5.2 build `fbe6228777e7`.
Local evidence is under `_validation/cn_package_accept`: `localization.json`,
`mesh.log` and `chain.json`. The existing OWOTS character retains LOD0
(48,909 vertices and 317 bones), a 2048 x 2048 cloth texture, and Chain2
imports retain 22 groups, 82 nodes and 10 links. The two previously documented
missing skeleton hashes remain an asset-binding limitation.
