bl_info = {
	"name": "RE Asset Library",
	"author": "NSA Cloud; fork maintainer: yequ172672",
	"version": (0, 25, 6),
	"blender": (4, 3, 0),
	"location": "Asset Browser > RE Assets",
	"description": "Quickly search through and import RE Engine meshes.",
	"wiki_url": "https://github.com/yequ172672/RE-Asset-Library-5.2-CN/tree/feat/onimusha-wots",
	"tracker_url": "https://github.com/yequ172672/RE-Asset-Library-5.2-CN/issues",
	"category": "Import-Export"}

import bpy
from . import translations
from .translations import tr_iface, tr_report
from . import addon_updater_ops

from bpy.app.handlers import persistent

import os
import json
import queue
import shutil
import subprocess
import glob
import traceback

from .modules.gen_functions import formatByteSize,resolvePath,wildCardFileSearch,openFolder
from .modules.blender_utils import showErrorMessageBox
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty, CollectionProperty,PointerProperty
from bpy.types import Operator,Panel,AddonPreferences

from .modules.pak.re_pak_operators import (
	WM_OT_PromptSetExtractInfo,
	WM_OT_SetExtractInfo,
	WM_OT_ExtractGameFiles,
	WM_OT_OpenExtractFolder,
	WM_OT_ReloadPakCache,
	WM_OT_CreatePakPatch,
	WM_OT_UnpackModPak,
	PAK_FH_drag_import,
	
	
)
from .modules.pak.re_pak_utils import (
	extractFilesFromPakCache,

)

from .modules.asset.re_asset_utils import (
	buildNativesPathFromObj,

)
from .modules.asset.blender_re_asset import (
	importREMeshAsset,
	importREChainAsset,
	importREChain2Asset,
	importREFBXSkelAsset,
	)
from .modules.asset.native_browser import (
	CLASSES as REENGINE_BROWSER_CLASSES,
	is_available as is_reengine_browser_available,
	register as register_reengine_browser,
	unregister as unregister_reengine_browser,
	)
from .modules.asset.re_asset_operators import (
	getGameNameFromAssetBrowser,
	getAssetLibrary,
	unzipLibrary,
	loadGameInfo,
	downloadREAssetLibDirectory,
	downloadFileContent,
	getFileCRC,
	download_file_from_google_drive,
	getChunkPathList,
	
	WM_OT_FetchREAssetThumbnails,
	WM_OT_ImportREAssetLibraryFromCatalog,
	WM_OT_SaveREAssetLibraryToCatalog,
	WM_OT_ExportCatalogDiff,
	WM_OT_ImportCatalogDiff,
	WM_OT_PackageREAssetLibrary,
	WM_OT_InitializeREAssetLibrary,
	WM_OT_CheckForREAssetLibraryUpdate,
	WM_OT_OpenLibraryFolder,
	WM_OT_GenerateMaterialCompendium,
	WM_OT_GenerateRSZCRCCompendium,
	
	REToolListFileToREAssetCatalogAndGameInfo,
	

)
from .modules.mdf.re_mdf_updater_operators import (
	WM_OT_BatchMDFUpdater,
	WM_OT_BlenderMDFUpdater,

)

from .modules.rszmini.re_rsz_updater_operators import (
	WM_OT_BatchRSZUpdater,

)

from .modules.asset.re_asset_propertyGroups import (
	REAssetWhiteListEntryPropertyGroup,
	ASSET_UL_FileTypeWhiteList,
	REAssetLibEntryPropertyGroup,
	ASSET_UL_REAssetLibList,

)


from .modules.asset.ui_re_asset_panels import (
	OBJECT_PT_REAssetLibraryPanel,
	)
from .modules.pak.re_pak_propertyGroups import (
	ToggleStringPropertyGroup,
	ASSET_UL_StringCheckList,

)
from .modules.pak.ui_re_pak_panels import (
	OBJECT_PT_ExtractGameFilesPanel,
	)
class LIST_OT_NewWhiteListItem(Operator):
	bl_idname = "re_asset.new_whitelist_item"
	bl_label = "Add File Type"
	bl_description = "Add file type to whitelist.\nWhen creating a new asset library, choose which file types will be imported into the library.\nNOTE: Allowing too many file types may cause the asset browser to slow down."
	bl_options ={"INTERNAL"}
	def execute(self, context): 
		bpy.context.preferences.addons[__name__].preferences.fileTypeWhiteList_items.add() 
		return{'FINISHED'}

class LIST_OT_DeleteWhiteListItem(Operator):
	bl_idname = "re_asset.delete_whitelist_item"
	bl_label = "Remove File Type"
	bl_options ={"INTERNAL"}
	bl_description = "Remove file type from the whitelist"
	def execute(self, context): 
		whiteList = bpy.context.preferences.addons[__name__].preferences.fileTypeWhiteList_items
		index = bpy.context.preferences.addons[__name__].preferences.fileTypeWhiteList_index
		whiteList.remove(index)
		bpy.context.preferences.addons[__name__].preferences.fileTypeWhiteList_index = min(max(0, index - 1), len(whiteList) - 1)
		
		return{'FINISHED'}
	
