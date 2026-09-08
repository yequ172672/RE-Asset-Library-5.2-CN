"""Chinese (Simplified) translations for the RE Asset Library add-on.

The add-on keeps its operator identifiers, RNA property identifiers, file
extensions and game identifiers in English.  Blender's translation registry
is used for presentation text instead, so switching back to English leaves
the source strings and all data formats unchanged.

Blender 5.2 uses ``zh_HANS`` for Simplified Chinese.  ``zh_CN`` is included
as a compatibility alias for installations which still expose the older
locale name.  The dictionaries are deliberately kept here rather than
scattered through operators, which makes new UI text easy to add and keeps
the English source readable.
"""

from __future__ import annotations

import bpy


_INTERFACE = {
    # Preferences and asset-browser panels.
    "Donate on Ko-fi": "在 Ko-fi 上捐赠",
    "RE Asset Libraries": "RE 资产库",
    "RE Assets": "RE 资产",
    "Unpack Mod Pak": "解包 Mod PAK",
    "Game extraction set up completed.": "游戏文件提取设置完成。",
    "The asset library must be set to the game you're extracting from.": "必须将资产库设置为要提取文件的游戏。",
    "New Asset Library File Type Whitelist": "新建资产库文件类型白名单",
    "Import Options": "导入选项",
    "Info": "信息",
    "Message Box": "消息框",
    "Error": "错误",
    "Library Name: ": "资产库名称：",
    "Library Name: {gameName}": "资产库名称：{gameName}",
    "Last Update: ": "上次更新：",
    "Last Update: {timestamp}": "上次更新：{timestamp}",
    "Download Size: ": "下载大小：",
    "Download Size: {size}": "下载大小：{size}",
    "Installed Size: ": "安装大小：",
    "Installed Size: {size}": "安装大小：{size}",
    "Blender will become unresponsive while downloading the library.":
        "下载资产库时 Blender 可能暂时无响应。",
    "Failed to retrieve available asset libraries.": "获取可用资产库失败。",
    "Check your internet connection.": "请检查网络连接。",
    "Download List Files": "下载列表文件",
    "RE Asset Library V": "RE 资产库 V",
    "RE Asset Library V{version}": "RE 资产库 V{version}",
    "Library: ": "资产库：",
    "Library: {gameName}": "资产库：{gameName}",
    "Game: {gameName}": "游戏：{gameName}",
    "Update Date: {timestamp}": "更新日期：{timestamp}",
    "Download Asset Library": "下载资产库",
    "Update Asset Library": "更新资产库",
    "Set Game Extract Paths": "设置游戏文件提取路径",
    "Extract Game Files": "提取游戏文件",
    "Update MDF Files": "更新 MDF 文件",
    "Update MDF Collections": "更新 MDF 集合",
    "Update RSZ Files": "更新 RSZ 文件",
    "No RE Asset library is selected.": "未选择 RE 资产库。",
    "RE Asset Settings": "RE 资产设置",
    "RE Engine Asset Browser": "RE Engine 资产浏览器",
    "Asset library path is not configured": "尚未配置资产库路径",
    "Asset library path is missing": "资产库路径不存在",
    "No RE asset catalogs found": "未找到 RE 资产目录",
    "Catalogs: ": "目录：",
    "Catalogs: {games}  Assets: {assets}": "目录：{games}  资产：{assets}",
    "Preview: {message}": "预览：{message}",
    "Vertices: {vertices}  Triangles: {triangles}": "顶点：{vertices}  三角形：{triangles}",
    "Waiting for preview decoding before import": "等待预览解码结束后导入",
    "RE Asset Library Developer Tools": "RE 资产库开发工具",
    "Thumnbnail Tools": "缩略图工具",
    "Catalog Tools": "目录工具",
    "Export Tools": "导出工具",
    "Extract Game Files": "提取游戏文件",
    "Reload all new or changed asset thumbnails?": "重新加载所有新增或已更改的资产缩略图？",
    "Are you sure you want to reimport the catalog?": "确定要重新导入目录吗？",
    "This will reset any unsaved names.": "这会重置所有未保存的名称。",
    "Save changes made to RE Assets to catalog?": "要将对 RE 资产所做的更改保存到目录吗？",
    "This will also save the current blend file.": "这也会保存当前 Blend 文件。",
    "This will generate a zip file containing all changes made.": "这会生成包含全部更改的 ZIP 文件。",
    "Package the library into an .reassetlib file?": "要将资产库打包为 .reassetlib 文件吗？",
    "This will overwrite packedAssetCat_XXXX.zst.": "这会覆盖 packedAssetCat_XXXX.zst。",
    "Any changes in the library are compared to this file.": "资产库中的更改将与此文件进行比较。",
    "Submit Changes To GitHub won't work as intended.": "提交更改到 GitHub 的功能将无法按预期工作。",
    "An update is available.": "有可用更新。",
    "Update Date: ": "更新日期：",
    "Asset library is up to date.": "资产库已是最新版本。",
    "Update MDF files for the latest game version.": "将 MDF 文件更新到最新游戏版本。",
    "Update MDF collections in Blender for the latest game version.":
        "将 Blender 中的 MDF 集合更新到最新游戏版本。",
    "Update RSZ (scn,pfb,user) files for the latest game version.":
        "将 RSZ（scn、pfb、user）文件更新到最新游戏版本。",
    "Note that this may not work if the file has had structural changes.":
        "请注意，如果文件结构发生变化，此操作可能无法正常工作。",
    "Be sure to check that it's working properly in game.": "请务必在游戏中检查是否正常工作。",
    "EXPERIMENTAL": "实验性功能",
    "No asset libraries that support this feature are installed.": "未安装支持此功能的资产库。",
    "MDF Updater": "MDF 更新器",
    "RSZ Updater": "RSZ 更新器",
    "Updated {count} MDF files.": "已更新 {count} 个 MDF 文件。",
    "Updated {count} MDF collections.": "已更新 {count} 个 MDF 集合。",
    "Updated {count} RSZ files.": "已更新 {count} 个 RSZ 文件。",
    "An asset library with MDF updater support must be chosen and a mod directory must be set.": "必须选择支持 MDF 更新器的资产库并设置 Mod 目录。",
    "An asset library with MDF updater support must be chosen.": "必须选择支持 MDF 更新器的资产库。",
    "An asset library with RSZ updater support must be chosen and a mod directory must be set.": "必须选择支持 RSZ 更新器的资产库并设置 Mod 目录。",
    "Loose Files Directory (Optional)": "松散文件目录（可选）",
    "Output Directory (Optional)": "输出目录（可选）",
    "Large pak files may be slow": "较大的 PAK 文件可能处理较慢",
    "Restart blender": "重启 Blender",
    "Update Now": "立即更新",
    "Defer": "稍后处理",
    "Click for manual download.": "点击手动下载。",
    "(failed to retrieve direct download)": "（无法获取直接下载链接）",
    "Choose 'Update Now' & press OK to install, ": "选择“立即更新”并按“确定”安装，",
    "or click outside window to defer": "或点击窗口外部稍后处理",
    "Press the download button below and install": "按下方的下载按钮并安装",
    "the zip file like a normal addon.": "像普通插件一样安装 ZIP 文件。",
    "There was an issue trying to auto-install": "自动安装时出现问题",
    "Select install version": "选择安装版本",
    "Install update now": "立即安装更新",
    "Ignore this update to prevent future popups": "忽略此更新以阻止今后弹出提示",
    "Ignore update to prevent future popups": "忽略更新以阻止今后弹出提示",
    "Defer choice till next blender session": "将选择延后到下次 Blender 会话",
    "After the patch pak is created, open the directory containing it in File Explorer": "创建 PAK 补丁后，在文件资源管理器中打开其所在目录",
    "The file was not found on your system.": "在系统中找不到该文件。",
    "Would you like to set up automatic game file extraction?": "要设置自动提取游戏文件吗？",
    "This feature requires the game extract paths to be set.": "此功能需要先设置游戏文件提取路径。",
    "Set the extraction paths now?": "现在设置提取路径吗？",
    "Extract path is very long.": "提取路径过长。",
    "File paths may exceed the max length of 255 characters and fail to extract.":
        "文件路径可能超过 255 个字符的长度限制，导致提取失败。",
    "Consider changing this to a shorter path such as C:\\EXTRACT.":
        "建议改用更短的路径，例如 C:\\EXTRACT。",
    "NOTE: Audio and video files currently do not extract correctly for this game.":
        "注意：此游戏的音频和视频文件目前无法正确提取。",
    "Size is calculated based on the size reported by the game files which isn't always accurate. The actual amount may be less.":
        "大小根据游戏文件报告的数值计算，该数值不一定准确，实际占用可能更小。",
    "Update all new or changed asset thumbnails?": "更新所有新增或已更改的资产缩略图？",
    # Updater UI (the updater module is bundled with this add-on).
    "Updater module error": "更新器模块错误",
    "No updates available": "没有可用更新",
    "Press okay to dismiss dialog": "按“确定”关闭此对话框",
    "Check for update now?": "现在检查更新吗？",
    "Updater error": "更新器错误",
    "Install the addon manually": "手动安装插件",
    "Direct download": "直接下载",
    "Open website": "打开网站",
    "See source website to download the update": "请访问源网站下载更新",
    "Installation Report": "安装报告",
    "Error occurred, did not install": "发生错误，未完成安装",
    "Addon restored": "插件已还原",
    "Addon successfully installed": "插件安装成功",
    "Restart blender to reload": "重启 Blender 以重新加载",
    "Consider restarting blender to fully reload.": "建议重启 Blender 以完全重新加载。",
    "Restore backup": "还原备份",
    "Ignore update": "忽略更新",
    "Update ready!": "更新已就绪！",
    "Ignore": "忽略",
    "Update": "更新",
    "Install manually": "手动安装",
    "Get it now": "立即获取",
    "Error initializing updater code:": "初始化更新器代码时出错：",
    "Error getting updater preferences": "获取更新器偏好设置时出错",
    "Updater Settings": "更新器设置",
    "Interval between checks": "检查间隔",
    "Checking...": "正在检查……",
    "Addon is up to date": "插件已是最新版本",
    "(Re)install addon version": "（重新）安装插件版本",
    "Last update check: ": "上次检查更新：",
    "Last update check: Never": "上次检查更新：从未检查",
    "Last check: ": "上次检查：",
    "Last check: Never": "上次检查：从未检查",
    "Restart blender to complete update": "重启 Blender 以完成更新",
    "to complete update": "以完成更新",
    "Install update manually": "手动安装更新",
    "Popup to check and display current updates available": "检查并显示当前可用更新的弹窗",
}


