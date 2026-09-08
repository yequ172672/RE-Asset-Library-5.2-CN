#Author: NSA Cloud
import zstandard as zstd
import zlib
import os
import sys
from multiprocessing import Pool
import json

# This script runs as a standalone subprocess from the add-on.  Import the
# shared PAK reader so multiprocessing follows the same chunk semantics as
# the single-threaded and cache-backed paths.
MODULE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),"..",".."))
if MODULE_ROOT not in sys.path:
	sys.path.insert(0,MODULE_ROOT)
from modules.pak.re_pak_utils import readPakEntryData
from modules.pak.file_re_pak import ReadPakChunkTable

def pakExtractor(jobDict):
	jobIndex = jobDict["jobIndex"]
	#print(f"Extraction Job {str(jobIndex).zfill(2)} Started")
	#sys.stdout.flush()
	outDir = jobDict["outDir"]
	pakPath = jobDict["pakPath"]
	decompressorZSTD = zstd.ZstdDecompressor()
	chunkTable = None
	if any(entry.get("offsetType",0) == 1 for entry in jobDict["fileEntries"]):
		chunkTable = ReadPakChunkTable(pakPath)
	errors = []
	
	#decompressorDeflate = zlib.decompressobj(wbits=-zlib.MAX_WBITS)
	with open(pakPath,"rb") as pakStream:
		
		
		for entry in jobDict["fileEntries"]:
			try:
				fileData = readPakEntryData(entry,pakStream,chunkTable,decompressorZSTD)
				
				outPath = os.path.join(outDir,entry["filePath"])
				os.makedirs(os.path.split(outPath)[0],exist_ok=True)
				with open(outPath,"wb") as outFile:
					outFile.write(fileData)
			except Exception as err:
				message = "Failed to extract " + entry["filePath"] + f" {str(err)}"
				print(message)
				errors.append(message)
				
				#print(f"Extracted {outPath}")
			
	if errors:
		raise RuntimeError("; ".join(errors))
	#print(f" Extraction Job {str(jobIndex+1).zfill(2)} Finished")
	sys.stdout.write(f"Extraction Job {str(jobIndex+1).zfill(2)} Finished")
	sys.stdout.flush()
	return True

def runPakExtractJob(jobJSONPath):
	try:
		with open(jobJSONPath,"r", encoding ="utf-8") as file:
			jobJSONDict = json.load(file)
		print("Loaded job JSON.")
	except Exception as e:
		print(f"Error reading the extraction job JSON: {e}")
    # Create a pool of workers to extract the files in parallel
	print("Starting " + str(jobJSONDict["maxThreads"])+ " pak extraction jobs.")
	jobCount = len(jobJSONDict["jobList"])
	print(f"{jobCount} jobs to process.")
	
	print("\nThis may take a long time depending on the speed of your CPU and hard drive.")
	print("Don't worry if it looks stuck, it will finish eventually.\n")
	with Pool(processes=jobJSONDict["maxThreads"]) as pool:
		#print(jobJSONDict["jobList"])
		results = pool.imap_unordered(func=pakExtractor, iterable = jobJSONDict["jobList"],chunksize = 1)
		for i, results in enumerate(results):
			sys.stdout.write(f" ({i+1} of {jobCount})\n")
			sys.stdout.flush()
		
TEMPDIR = os.path.join(os.path.abspath(os.path.split(__file__)[0]),"TEMP")
JOB_JSON_NAME = os.path.join(TEMPDIR,"TEMP_PAK_EXTRACT_JOB.json")
if __name__ == '__main__':
	print("Subprocess started.")

	# Check if the file exists
	if os.path.isfile(JOB_JSON_NAME):
		runPakExtractJob(JOB_JSON_NAME)
	else:
		print(f"The file {os.path.split(JOB_JSON_NAME)[1]} does not exist.")