class LIST_OT_ResetWhiteListItems(Operator):
	bl_idname = "re_asset.reset_whitelist_items"
	bl_label = "Reset to Default"
	bl_options ={"INTERNAL"}
	bl_description = "Resets the filetype whitelist to it's default values."
	def execute(self, context): 
		whiteList = bpy.context.preferences.addons[__name__].preferences.fileTypeWhiteList_items
		whiteList.clear()
		item = whiteList.add()
		item.fileType = "mesh"
		
		item = whiteList.add()
		item.fileType = "chain"
		
		item = whiteList.add()
		item.fileType = "chain2"
		
		item = whiteList.add()
		item.fileType = "fbxskel"
		return{'FINISHED'}
class REAssetPreferences(AddonPreferences):
	bl_idname = __name__
	# addon updater preferences
	assetLibraryPath: StringProperty(
		name="Asset Library Path",
		subtype='DIR_PATH',
		description = "Location to store downloaded/created RE Asset libraries",
		default = os.path.join(os.path.dirname(os.path.realpath(__file__)),"REAssetLibrary")
	)
	
	showMeshImportOptions : BoolProperty(
	   name = "Show Mesh Import Options",
	   description = "When dragging an RE Asset onto the 3D View, prompt with import options",
	   default = True)
	placeAtCursor : BoolProperty(
	   name = "Place At Cursor",
	   description = "When dragging an RE Asset, it will be imported at the location that it was dragged to.\nIf this is disabled, it will be imported at the world origin.\nNote that if you are creating mesh mods, do not check this option. Having objects not imported at the world origin may cause issues when exporting",
	   default = False)
	
	instanceDuplicates : BoolProperty(
	   name = "Instance Duplicates",
	   description = "If a mesh is imported more than once, create an instance of previously imported mesh.\nNOTE: The Create Collections import option must be enabled",
	   default = True)
	forceExtract : BoolProperty(
	   name = "Force Extract Files",
	   description = "When dragging an asset from the browser, force files to be extracted from the game files.\nUse this option when there's a game update and you need the latest version of a file.\nAlso enable this if you're getting missing/red textures when importing models.\nThis makes importing files slower but will ensure that nothing is missing or outdated",
	   default = True)
	
	fileTypeWhiteList_items: bpy.props.CollectionProperty(type=REAssetWhiteListEntryPropertyGroup)
	fileTypeWhiteList_index: bpy.props.IntProperty(name="")
	
	auto_check_update: bpy.props.BoolProperty(
	    name = "Auto-check for Update",
	    description = "If enabled, auto-check for updates using an interval",
	    default = False,
	)
	
	updater_interval_months: bpy.props.IntProperty(
	    name='Months',
	    description = "Number of months between checking for updates",
	    default=0,
	    min=0
	)
	updater_interval_days: bpy.props.IntProperty(
	    name='Days',
	    description = "Number of days between checking for updates",
	    default=7,
	    min=0,
	)
	updater_interval_hours: bpy.props.IntProperty(
	    name='Hours',
	    description = "Number of hours between checking for updates",
	    default=0,
	    min=0,
	    max=23
	)
	updater_interval_minutes: bpy.props.IntProperty(
	    name='Minutes',
	    description = "Number of minutes between checking for updates",
	    default=0,
	    min=0,
	    max=59
	)
	def draw(self, context):
		layout = self.layout
		op = self.layout.operator(
        'wm.url_open',
        text=tr_iface('Donate on Ko-fi'),
        icon='FUND'
        )
		op.url = 'https://ko-fi.com/nsacloud'
		
		layout.label(text=tr_iface("RE Asset Libraries"))
		layout.prop(self,"assetLibraryPath")
		layout.operator("re_asset.open_re_asset_library_folder",icon = "FILE_FOLDER")
		layout.row()
		layout.operator("re_asset.download_re_asset_library",icon = "INTERNET")
		layout.operator("re_asset.detect_re_asset_library",icon = "FILE_REFRESH")
		layout.operator("re_asset.create_re_asset_library",icon = "NEWFOLDER")
		
		layout.row()
		layout.label(text=tr_iface("New Asset Library File Type Whitelist"))
		layout.template_list("ASSET_UL_FileTypeWhiteList", "", self, "fileTypeWhiteList_items", self, "fileTypeWhiteList_index",rows = 4)
		row = layout.row()
		col = row.column()
		col.operator("re_asset.new_whitelist_item")
		col = row.column()
		col.operator("re_asset.delete_whitelist_item")
		layout.operator("re_asset.reset_whitelist_items")
		layout.label(text=tr_iface("Import Options"))
		layout.prop(self,"showMeshImportOptions")
		layout.prop(self,"placeAtCursor")
		#layout.prop(self,"instanceDuplicates")
		layout.prop(self,"forceExtract")
		addon_updater_ops.update_settings_ui(self,context)