_OPERATORS = {
    # Operator labels.
    "Add File Type": "添加文件类型",
    "Remove File Type": "移除文件类型",
    "Reset to Default": "恢复默认值",
    "Import RE Asset Library (.reassetlib)": "导入 RE 资产库（.reassetlib）",
    "Download RE Asset Libraries": "下载 RE 资产库",
    "Create New RE Asset Library": "创建新的 RE 资产库",
    "Refresh RE Asset Libraries": "刷新 RE 资产库",
    "Open RE Asset Library Folder": "打开 RE 资产库文件夹",
    "Open Asset Location": "打开资产位置",
    "Render RE Asset Thumbnails": "渲染 RE 资产缩略图",
    "Fetch RE Asset Thumbnails": "获取 RE 资产缩略图",
    "Initialize RE Asset Library": "初始化 RE 资产库",
    "Reload RE Asset Catalog File": "重新加载 RE 资产目录文件",
    "Save Changes To Catalog": "保存更改到目录",
    "Generate Library Diff": "生成资产库差异",
    "Import Library Changes": "导入资产库更改",
    "Package RE Asset Library": "打包 RE 资产库",
    "Check For Library Update": "检查资产库更新",
    "Open Library Folder": "打开资产库文件夹",
    "Generate Material Compendium": "生成材质汇编",
    "Generate RSZ CRC Compendium": "生成 RSZ CRC 汇编",
    "Select RE Engine Asset": "选择 RE Engine 资产",
    "Preview RE Engine Asset": "预览 RE Engine 资产",
    "Import RE Engine Asset": "导入 RE Engine 资产",
    "Refresh RE Engine Browser": "刷新 RE Engine 浏览器",
    "Clear RE Engine Preview": "清除 RE Engine 预览",
    "Set Up Automatic Game File Extraction": "设置自动提取游戏文件",
    "Set Game Extract Paths": "设置游戏文件提取路径",
    "Extract Game Files": "提取游戏文件",
    "Open Extract Folder": "打开提取文件夹",
    "Reload Pak Cache": "重新加载 PAK 缓存",
    "Create Pak Patch": "创建 PAK 补丁",
    "Extract Mod Pak": "提取 Mod PAK",
    "File handler for RE Pak extraction": "RE PAK 提取文件处理器",
    "Batch MDF Updater": "批量 MDF 更新器",
    "Blender MDF Updater": "Blender MDF 更新器",
    "Batch RSZ CRC Updater": "批量 RSZ CRC 更新器",
    "Update {x} addon": "更新 {x} 插件",
    "Check now for " : "立即检查更新：",
    "Update " : "更新",
    "Install update manually": "手动安装更新",
    "Installation Report": "安装报告",
    "Restore addon from backup": "从备份还原插件",
    "Ignore update": "忽略更新",
    "End background check": "结束后台检查",
}


