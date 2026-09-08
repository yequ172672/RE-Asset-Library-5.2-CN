# Companion editor patches

OWOTS support requires matching changes in the asset library, RE Mesh Editor and RE Chain Editor. This directory preserves the companion source changes so the asset library fork can be reproduced without relying on a particular local Blender installation.

The adapted companion sources are also available in the user's forks on
`feat/onimusha-wots`: [RE Mesh Editor](https://github.com/yequ172672/RE-Mesh-Editor-5.2-CN/tree/feat/onimusha-wots)
and [RE Chain Editor](https://github.com/yequ172672/RE-Chain-Editor-5.2-CN/tree/feat/onimusha-wots).
These maintained branches include OWOTS compatibility and Simplified Chinese
localization. Do not apply the patches again to these branches.

| Patch | Upstream repository | Base commit |
| --- | --- | --- |
| `re-mesh-editor-owots.patch` | [NSACloud/RE-Mesh-Editor](https://github.com/NSACloud/RE-Mesh-Editor) | `622daa75b41ec622c3444ecb44ef31a651692687` (0.66) |
| `re-chain-editor-owots.patch` | [NSACloud/RE-Chain-Editor](https://github.com/NSACloud/RE-Chain-Editor) | `54ed5d41a6360511b4b314c80e9b459032b32688` (14.0) |

Apply each patch to a clean checkout of its exact base commit. Do not apply it again to a checkout that already contains the OWOTS changes. For example, from the directory containing these sibling repositories:

```powershell
git -C RE-Mesh-Editor-main apply --check ../RE-Asset-Library-cn/compatibility/re-mesh-editor-owots.patch
git -C RE-Mesh-Editor-main apply ../RE-Asset-Library-cn/compatibility/re-mesh-editor-owots.patch
git -C RE-Chain-Editor-main apply --check ../RE-Asset-Library-cn/compatibility/re-chain-editor-owots.patch
git -C RE-Chain-Editor-main apply ../RE-Asset-Library-cn/compatibility/re-chain-editor-owots.patch
```

The patches retain the original editor architecture and licenses. They add OWOTS mesh/material/texture handling, Chain2 17, the Geometry Nodes modifier input API required by Blender 5.2, and Chinese UI translation registration. They do not add game assets.

Build installable ZIP files with `tools/package_addons.ps1` in the asset library repository. Pass the three source directories and a separate output directory. Install all three ZIP files in Blender 5.2; the ZIP roots retain the original add-on module names so existing settings can be reused.

Game-resource validation requires a local game installation. The asset library's `tools/headless_validate.py`, `tools/test_owots_formats.py`, and PAK checks are separate from the installation ZIPs. A successful import does not by itself prove in-game export compatibility.