class ImportREAssetLib(bpy.types.Operator, ImportHelper):
	'''Import RE Engine Asset Library (.reassetlib) File'''
	bl_idname = "re_asset.importlibrary"
	bl_label = "Import RE Asset Library (.reassetlib)"
	bl_options = {'PRESET', "REGISTER", "UNDO"}
	
	filename_ext = ".reassetlib"
	filter_glob: StringProperty(default="*.reassetlib", options = {"HIDDEN"})
	currentBlendPath: bpy.props.StringProperty(default="", options = {"HIDDEN"})
	def execute(self, context):
		if os.path.isfile(self.filepath):
			assetLibraryDir = bpy.path.abspath(bpy.context.preferences.addons[__name__].preferences.assetLibraryPath)
			gameName = unzipLibrary(assetLibraryDir, self.filepath)
			if gameName != None:
				print(f"Attempting to install {gameName} library...")
				newLibraryDir = os.path.join(assetLibraryDir,gameName)
				os.makedirs(newLibraryDir,exist_ok=True)
				outputCatalogPath = os.path.join(newLibraryDir,f"REAssetCatalog_{gameName}.tsv")
				outputGameInfoPath = os.path.join(newLibraryDir,f"GameInfo_{gameName}.json")
				addonDir = os.path.split(__file__)[0]
				sourceBlendPath = os.path.join(addonDir,"Resources","Blend","libraryBase.blend")
				outputBlendPath = os.path.join(newLibraryDir,f"REAssetLibrary_{gameName}.blend")
				scriptPath = os.path.join(addonDir,"Resources","Scripts","initializeLibrary.py")
				if not os.path.isfile(outputBlendPath):
					shutil.copy(sourceBlendPath,outputBlendPath)
					
				if os.path.isfile(outputCatalogPath) and os.path.isfile(outputGameInfoPath) and os.path.isfile(outputBlendPath) and os.path.isfile(scriptPath):
					if outputBlendPath == self.currentBlendPath:
						bpy.ops.re_asset.initialize_library()
					else:
						with subprocess.Popen([bpy.app.binary_path, outputBlendPath, "--python", scriptPath]):
							pass#Wait for install to finish
						
						self.report({"INFO"},tr_report("Installed {gameName} library.", gameName=gameName))
						
						
				else:
					self.report({"ERROR"},tr_report("Missing files, cannot create library."))
					return {'CANCELLED'}
				
				#Update asset library list
				bpy.ops.re_asset.detect_re_asset_library(silent = True)
				return {"FINISHED"}
		self.report({"INFO"},tr_report("Failed to import RE Asset Library. See Window > Toggle System Console for details"))
		return {"CANCELLED"}
	
def getAssetDirectoryItems(self,context):
	entryList = []
	for index,entry in enumerate(self.assetLibList_items):
		entryList.append((str(index),entry.displayName,""))
	return entryList
class WM_OT_DownloadREAssetLibrary(Operator):
	bl_label = "Download RE Asset Libraries"
	bl_description = "Download RE Asset Libaries"
	bl_idname = "re_asset.download_re_asset_library"
	bl_options = {'INTERNAL'}
	
		
	libraryListEntry: EnumProperty(
		name="RE Asset Library",
		description="Choose which asset library to download from the repository",
		items= getAssetDirectoryItems
		)
	assetLibList_items: bpy.props.CollectionProperty(type = REAssetLibEntryPropertyGroup)
	assetLibList_index: bpy.props.IntProperty(name="")
	def execute(self, context):
		if len(self.assetLibList_items) != 0:
			bpy.ops.wm.save_userpref()#Save preferences to prevent asset library path from being lost
			entry = self.assetLibList_items[int(self.libraryListEntry)]
			libraryDir = bpy.path.abspath(bpy.context.preferences.addons[__name__].preferences.assetLibraryPath)
			os.makedirs(libraryDir,exist_ok = True)
			outFilePath = os.path.join(libraryDir,f"{entry.gameName}.reassetlib")
			if os.path.isfile(outFilePath):#If the file has been downloaded before, remove it before starting the download again.
				try:
					os.remove(outFilePath)
				except Exception as err:
					print(f"Failed to delete existing .reassetlib file: {str(err)}")
			libCRC = int(entry.CRC)
			"""
			content = downloadFileContent(entry.URL)
			if content != None:
				with open(outFilePath,"wb") as outFile:
					outFile.write(content)
			"""
			for _,_ in download_file_from_google_drive(file_id=entry.URL,destination=outFilePath):
				pass
			if os.path.isfile(outFilePath):
				if libCRC == getFileCRC(outFilePath):
					print("CRC Check Passed")
					bpy.ops.re_asset.importlibrary(filepath = outFilePath)
					try:
						os.remove(outFilePath)
					except:
						pass
					
					
					self.report({"INFO"},tr_report("Downloaded {gameName} library. You can open the Asset Browser by going to File > New > RE Assets.", gameName=entry.gameName))
					
				else:
					print("CRC Check failed, aborting install.")
					self.report({"ERROR"},tr_report("CRC Check on the downloaded file failed. Try downloading the library again."))
				
		return {'FINISHED'}
		
	def invoke(self, context, event):
		self.assetLibList_items.clear()
		directoryDict = downloadREAssetLibDirectory()
		
		"""
		TESTPATH = r"D:\Modding\Monster Hunter Wilds\AssetLibrary\REAssetLib_directory.json"
		with open(TESTPATH,"r", encoding ="utf-8") as file:
			directoryDict = json.load(file)
		"""
		#directoryDict = None
		if directoryDict != None:
			#print(directoryDict)
			if directoryDict.get("libraryList"):
				libraryList = directoryDict.get("libraryList")
				for entry in libraryList:
					item = self.assetLibList_items.add()
					item.gameName = entry["gameName"]
					item.displayName = entry["displayName"]
					item.releaseDescription = entry.get("releaseDescription","")
					item.timestamp = entry["timestamp"]
					item.CRC = str(entry["CRC"])
					item.compressedSize = str(entry["compressedSize"])
					item.uncompressedSize = str(entry["uncompressedSize"])
					item.URL = entry["URL"]
			return context.window_manager.invoke_props_dialog(self,width = 400,confirm_text = tr_iface("Download Asset Library"))
		else:
			return context.window_manager.invoke_popup(self)

	def draw(self, context):
		layout = self.layout
		if len(self.assetLibList_items) != 0:
			layout.prop(self,"libraryListEntry")
		layout.separator()
		layout.label(text=tr_iface("Info"))
		box = layout.box()
		if len(self.assetLibList_items) != 0:
			entry = self.assetLibList_items[int(self.libraryListEntry)]
			box.label(text = tr_iface("Library Name: {gameName}", gameName=entry.gameName))
			
			box.separator()
			box.label(text = entry.releaseDescription)
			box.label(text = tr_iface("Last Update: {timestamp}", timestamp=entry.timestamp))
			
			box.label(text = tr_iface("Download Size: {size}", size=formatByteSize(int(entry.compressedSize))))
			box.label(text = tr_iface("Installed Size: {size}", size=formatByteSize(int(entry.uncompressedSize))))
			
			layout.label(text=tr_iface("Blender will become unresponsive while downloading the library."),icon = "ERROR")
		else:
			box.label(text = tr_iface("Failed to retrieve available asset libraries."))
			box.label(text = tr_iface("Check your internet connection."))