_PROPERTIES = {
    # Preferences, dialog fields, and property groups.
    "Asset Library Path": "资产库路径",
    "Show Mesh Import Options": "显示网格导入选项",
    "Place At Cursor": "放置到光标处",
    "Instance Duplicates": "实例化重复项",
    "Force Extract Files": "强制提取文件",
    "Auto-check for Update": "自动检查更新",
    "Months": "月",
    "Days": "天",
    "Hours": "小时",
    "Minutes": "分钟",
    "File Type": "文件类型",
    "Library Name": "资产库名称",
    "Game Name": "游戏名称",
    "Release Description": "发布说明",
    "Package Date": "打包日期",
    "CRC": "CRC",
    "Download Size": "下载大小",
    "Installed Size": "安装大小",
    "URL": "URL",
    "RE Asset Library": "RE 资产库",
    "List Path": "列表路径",
    "Library Path": "资产库路径",
    "Game EXE File Path": "游戏 EXE 文件路径",
    "Extract Path": "提取路径",
    "Platform": "平台",
    "Skip Unknowns": "跳过未知文件",
    "Check All Categories": "选中所有类别",
    "Uncheck All Categories": "取消选中所有类别",
    "Check All Paks": "选中所有 PAK",
    "Uncheck All Paks": "取消选中所有 PAK",
    "Refresh Required Storage Amounts": "刷新所需存储空间",
    "Open Extract Folder When Finished": "完成后打开提取文件夹",
    "Mod Directory": "Mod 目录",
    "Pak Output Path": "PAK 输出路径",
    "Open output directory after pak creation": "创建 PAK 后打开输出目录",
    "File Path": "文件路径",
    "Game": "游戏",
    "Target version to install": "要安装的目标版本",
    "Clean install": "全新安装",
    "Process update": "处理更新",
    "Search Subdirectories": "搜索子目录",
    "Create MDF Backups": "创建 MDF 备份",
    "Create RSZ Backups": "创建 RSZ 备份",
    "Force Reload All": "强制全部重新加载",
    "Silent": "静默",
    "Open Directory": "打开目录",
    "Check to enable extracting of this": "勾选以启用此项提取",
    "Download List Files": "下载列表文件",
    "Choose which asset library to download from the repository": "选择要从仓库下载的资产库",
    "Set which game to create the library for": "选择要为其创建资产库的游戏",
    "Set the folder containing the natives folder for your mod": "设置包含 Mod 的 natives 文件夹的目录",
    "Set the path where you want the patch pak to saved": "设置保存 PAK 补丁的路径",
}