class WM_OT_CreateNewREAssetLibrary(Operator):
	bl_label = "Create New RE Asset Library"
	bl_description = "Create a new asset library using an RETool .list file"
	bl_idname = "re_asset.create_re_asset_library"
	bl_options = {'INTERNAL'}
	gameName: EnumProperty(
		name="",
		description="Set which game to create the library for",
		items= [
		("DMC5", "Devil May Cry 5", ""),
		("RE2", "Resident Evil 2", ""),
		("RE3", "Resident Evil 3", ""),
		("RE8", "Resident Evil 8", ""),	
		("RE2RT", "Resident Evil 2 Ray Tracing", ""),
		("RE3RT", "Resident Evil 3 Ray Tracing", ""),
		("RE7RT", "Resident Evil 7 Ray Tracing", ""),
		("MHRSB", "Monster Hunter Rise", ""),
		("SF6", "Street Fighter 6", ""),
		("RE4", "Resident Evil 4", ""),
		("DD2", "Dragon's Dogma 2", ""),
		("KG", "Kunitsu-Gami", ""),
		("DR", "Dead Rising", ""),
		("ONI2", "Onimusha 2", ""),
		("OWOTS", "Onimusha: Way of the Sword", ""),
		("PRAG", "Pragmata", ""),
		("MHWILDS", "Monster Hunter Wilds", ""),
		("MHS3", "Monster Hunter Stories 3", ""),
		("RE9", "Resident Evil 9", ""),#TODO Update this to pull the active game enum directly from the mesh editor mdf property group
		]
    )
	listPath: StringProperty(
		name="List Path",
		subtype='FILE_PATH',
		description = "Location of RE Tool .list file. Make sure to use the correct one for the game you set.\nIf you don't have a .list file, download one from the GitHub repo by pressing the Download List Files button below\nTip: You can shift right click the list file and click Copy as path, then paste it into this field",
		
	)
	def draw(self,context):
		layout = self.layout
		layout.prop(self,"gameName")
		layout.prop(self,"listPath")
		op = self.layout.operator(
        'wm.url_open',
        text=tr_iface('Download List Files'),
        icon='TEXT'
        )
		
		op.url = 'https://github.com/Ekey/REE.PAK.Tool/tree/main/Projects'
		
	@classmethod
	def poll(self,context):
		return context is not None
	def execute(self, context):
		
		newListPath = self.listPath.replace("\"","")
		if os.path.isfile(newListPath):
			#if os.path.isdir(bpy.context.preferences.addons[__name__].preferences.assetLibraryPath):
				newLibraryDir = os.path.join(bpy.path.abspath(bpy.context.preferences.addons[__name__].preferences.assetLibraryPath),self.gameName)
				bpy.ops.wm.save_userpref()#Save preferences to prevent asset library path from being lost
				os.makedirs(newLibraryDir,exist_ok=True)
				outputCatalogPath = os.path.join(newLibraryDir,f"REAssetCatalog_{self.gameName}.tsv")
				outputGameInfoPath = os.path.join(newLibraryDir,f"GameInfo_{self.gameName}.json")
				addonDir = os.path.split(__file__)[0]
				sourceBlendPath = os.path.join(addonDir,"Resources","Blend","libraryBase.blend")
				outputBlendPath = os.path.join(newLibraryDir,f"REAssetLibrary_{self.gameName}.blend")
				scriptPath = os.path.join(addonDir,"Resources","Scripts","initializeLibrary.py")
				
				whiteListSet = set()
				for item in bpy.context.preferences.addons[__name__].preferences.fileTypeWhiteList_items:
					whiteListSet.add(item.fileType.lower())
				
				REToolListFileToREAssetCatalogAndGameInfo(newListPath, outputCatalogPath, outputGameInfoPath,list(whiteListSet))
				shutil.copy(sourceBlendPath,outputBlendPath)
				if os.path.isfile(outputCatalogPath) and os.path.isfile(outputGameInfoPath) and os.path.isfile(outputBlendPath) and os.path.isfile(scriptPath):
					subprocess.Popen([bpy.app.binary_path, outputBlendPath, "--python", scriptPath])
				else:
					self.report({"ERROR"},tr_report("Missing files, cannot create library."))
					return {'CANCELLED'}
					self.report({"INFO"},tr_report("Created new RE Asset Library."))
				return {'FINISHED'}
				self.report({"INFO"},tr_report("Created new RE Asset Library."))
			#else:
				#self.report({"ERROR"},"Invalid asset library path.")
		else:
			self.report({"ERROR"},tr_report("Invalid list path."))
		
		return {'FINISHED'}
	
	def invoke(self,context,event):
		return context.window_manager.invoke_props_dialog(self)
class WM_OT_DetectREAssetLibrary(Operator):
	bl_label = "Refresh RE Asset Libraries"
	bl_description = "Check for any libraries that are not listed and add them to the list."
	bl_idname = "re_asset.detect_re_asset_library"
	bl_options = {'INTERNAL'}
	
	silent : BoolProperty(
	   name = "Silent",
	   description = "Don't report status after running",
	   default = False)	
	@classmethod
	def poll(self,context):
		return context is not None
	def execute(self, context):
		assetLibraryPath = bpy.path.abspath(bpy.context.preferences.addons[__name__].preferences.assetLibraryPath)
		
		if not os.path.isdir(assetLibraryPath):
			if not self.silent:
				self.report({"ERROR"},tr_report("Invalid RE asset library path."))
			return {'CANCELLED'}
		subDirectoryList = [ f.name for f in os.scandir(assetLibraryPath) if f.is_dir() ]
		for directory in subDirectoryList:
			if os.path.isfile(os.path.join(assetLibraryPath,directory,f"REAssetLibrary_{directory.upper()}.blend")):
				#Get existing library entry or make a new one
				libName = f"RE Assets - {directory.upper()}"
				library = getAssetLibrary(libName)
				library.name = libName
				library.path = os.path.join(assetLibraryPath,directory)
		for lib in bpy.context.preferences.filepaths.asset_libraries:#Remove any paths that don't exist
			if "RE Assets - " in lib.name and not os.path.isdir(lib.path):
				bpy.context.preferences.filepaths.asset_libraries.remove(lib)
		bpy.ops.wm.save_userpref()
		if not self.silent:
			self.report({"INFO"},tr_report("Refreshed RE Asset Library list."))
		return {'FINISHED'}
	
class WM_OT_OpenREAssetLibraryFolder(Operator):
	bl_label = "Open RE Asset Library Folder"
	bl_description = "Opens the folder containing RE Asset Libraries in File Explorer"
	bl_idname = "re_asset.open_re_asset_library_folder"

	def execute(self, context):
		try:
			openFolder(bpy.path.abspath(bpy.context.preferences.addons[__name__].preferences.assetLibraryPath))
		except:
			pass
		return {'FINISHED'}


class ASSETBROWSER_PT_REAssetToolPanel(Panel):
	bl_label = "RE Asset Library"
	bl_idname = "ASSETBROWSER_PT_REAssetToolPanel"
	bl_options = {"INSTANCED"}
	bl_space_type = "VIEW_3D"
	bl_region_type = "WINDOW"
	
	def draw(self, context):
		preferences = bpy.context.preferences.addons[__name__].preferences
		
		layout = self.layout
		libVersion = str(bl_info["version"][0])+"."+str(bl_info["version"][1])
		layout.label(text=tr_iface("RE Asset Library V{version}", version=libVersion))
		
		gameName = getGameNameFromAssetBrowser()
		
		if gameName != None:
			layout.label(text = tr_iface("Library: {gameName}", gameName=gameName))
			layout.operator("re_asset.set_game_extract_paths",icon = "CURRENT_FILE")
			layout.operator("re_asset.extract_game_files",icon = "DOCUMENTS")
			layout.operator("re_asset.open_chunk_extract_folder",icon = "FOLDER_REDIRECT")
			layout.operator("re_asset.reload_pak_cache",icon = "FILE_REFRESH")
			layout.operator("re_asset.check_for_library_update",icon="IMPORT")
			
		else:
			layout.separator()
			layout.label(text = tr_iface("No RE Asset library is selected."))
			layout.operator("re_asset.download_re_asset_library",icon = "INTERNET")
		layout.separator(type="LINE")
		layout.label(text = tr_iface("RE Asset Settings"))
		layout.prop(preferences,"showMeshImportOptions")
		layout.prop(preferences,"placeAtCursor")
		#layout.prop(self,"instanceDuplicates")#TODO
		layout.prop(preferences,"forceExtract")