_TOOLTIPS = {
    # Property descriptions and operator descriptions.
    "Add file type to whitelist.\nWhen creating a new asset library, choose which file types will be imported into the library.\nNOTE: Allowing too many file types may cause the asset browser to slow down.":
        "将文件类型添加到白名单。\n创建新资产库时，选择要导入库中的文件类型。\n注意：允许过多文件类型可能会使资产浏览器变慢。",
    "Remove file type from the whitelist": "从白名单中移除文件类型",
    "Resets the filetype whitelist to it's default values.": "将文件类型白名单恢复为默认值。",
    "Location to store downloaded/created RE Asset libraries": "保存下载或创建的 RE 资产库的位置",
    "When dragging an RE Asset onto the 3D View, prompt with import options": "将 RE 资产拖入 3D 视图时显示导入选项",
    "When dragging an RE Asset, it will be imported at the location that it was dragged to.\nIf this is disabled, it will be imported at the world origin.\nNote that if you are creating mesh mods, do not check this option. Having objects not imported at the world origin may cause issues when exporting":
        "拖动 RE 资产时，将其导入到拖放位置。\n禁用后会导入到世界原点。\n如果正在制作网格 Mod，请勿勾选此项；对象未导入世界原点可能会导致导出问题。",
    "If a mesh is imported more than once, create an instance of previously imported mesh.\nNOTE: The Create Collections import option must be enabled":
        "同一网格被导入多次时，创建已导入网格的实例。\n注意：必须启用“创建集合”导入选项。",
    "When dragging an asset from the browser, force files to be extracted from the game files.\nUse this option when there's a game update and you need the latest version of a file.\nAlso enable this if you're getting missing/red textures when importing models.\nThis makes importing files slower but will ensure that nothing is missing or outdated":
        "从浏览器拖动资产时强制从游戏文件中提取。\n游戏更新后需要最新文件时使用此选项。\n导入模型时出现纹理缺失或显示红色时也请启用。\n这会降低导入速度，但能确保文件完整且不过时。",
    "If enabled, auto-check for updates using an interval": "启用后按设定间隔自动检查更新",
    "Number of months between checking for updates": "检查更新的间隔月数",
    "Number of days between checking for updates": "检查更新的间隔天数",
    "Number of hours between checking for updates": "检查更新的间隔小时数",
    "Number of minutes between checking for updates": "检查更新的间隔分钟数",
    "Download RE Asset Libaries": "下载 RE 资产库",
    "Choose which asset library to download from the repository": "选择要从仓库下载的资产库",
    "Create a new asset library using an RETool .list file": "使用 RETool .list 文件创建新的资产库",
    "Location of RE Tool .list file. Make sure to use the correct one for the game you set.\nIf you don't have a .list file, download one from the GitHub repo by pressing the Download List Files button below\nTip: You can shift right click the list file and click Copy as path, then paste it into this field":
        "RETool .list 文件的位置。请确保它与所选游戏匹配。\n如果没有 .list 文件，请按下方的“下载列表文件”按钮从 GitHub 仓库下载。\n提示：可以按住 Shift 右键点击列表文件，选择“复制为路径”，再粘贴到此字段。",
    "Check for any libraries that are not listed and add them to the list.": "检查未列出的资产库并将其添加到列表。",
    "Don't report status after running": "运行后不报告状态",
    "Opens the folder containing RE Asset Libraries in File Explorer": "在文件资源管理器中打开包含 RE 资产库的文件夹",
    "Open the location the selected RE Asset is saved to.\nNote that the file has to be extracted to be able to find it's location": "打开所选 RE 资产的保存位置。\n注意：必须先提取文件才能找到其位置。",
    "Renders thumbnails for all RE assets of a supported type.\nThis will open a new blend file and will take a long time.\nOnly assets without existing thumbnails will be rendered.\nA lot of storage space will be used for cached textures. Consider clearing RE Mesh Editor's texture cache folder after rendering":
        "为所有受支持类型的 RE 资产渲染缩略图。\n这会打开新的 Blend 文件，并且需要较长时间。\n只会渲染没有现有缩略图的资产。\n缓存纹理会占用大量存储空间；渲染后可以清理 RE Mesh Editor 的纹理缓存文件夹。",
    "Sets asset browser thumbnails to thumbnails created by the Render RE Asset button.\nThis may take a minute. Blender will freeze temporarily while assets are being assigned thumbnails":
        "将资产浏览器缩略图设置为“渲染 RE 资产缩略图”创建的缩略图。\n这可能需要几分钟；分配缩略图时 Blender 会暂时冻结。",
    "Discards all saved thumbnail info and reloads it.": "丢弃所有已保存的缩略图信息并重新加载。",
    "Loads all loadable assets from the REAssetCatalog_XXXX.tsv file in the same directory as the blend file.\nTHIS WILL CLEAR ALL ASSETS FROM THE CURRENT LIBRARY":
        "从与 Blend 文件相同目录中的 REAssetCatalog_XXXX.tsv 文件加载全部可加载资产。\n这会清除当前资产库中的所有资产。",
    "Loads all loadable assets from the REAssetCatalog_XXXX.tsv file in the same directory as the blend file": "从与 Blend 文件相同目录中的 REAssetCatalog_XXXX.tsv 文件加载全部可加载资产",
    "Saves all changes to RE Asset names, categories and tags made in Blender to REAssetCatalog_XXXX.tsv": "将 Blender 中对 RE 资产名称、类别和标签所做的全部更改保存到 REAssetCatalog_XXXX.tsv",
    "Exports changes made to library compared to it's original state to a CSV file.": "将资产库相对于原始状态的更改导出为 CSV 文件。",
    "Imports \"_diff\" catalog files. If a directory is chosen, all _diff files will be imported.\nThis will modify the REAssetCatalog file.": "导入“_diff”目录文件。选择目录时会导入其中全部 _diff 文件。\n这会修改 REAssetCatalog 文件。",
    "Packages asset library into .reassetlib file. Can be imported from addon preferences.\nAlso generates packedAssetCat_XXXX.zst for comparing library changes.": "将资产库打包为 .reassetlib 文件，可从插件偏好设置中导入。\n同时生成用于比较资产库更改的 packedAssetCat_XXXX.zst。",
    "Check if a newer version of the library is available on the asset library repository": "检查资产库仓库中是否有更新版本",
    "Opens the folder containing this blend file.": "打开包含此 Blend 文件的文件夹。",
    "Generates file containing paths to all material shaders. This is used for the MDF Updater": "生成包含所有材质着色器路径的文件，供 MDF 更新器使用",
    "Generates file containing paths to all rsz instance types. This is used for the RSZ CRC Updater": "生成包含所有 RSZ 实例类型路径的文件，供 RSZ CRC 更新器使用",
    "Set the path of the main .exe for the game and the location you want to extract files to.\nThis is required for extracting game files": "设置游戏主 .exe 的路径和文件提取位置。\n提取游戏文件前必须完成此设置",
    "Set the path to the main executable file for the game. Example: MonsterHunterWilds.exe.\nYou can find where this file is located by right clicking the game in Steam > Browse Local Files.\nThis is used to determine where pak files are and when the game is updated.\nDo not set it to anything other than the game .exe or extracted files may be corrupted when you try to extract them after a game update": "设置游戏主可执行文件的路径。例如：MonsterHunterWilds.exe。\n可以在 Steam 中右键点击游戏，选择“浏览本地文件”来找到它。\n此路径用于确定 PAK 文件位置以及游戏是否更新。\n请勿设置为游戏 .exe 以外的文件，否则游戏更新后提取文件时可能损坏。",
    "Set where you want to put extracted chunk files. By default it will be extracted to the game install folder": "设置提取的 Chunk 文件保存位置。默认提取到游戏安装目录",
    "Set where you downloaded the game from. This is used to determine the path needed to extract files": "设置游戏来源平台，用于确定提取文件所需的路径",
    "Choose which files to extract from the game's files. You must use the Set Game Extract Paths button first.\n\nNOTE: If you have mods installed using Fluffy Manager and archive invalidation is disabled in the options, uninstall any mods and verify game files on Steam.\n\nOtherwise any files that have been modified will not be extracted.\n\nUse the Reload Pak Cache button afterwards.": "选择要从游戏文件中提取的文件。必须先使用“设置游戏文件提取路径”。\n\n注意：如果通过 Fluffy Manager 安装了 Mod，且选项中禁用了归档失效，请卸载所有 Mod 并在 Steam 中验证游戏文件。\n\n否则任何已修改的文件都不会被提取。\n\n完成后使用“重新加载 PAK 缓存”。",
    "Skips files where the name is unknown.\nIf disabled, these files will be extracted to the re_chunk_000\\UNKNOWN folder as .bin files": "跳过名称未知的文件。\n禁用后，这些文件会作为 .bin 文件提取到 re_chunk_000\\UNKNOWN 文件夹。",
    "Select all categories to be extracted": "选择要提取的全部类别",
    "Deselect all categories to be extracted": "取消选择要提取的全部类别",
    "Select all pak files to be extracted": "选择要提取的全部 PAK 文件",
    "Deselect all pak files to be extracted": "取消选择要提取的全部 PAK 文件",
    "Updates the displayed storage requirements based on which categories and paks are selected.\nMay take a moment to refresh if this is the first time pak sizes are being checked": "根据所选类别和 PAK 更新显示的存储需求。\n首次检查 PAK 大小时刷新可能需要一些时间",
    "Once the pak files are finished extracting, open the extract folder in File Explorer": "PAK 文件提取完成后，在文件资源管理器中打开提取文件夹",
    "Opens the folder extracted game files are saved to.": "打开提取游戏文件的保存文件夹。",
    "Manually rescan all pak files.\nThis is usually done automatically after a change to the game .exe file is detected.\nNOTE: Using Fluffy Manager with archive invalidation enabled in the options will prevent any modified files from being extracted.\nUse this option after uninstalling all Fluffy Manager mods and verifying game files on Steam.": "手动重新扫描所有 PAK 文件。\n检测到游戏 .exe 发生变化后通常会自动执行。\n注意：如果在选项中启用 Fluffy Manager 的归档失效，任何修改过的文件都不会被提取。\n卸载所有 Fluffy Manager Mod 并在 Steam 中验证游戏文件后使用此选项。",
    "Create a pak patch from a selected directory. The natives folder must be inside the selected directory.\nRequired for textures to work in MH Wilds. (May change in the future)\nInstall using Fluffy Manager.": "从所选目录创建 PAK 补丁。natives 文件夹必须位于所选目录内。\n要让《怪物猎人：荒野》中的纹理生效，必须执行此操作（未来可能变化）。\n请使用 Fluffy Manager 安装。",
    "Choose which game to extract the pak file for. The corresponding asset library for the game must be installed and set up for extracting files.": "选择要为其提取 PAK 文件的游戏。必须安装并设置该游戏对应的资产库才能提取文件。",
    "(Optional) Pick a directory containing loose files to scan for additional file paths. All subdirectories will be searched.\nThis is intended to be used when a mod includes files outside of the pak file.\nTip: hold shift and right click a folder, then click \"Copy as path\" and paste it here.": "（可选）选择包含松散文件的目录以扫描其他文件路径。会搜索全部子目录。\n当 Mod 包含 PAK 之外的文件时使用。\n提示：按住 Shift 右键点击文件夹，选择“复制为路径”，再粘贴到此处。",
    "(Optional) Pick directory to place extracted files.\nTip: hold shift and right click a folder, then click \"Copy as path\" and paste it here.\nIf unchanged, the pak will be extracted to whatever folder it's located in": "（可选）选择提取文件的保存目录。\n提示：按住 Shift 右键点击文件夹，选择“复制为路径”，再粘贴到此处。\n保持不变时，PAK 会提取到其所在文件夹。",
    "Updates all .mdf2 (material) files in the chosen directory using the newest MDF files from the pak files": "使用 PAK 中最新的 MDF 文件更新所选目录中的全部 .mdf2（材质）文件",
    "Choose which game to update MDF files for. This is only supported for asset libraries that have support for this feature": "选择要更新 MDF 文件的游戏。仅支持包含此功能的资产库",
    "Choose the folder containing your mod's MDF files.": "选择包含 Mod MDF 文件的文件夹。",
    "Search all directories inside the chosen directory for MDF files to update.": "在所选目录及其所有子目录中搜索要更新的 MDF 文件。",
    "If an MDF file is updated, create a copy of the original file with .bak on the end of it.": "更新 MDF 文件时，在原文件末尾添加 .bak 副本。",
    "Updates all MDF collections loaded in the current blend file": "更新当前 Blend 文件中加载的所有 MDF 集合",
    "Updates outdated CRC values for .scn, .pfb and .user files.\nThis can allow for outdated RSZ files to work after an update, but certain files may not work if there have been structural changes": "更新 .scn、.pfb 和 .user 文件中过时的 CRC 值。\n这可以让过时的 RSZ 文件在更新后继续工作，但文件结构发生变化时部分文件可能无法工作",
    "Choose which game to update MDF files for. This is only supported for asset libraries that have support for this feature": "选择要更新 RSZ 文件的游戏。仅支持包含此功能的资产库",
    "Choose the folder containing your mod's RSZ (scn/pfb/user) files.": "选择包含 Mod RSZ（scn/pfb/user）文件的文件夹。",
    "Search all directories inside the chosen directory for RSZ files to update.": "在所选目录及其所有子目录中搜索要更新的 RSZ 文件。",
    "If an RSZ file is updated, create a copy of the original file with .bak on the end of it.": "更新 RSZ 文件时，在原文件末尾添加 .bak 副本。",
    "Install the addon manually": "手动安装插件",
    "If enabled, completely clear the addon's folder before ": "启用后，在安装前完全清空插件文件夹。",
    "If enabled, completely clear the addon's folder before installing new update, creating a fresh install": "启用后，在安装新更新前完全清空插件文件夹，以进行全新安装",
    "Decide to install, ignore, or defer new addon update": "决定安装、忽略或延后新的插件更新",
    "Select the version to install": "选择要安装的版本",
    "Proceed to manually install update": "继续手动安装更新",
    "Update installation response": "更新安装响应",
    "Stop checking for update in the background": "停止在后台检查更新",
    "Ignore this update to prevent future popups": "忽略此更新以阻止今后弹出提示",
    "Defer choice till next blender session": "将选择延后到下次 Blender 会话",
}