class WM_OT_OpenFileLocation(Operator):
	bl_label = "Open Asset Location"
	bl_description = "Open the location the selected RE Asset is saved to.\nNote that the file has to be extracted to be able to find it's location"
	bl_idname = "re_asset_library.open_file_location"
	bl_context = "objectmode"
	bl_options = {'INTERNAL'}
	
	@classmethod
	def poll(self,context):
		return context.asset

	
	def execute(self, context):
		if context.asset:
			asset = context.asset
			#print(f"{asset.name=}")
			#print(f"{asset.metadata.description}")
			realPath = None
			filePath = asset.metadata.description.replace("/",os.sep).replace("\\",os.sep)
			libPath = asset.full_library_path
			if libPath == "":#current file
				libPath = bpy.context.blend_data.filepath
			#print(libPath)
			split = os.path.split(libPath)[1].split("REAssetLibrary_")
			if len(split) == 2:	
				
				gameName = split[1].split(".blend")[0].upper()
				chunkList = getChunkPathList(gameName)
				if len(chunkList) != 0:
					for chunkPath in chunkList:
						realPath = wildCardFileSearch(glob.escape(os.path.join(chunkPath,filePath))+".*")
						if realPath != None:
							openFolder(os.path.split(realPath)[0])
							self.report({"INFO"},tr_report("Opened file location."))
							break
						
					if realPath == None:
						self.report({"ERROR"},tr_report("File not found. It might not be extracted.\nDrag it from the library into the 3D view to extract it."))
				else:
					self.report({"ERROR"},tr_report("No chunk paths for {gameName} are present.", gameName=gameName))
			
			else:
				self.report({"ERROR"},tr_report("Asset is not an RE Asset."))
		
		return {'FINISHED'}
	
def re_asset_settings_button(self, context):
	self.layout.popover("ASSETBROWSER_PT_REAssetToolPanel",icon = "SETTINGS")
    #self.layout.operator(WM_OT_SetREAssetSettings.bl_idname,icon = "SETTINGS")
def re_asset_open_file_location_button(self, context):
    self.layout.operator(WM_OT_OpenFileLocation.bl_idname,icon = "FOLDER_REDIRECT")


execution_queue = queue.Queue()

def run_in_main_thread(function):
	execution_queue.put(function)
	if not bpy.app.timers.is_registered(execute_queued_functions):
		bpy.app.timers.register(execute_queued_functions, first_interval = 0.5)

def execute_queued_functions():
	while True:
		try:
			function = execution_queue.get_nowait()
		except queue.Empty:
			return None
		try:
			function()
		except Exception:
			traceback.print_exc()

def deleteLastREAsset():
	#print("Delete function run")
	if bpy.context.scene.get("lastREAsset"):#Object pointer stored in scene
		asset_obj = bpy.context.scene["lastREAsset"]
		del bpy.context.scene["lastREAsset"]#Clear reference
		deleteREAssetObject(asset_obj)
		#print(bpy.context.scene.get("lastREAsset") +" Deleted")

def deleteREAssetObject(asset_obj):
	if asset_obj is not None and asset_obj.name in bpy.data.objects:
		bpy.data.objects.remove(asset_obj, do_unlink=True)

def reportAssetImportError(message):
	print("RE Asset Library - " + message)
	if not bpy.app.background:
		showErrorMessageBox(message)

@persistent
def REAssetPostHandler(lapp_context):
	gameInfoPath = None
	gameInfo = None
	
	assetPath = None
	
	
	if len(lapp_context.import_items) == 1:#Make sure it's an asset drag and drop
		item = lapp_context.import_items[0]
		if item.id.get("~TYPE") == "RE_ASSET_LIBRARY_ASSET":
			addonPreferences = bpy.context.preferences.addons[__name__].preferences
			gameInfoPath = os.path.join(os.path.split(bpy.path.abspath(item.source_library.filepath))[0],"GameInfo_"+item.id.get("~GAME","UNKN")+".json")
			#print(gameInfoPath)
			if os.path.isfile(gameInfoPath):
				gameInfo = loadGameInfo(gameInfoPath)
			else:
				print(f"RE Asset Library - Missing GameInfo:{gameInfoPath}")
			assetType = item.id.get("assetType","UNKN")
			asset_obj = item.id
			
			promptSetExtractInfo = False
			pendingImport = None
			pendingImportDescription = str(item.id.get("assetPath",item.id.name))
			extractionFailed = False
			if gameInfo != None:
				
				#Find asset path
				chunkPathList = getChunkPathList(item.id.get("~GAME"))
				
				#if len(chunkPathList) == 0:
				#	promptSetExtractInfo = True
					#showErrorMessageBox("No chunk paths found for "+obj["~GAME"]+ " in RE Mesh Editor preferences.")
				#else:
				if len(chunkPathList) != 0:
					for chunkPath in chunkPathList:
						newPath = os.path.join(bpy.path.abspath(chunkPath),item.id.get("assetPath","MISSING_ASSET_PATH")+"."+gameInfo["fileVersionDict"].get(f"{assetType}_VERSION","UNKNOWNVERSION")).replace("/",os.sep).replace("\\",os.sep)
						print(f"Checking for file at: {newPath}")
						if os.path.isfile(newPath):
							assetPath = newPath
							print(f"Found asset path")
							break
				else:
					promptSetExtractInfo = True
				if assetPath == None or addonPreferences.forceExtract:
					extractInfoPath = os.path.join(os.path.split(bpy.path.abspath(item.source_library.filepath))[0],"ExtractInfo_"+item.id.get("~GAME","UNKN")+".json")
					pakCachePath = os.path.join(os.path.split(bpy.path.abspath(item.source_library.filepath))[0],"PakCache_"+item.id.get("~GAME","UNKN")+".pakcache")
					
					if not os.path.isfile(extractInfoPath):#File extraction is not set up
						promptSetExtractInfo = True
					else:
						if not promptSetExtractInfo and item.id.get("assetPath"):
							try:
								extractFilesFromPakCache(gameInfoPath,[],extractInfoPath,pakCachePath,extractDependencies = True,blenderAssetObj = item.id)
							except Exception as err:
								reportAssetImportError(tr_report("Failed to extract {assetPath}: {err}", assetPath=item.id.get('assetPath',item.id.name), err=err))
								assetPath = None
								extractionFailed = True
							if not extractionFailed:
								for chunkPath in chunkPathList:
									newPath = os.path.join(bpy.path.abspath(chunkPath),item.id.get("assetPath","MISSING_ASSET_PATH")+"."+gameInfo["fileVersionDict"].get(f"{assetType}_VERSION","UNKNOWNVERSION")).replace("/",os.sep).replace("\\",os.sep)
									print(f"Checking for file at: {newPath}")
									if os.path.isfile(newPath):
										assetPath = newPath
										print(f"Found asset path")
										break
							if assetPath == None:
								reportAssetImportError(tr_report("{assetPath} - File not found at any chunk paths. See console for details on how to fix this. (Window > Toggle System Console)", assetPath=item.id.get("assetPath",item.id.name)))
								print("\nIf this issue persists, try the following:")
								print("1: Check for updates to the asset library addon in Edit > Preferences > Addons > RE Asset Library > Check now for re_asset_library update.")
								print("2: Uninstall any mods installed with Fluffy Manager and validate game files on Steam.")
								print("3: In the RE Asset Library menu in the asset browser, click Set Game Extract Paths and set the paths again.")
								print("4: In the RE Asset Library menu in the asset browser, click Reload Pak Cache, then enable Force Extract Files.")
								print("5: Drag the file onto the 3D view again.")
								print("If it still does not work again after doing all of the above steps, please screenshot the output of the console when importing something from the asset browser and send it to me.\nAlso make sure you're not trying to extract DLC you don't have installed.\n")
			
				if assetPath != None:
					match assetType:
						case "MESH":
							pendingImport = lambda obj=asset_obj,path=str(assetPath),prefs=addonPreferences: importREMeshAsset(obj,path,prefs)
						case "CHAIN":
							pendingImport = lambda obj=asset_obj,path=str(assetPath),prefs=addonPreferences: importREChainAsset(obj,path,prefs)
						case "CHAIN2":
							pendingImport = lambda obj=asset_obj,path=str(assetPath),prefs=addonPreferences: importREChain2Asset(obj,path,prefs)
						case "FBXSKEL":
							pendingImport = lambda obj=asset_obj,path=str(assetPath),prefs=addonPreferences: importREFBXSkelAsset(obj,path,prefs)
						case "REFSKEL":
							pendingImport = lambda obj=asset_obj,path=str(assetPath),prefs=addonPreferences: importREFBXSkelAsset(obj,path,prefs)
						case "SKELETON":
							pendingImport = lambda obj=asset_obj,path=str(assetPath),prefs=addonPreferences: importREFBXSkelAsset(obj,path,prefs)
						case _:
							reportAssetImportError(tr_report("Unsupported asset type, cannot import {assetName} - {assetType}", assetName=item.id.name, assetType=assetType))
					
					
			bpy.context.scene["lastREAsset"] = asset_obj
			if pendingImport is not None:
				def queued_import(import_fn=pendingImport, description=pendingImportDescription):
					try:
						if import_fn() is False:
							reportAssetImportError(tr_report("Import failed for {description}", description=description))
					except Exception as err:
							reportAssetImportError(tr_report("Import failed for {description}: {err}", description=description, err=err))
				run_in_main_thread(queued_import)
			if promptSetExtractInfo:
				library_path = bpy.path.abspath(item.source_library.filepath)
				run_in_main_thread(lambda path=library_path: bpy.ops.re_asset.prompt_extract_info("INVOKE_DEFAULT",libraryPath = path))
			# Remove the temporary linked asset after the deferred import/prompt.
			run_in_main_thread(lambda obj=asset_obj: deleteREAssetObject(obj))
		