_REPORTS = {
    "Encountered a problem while trying to update": "更新时出现问题",
    "Failed to extract {assetPath}: {err}": "提取 {assetPath} 失败：{err}",
    "{assetPath} - File not found at any chunk paths. See console for details on how to fix this. (Window > Toggle System Console)": "{assetPath} - 在任何 Chunk 路径中都找不到文件。请查看控制台中的修复说明（窗口 > 切换系统控制台）。",
    "Unsupported asset type, cannot import {assetName} - {assetType}": "不支持的资产类型，无法导入 {assetName} - {assetType}",
    "Import failed for {description}": "导入 {description} 失败",
    "Import failed for {description}: {err}": "导入 {description} 失败：{err}",
    "Installed {gameName} library.": "已安装 {gameName} 资产库。",
    "Missing files, cannot create library.": "缺少文件，无法创建资产库。",
    "Failed to import RE Asset Library. See Window > Toggle System Console for details": "导入 RE 资产库失败。详情请查看“窗口 > 切换系统控制台”。",
    "Downloaded {gameName} library. You can open the Asset Browser by going to File > New > RE Assets.": "已下载 {gameName} 资产库。可以通过“文件 > 新建 > RE 资产”打开资产浏览器。",
    "CRC Check on the downloaded file failed. Try downloading the library again.": "下载文件的 CRC 检查失败，请重新下载资产库。",
    "Created new RE Asset Library.": "已创建新的 RE 资产库。",
    "Invalid list path.": "列表路径无效。",
    "Invalid RE asset library path.": "RE 资产库路径无效。",
    "Refreshed RE Asset Library list.": "已刷新 RE 资产库列表。",
    "Opened file location.": "已打开文件位置。",
    "File not found. It might not be extracted.\nDrag it from the library into the 3D view to extract it.": "找不到文件。文件可能尚未提取。\n将其从资产库拖入 3D 视图即可提取。",
    "No chunk paths for {gameName} are present.": "不存在 {gameName} 的 Chunk 路径。",
    "Asset is not an RE Asset.": "该资产不是 RE 资产。",
    "Started asset render job.": "已开始资产渲染任务。",
    "Could not start asset render job. See console. (Window > Toggle System Console)": "无法开始资产渲染任务。请查看控制台（窗口 > 切换系统控制台）。",
    "RE Asset thumbnails have not been rendered. Cannot retrieve.": "RE 资产缩略图尚未渲染，无法获取。",
    "Fetched RE Asset thumbnails.": "已获取 RE 资产缩略图。",
    "Game name not set.": "未设置游戏名称。",
    "REAssetCatalog_{gameName} catalog file missing. Cannot load.": "缺少 REAssetCatalog_{gameName} 目录文件，无法加载。",
    "Loaded RE Assets.": "已加载 RE 资产。",
    "Game name not set in blend file.": "Blend 文件中未设置游戏名称。",
    "REAssetCatalog_{gameName}.tsv catalog file missing. Cannot load.": "缺少 REAssetCatalog_{gameName}.tsv 目录文件，无法加载。",
    "GameInfo_{gameName}.json file missing. Cannot load.": "缺少 GameInfo_{gameName}.json 文件，无法加载。",
    "blender_assets.cats.txt catalog file missing. Cannot load.": "缺少 blender_assets.cats.txt 目录文件，无法加载。",
    "Saved changes to RE Asset Catalog.": "已保存对 RE 资产目录的更改。",
    "packedAssetCat_{gameName}.zst catalog file missing. Cannot load.": "缺少 packedAssetCat_{gameName}.zst 目录文件，无法加载。",
    "Generated Diff file.": "已生成差异文件。",
    "No changes have been made to the asset library so a Diff file can't be generated.": "资产库没有更改，无法生成差异文件。",
    "Imported RE Asset library changes.": "已导入 RE 资产库更改。",
    "Failed to import RE Asset library changes.": "导入 RE 资产库更改失败。",
    "Packaged RE Asset library.": "已打包 RE 资产库。",
    "Failed to package RE Asset library. See console for details.": "打包 RE 资产库失败。详情请查看控制台。",
    "This blend file is not an RE Asset Library. Cannot package.": "此 Blend 文件不是 RE 资产库，无法打包。",
    "Updated RE Asset Library.": "已更新 RE 资产库。",
    "Failed to update RE Asset Library, CRC check failed. Try downloading the asset library again.": "更新 RE 资产库失败，CRC 检查未通过。请重新下载资产库。",
    "Game is not on repository or repository is unreachable.": "仓库中没有该游戏，或无法访问仓库。",
    "Generated Material Compendium.": "已生成材质汇编。",
    "Could not generate compendium. See console. (Window > Toggle System Console)": "无法生成汇编。请查看控制台（窗口 > 切换系统控制台）。",
    "Generated CRC Compendium.": "已生成 CRC 汇编。",
    "Set game extract paths.": "已设置游戏文件提取路径。",
    "RE Engine Extension Browser API is unavailable": "RE Engine 扩展浏览器 API 不可用",
    "RE asset library path is missing or invalid": "RE 资产库路径缺失或无效",
    "Only .mesh assets support GPU preview": "只有 .mesh 资产支持 GPU 预览",
    "Only .mesh assets support full import": "只有 .mesh 资产支持完整导入",
    "RE Asset Library preferences are unavailable": "RE 资产库偏好设置不可用",
    "EXE or extract path is invalid.": "EXE 或提取路径无效。",
    "Invalid library path. Could not set extract paths.": "资产库路径无效，无法设置提取路径。",
    "Extracted game files.": "已提取游戏文件。",
    "Extract paths are not set.": "尚未设置提取路径。",
    "Asset catalog missing.": "缺少资产目录。",
    "Game files are not extracted.": "尚未提取游戏文件。",
    "Reloaded cached pak info.": "已重新加载缓存的 PAK 信息。",
    "No pak files found in game directory.": "游戏目录中未找到 PAK 文件。",
    "Game file extraction is not set up.": "尚未设置游戏文件提取。",
    "Failed to create patch pak. See Window > Toggle System Console": "创建 PAK 补丁失败。请查看“窗口 > 切换系统控制台”。",
    "Created pak patch.": "已创建 PAK 补丁。",
    "Mod directory or output pak path is invalid.": "Mod 目录或 PAK 输出路径无效。",
    "Finished pak extraction. Do not reupload any mod without the original author's permission!": "PAK 提取完成。未经原作者许可，请勿重新上传任何 Mod！",
    "Finished updating MDF files.": "MDF 文件更新完成。",
    "Cancelled MDF update. Run it again once extract paths are set.": "MDF 更新已取消。设置提取路径后请重新运行。",
    "Finished updating MDF collections.": "MDF 集合更新完成。",
    "Finished updating RSZ files.": "RSZ 文件更新完成。",
    "Nothing to update": "没有需要更新的内容",
    "No update ready": "没有就绪的更新",
    "Open addon preferences for updater options": "打开插件偏好设置以配置更新器选项",
    "Error Occurred": "发生错误",
}


_ENUMS = {
    "Devil May Cry 5": "鬼泣 5",
    "Resident Evil 2": "生化危机 2",
    "Resident Evil 3": "生化危机 3",
    "Resident Evil 8": "生化危机 8",
    "Resident Evil 2 Ray Tracing": "生化危机 2 光线追踪版",
    "Resident Evil 3 Ray Tracing": "生化危机 3 光线追踪版",
    "Resident Evil 7 Ray Tracing": "生化危机 7 光线追踪版",
    "Monster Hunter Rise": "怪物猎人：崛起",
    "Street Fighter 6": "街头霸王 6",
    "Resident Evil 4": "生化危机 4",
    "Dragon's Dogma 2": "龙之信条 2",
    "Kunitsu-Gami": "祇：女神之道",
    "Dead Rising": "丧尸围城",
    "Onimusha 2": "鬼武者 2",
    "Onimusha: Way of the Sword": "鬼武者：剑之道",
    "Monster Hunter Wilds": "怪物猎人：荒野",
    "Monster Hunter Stories 3": "怪物猎人物语 3",
    "Steam (Older Titles)": "Steam（较早作品）",
    "Steam (Newer Titles)": "Steam（较新作品）",
    "Steam (Ray Tracing)": "Steam（光线追踪版）",
    "Microsoft Store": "Microsoft Store",
    "Game Pass": "Game Pass",
    "Steam": "Steam",
    "Resident Evil 9": "生化危机 9",
    "Pragmata": "Pragmata",
    "(x64) Choose this option for DMC5 and the non ray tracing versions of RE2 and RE3. (Before 2021)":
        "（x64）DMC5 以及 RE2、RE3 非光线追踪版本使用此选项（2021 年以前）。",
    "(STM) Choose this option for all newer titles. (2021 or newer)":
        "（STM）所有较新作品使用此选项（2021 年及以后）。",
    "(MSG) Choose this option if you own the Microsoft Game Pass version of the game.":
        "（MSG）拥有 Microsoft Game Pass 版本游戏时使用此选项。",
}