# Registration
classes = [
	REAssetWhiteListEntryPropertyGroup,
	ASSET_UL_FileTypeWhiteList,
	REAssetLibEntryPropertyGroup,
	ASSET_UL_REAssetLibList,
	LIST_OT_NewWhiteListItem,
	LIST_OT_DeleteWhiteListItem,
	LIST_OT_ResetWhiteListItems,
	REAssetPreferences,
	
	ToggleStringPropertyGroup,
	ASSET_UL_StringCheckList,
	
	WM_OT_PromptSetExtractInfo,
	WM_OT_SetExtractInfo,
	WM_OT_ExtractGameFiles,
	WM_OT_OpenExtractFolder,
	WM_OT_ReloadPakCache,
	WM_OT_CreatePakPatch,
	WM_OT_UnpackModPak,
	PAK_FH_drag_import,
	
	WM_OT_BatchMDFUpdater,
	WM_OT_BlenderMDFUpdater,
	
	WM_OT_BatchRSZUpdater,
	
	WM_OT_InitializeREAssetLibrary,
	WM_OT_DownloadREAssetLibrary,
	WM_OT_CreateNewREAssetLibrary,
	WM_OT_DetectREAssetLibrary,
	WM_OT_OpenREAssetLibraryFolder,
	WM_OT_CheckForREAssetLibraryUpdate,
	WM_OT_OpenLibraryFolder,
	WM_OT_GenerateMaterialCompendium,
	WM_OT_GenerateRSZCRCCompendium,
	
	ImportREAssetLib,
	
	
	WM_OT_OpenFileLocation,
	WM_OT_FetchREAssetThumbnails,
	WM_OT_ImportREAssetLibraryFromCatalog,
	WM_OT_SaveREAssetLibraryToCatalog,
	WM_OT_ExportCatalogDiff,
	WM_OT_ImportCatalogDiff,
	WM_OT_PackageREAssetLibrary,
	*REENGINE_BROWSER_CLASSES,
	OBJECT_PT_ExtractGameFilesPanel,
	OBJECT_PT_REAssetLibraryPanel,
	ASSETBROWSER_PT_REAssetToolPanel,
	
	
	]

_registered_classes = []

def on_register():
	if len(bpy.context.preferences.addons[__name__].preferences.fileTypeWhiteList_items) == 0:
		bpy.ops.re_asset.reset_whitelist_items()
	bpy.ops.re_asset.detect_re_asset_library(silent = True)#Save preferences on register, otherwise when a new blend file is opened, the addon might not be registered on the new instance.
def register():
	translations.register(__name__)
	addon_updater_ops.register(bl_info)
	for classEntry in classes:
		# CHANNELS panels only exist in the custom provider build. Official
		# Blender still needs all regular asset operators for batch workers.
		if (classEntry in REENGINE_BROWSER_CLASSES
			and getattr(classEntry, "bl_region_type", None) == "CHANNELS"
			and not is_reengine_browser_available()):
			continue
		bpy.utils.register_class(classEntry)
		_registered_classes.append(classEntry)
	# The custom provider is registered only after its action operators and
	# provider-scoped panel exist.  Blender's official builds simply return
	# False here and continue using the regular Asset Browser workflow.
	try:
		register_reengine_browser()
	except Exception as err:
		print(f"Failed to register RE Engine Extension Browser: {err}")
		
	bpy.types.ASSETBROWSER_MT_editor_menus.append(re_asset_settings_button)
	bpy.types.ASSETBROWSER_MT_editor_menus.append(re_asset_open_file_location_button)
	bpy.app.handlers.blend_import_post.append(REAssetPostHandler)
	bpy.app.timers.register(on_register, first_interval=.01)
	
	#Add RE Assets workspace under File > New
	addonDir = os.path.split(bpy.path.abspath(__file__))[0]
	WORKSPACE_SRC = os.path.join(addonDir,"Resources","Blend","REAssetWorkspace.blend")
	WORKSPACE_DEST = os.path.join(bpy.path.abspath(bpy.utils.script_path_user()), "startup","bl_app_templates_user","RE_Assets","startup.blend")
	
	try:
		os.makedirs(os.path.split(WORKSPACE_DEST)[0],exist_ok = True)
	except Exception as err:
		print(f"Failed to create RE Asset workspace folder {str(err)}")
	try:
		shutil.copy(WORKSPACE_SRC,WORKSPACE_DEST)
	except Exception as err:
		print(f"Failed to copy RE Asset workspace blend file {str(err)}")
	
def unregister():
	# Invalidate the provider before stopping its loopback server or removing
	# action operators and GPU preview resources.
	try:
		unregister_reengine_browser()
	except Exception as err:
		print(f"Failed to unregister RE Engine Extension Browser: {err}")
	translations.unregister(__name__)
	addon_updater_ops.unregister()
	for classEntry in reversed(_registered_classes):
		bpy.utils.unregister_class(classEntry)
	_registered_classes.clear()
	bpy.types.ASSETBROWSER_MT_editor_menus.remove(re_asset_settings_button)
	bpy.types.ASSETBROWSER_MT_editor_menus.remove(re_asset_open_file_location_button)
	if REAssetPostHandler in bpy.app.handlers.blend_import_post:
		bpy.app.handlers.blend_import_post.remove(REAssetPostHandler)
	
	#Removing on unregister causes issues when loading the workspace
	"""	
	WORKSPACE_DEST = os.path.join(bpy.path.abspath(bpy.utils.script_path_user()), "startup","bl_app_templates_user","RE_Assets","startup.blend")
	try:
		os.remove(WORKSPACE_DEST)
		#pass
	except:
		pass
	"""
if __name__ == '__main__':
	register()