def _with_contexts(messages, contexts):
    """Expand a readable message table into Blender's context-keyed format."""
    return {
        (context, message): translation
        for context in contexts
        for message, translation in messages.items()
    }


# ``*`` is Blender's interface context.  Operator and tooltip contexts are
# registered as well because Blender uses those for RNA labels/descriptions
# and operator popovers.  Property labels receive both interface and property
# entries; this remains compatible with Blender 4.x while targeting 5.2.
translations_dict = {
    "zh_HANS": {
        **_with_contexts(_INTERFACE, ("*", "UI")),
        **_with_contexts(_OPERATORS, ("*", "Operator")),
        **_with_contexts(_PROPERTIES, ("*", "Property", "UI")),
        **_with_contexts(_TOOLTIPS, ("Tooltip", "Operator", "*")),
        **_with_contexts(_REPORTS, ("Report", "Tooltip", "*")),
        **_with_contexts(_ENUMS, ("*", "Enum")),
    },
}
# Blender 4.x/5.2 builds in the wild have used both locale spellings.
translations_dict["zh_CN"] = dict(translations_dict["zh_HANS"])
TRANSLATIONS = translations_dict


def register(module_name=__package__):
    """Register the add-on translations once for the current Blender session."""
    if not module_name:
        module_name = __name__.partition(".")[0]
    try:
        bpy.app.translations.register(module_name, translations_dict)
    except ValueError:
        # A script reload can leave the previous module entry in Blender's
        # registry. Replace that entry instead of making add-on enable fail.
        try:
            bpy.app.translations.unregister(module_name)
        except (KeyError, RuntimeError, ValueError):
            pass
        bpy.app.translations.register(module_name, translations_dict)


def unregister(module_name=__package__):
    """Unregister translations without affecting Blender's built-in locales."""
    if not module_name:
        module_name = __name__.partition(".")[0]
    try:
        bpy.app.translations.unregister(module_name)
    except (KeyError, RuntimeError, ValueError):
        # Safe during a partial add-on reload or when Blender already removed
        # the module's translation dictionary.
        pass


def _translate(function_name, message, **values):
    """Call Blender's context-aware translator and format dynamic values.

    Keeping formatting after translation lets messages such as
    ``"Installed {gameName} library."`` retain game identifiers and paths
    verbatim while still translating the surrounding text.  If translations
    are unavailable (for example during a unit test with a minimal bpy stub),
    the original English message is returned.
    """
    translated = message
    function = getattr(getattr(bpy.app, "translations", None), function_name, None)
    if function is not None:
        try:
            translated = function(message)
        except (TypeError, RuntimeError):
            translated = message
    if values:
        try:
            translated = translated.format(**values)
        except (KeyError, IndexError, ValueError):
            # A malformed external string should not make an import/report
            # path fail merely because it was passed through localization.
            translated = message.format(**values)
    return translated


def tr_iface(message, **values):
    """Translate interface labels and dialog text."""
    return _translate("pgettext_iface", message, **values)


def tr_tip(message, **values):
    """Translate tooltip/help text."""
    return _translate("pgettext_tip", message, **values)


def tr_report(message, **values):
    """Translate operator reports while preserving English fallback behavior."""
    return _translate("pgettext_tip", message, **values)


__all__ = ["translations_dict", "TRANSLATIONS", "register", "unregister", "tr_iface", "tr_tip", "tr_report"]
