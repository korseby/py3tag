#!/usr/bin/env python

# Load modules
import os
import sys
import multiprocessing
import argparse
import errno
import glob
from pathlib import Path
from setuptools.namespaces import flatten
import re
import time
import audioread
import numpy as np
import librosa
from mutagen.id3 import ID3, ID3NoHeaderError, TPE1, TSOP, TPE2, TCOM, TALB, TSOA, TRCK, TIT2, TDRC, TCON, TBPM, TCMP, APIC, error

if sys.platform.lower() == "win32":
	os.system('color')



# -------------------- Global variables --------------------
# Parse arguments
parser = argparse.ArgumentParser(description='Writes tags to mp3 files based on their filenames.')
parser.add_argument('-V', '--version', action='version', version='py3tag 1.0',
				   help='Show version.')
parser.add_argument('-n', '--dry-run', dest='dryrun', action='store_true', required=False,
				   help='Do not do anything, just show what is being done.')
parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', required=False,
				   help='Be verbose and show what is being done.')
parser.add_argument('-b', '--disable-bpm', dest='bpm_disabled', action='store_true', required=False,
				   help='Disable BPM detection.')
parser.add_argument('-c', '--cpu', metavar='4', dest="cpu", default='0', type=int, required=False,
				   help='Number of cpu cores to use. Default is to use all detected cores and threads.')
parser.add_argument('-g', '--genre', metavar='Electronic', dest="genre", default='Electronic', type=str, required=False,
				   help='Genre that is being used. Default is Electronic.')
parser.add_argument(nargs='+', type=str, dest='files', action='append',
				   help='List of file(s) and/or directories.')

args = parser.parse_args()

# Verbosity
__DEBUG__ = args.verbose

# Dry-run
__DRY_RUN__ = args.dryrun

# BPM Detection
__BPM_DISABLED__ = args.bpm_disabled

# CPU Cores
__CPU__ = args.cpu
if (__CPU__) == 0: __CPU__ = multiprocessing.cpu_count()

# Default genre
genre = args.genre



# -------------------- Class: fragile --------------------
class fragile(object):
	class Break(Exception):
		"""Break out of the with statement"""
	
	def __init__(self, value):
		self.value = value
	
	def __enter__(self):
		return self.value.__enter__()
	
	def __exit__(self, etype, value, traceback):
		error = self.value.__exit__(etype, value, traceback)
		if etype == self.Break:
			return True
		return error



# -------------------- Print an error message in red --------------------
def ERROR(msg):
	print("\033[91m{}\033[00m" .format(msg), file=sys.stderr)



# -------------------- Load an audio buffer --------------------
def audioread_load(path, offset, duration, dtype):
	# using audioread (modified from librosa, originally ISC licensed)
	y = []
	with audioread.audio_open(path) as input_file:
		sr_native = input_file.samplerate
		n_channels = input_file.channels

		s_start = int(np.round(sr_native * offset)) * n_channels

		if duration is None:
			s_end = np.inf
		else:
			s_end = s_start + (int(np.round(sr_native * duration))
							   * n_channels)

		n = 0

		for frame in input_file:
			frame = librosa.util.buf_to_float(frame, dtype=dtype)
			n_prev = n
			n = n + len(frame)

			if n < s_start:
				# offset is after the current frame
				# keep reading
				continue

			if s_end < n_prev:
				# we're off the end.  stop reading
				break

			if s_end < n:
				# the end is in this frame.  crop.
				frame = frame[:s_end - n_prev]

			if n_prev <= s_start <= n:
				# beginning is in this frame
				frame = frame[(s_start - n_prev):]

			# tack on the current frame
			y.append(frame)
		
	if y:
		y = np.concatenate(y)
		
		# For non-mono files, reduce to one channel
		if n_channels > 1:
			y = y.reshape((-1, n_channels)).T
		
		# Force an audio signal buffer down to mono by averaging samples across channels
		if y.ndim > 1:
			y = np.mean(y, axis=0)
	else:
		y = np.empty(0, dtype=dtype)

	return y, sr_native



# -------------------- Count BPMs --------------------
def bpm_count(mp3_filename):
	# Example from http://librosa.github.io/librosa/generated/librosa.beat.tempo.html
	
	# Convert with audioread if necessary
	if (mp3_filename.lower().endswith("wav")) or (mp3_filename.lower().endswith("aif")) or (mp3_filename.lower().endswith("aiff")) or (mp3_filename.lower().endswith("flac")) or (mp3_filename.lower().endswith("flc")):
		y, sr = librosa.load(mp3_filename)
	else:
		y, sr = audioread_load(path=mp3_filename, offset=0.0, duration=None, dtype=np.float32)
	
	# Estimate a static tempo
	onset_env = librosa.onset.onset_strength(y, sr=sr)
	tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
	return(float(tempo))



# -------------------- Update mp3 tags --------------------
def mp3_tag(mp3_dirname, mp3_filename, artist, album, track, tracks, title, year, genre, bpms, compilation):
	# Delete existing tags
	try:
		id3 = ID3(mp3_filename)
		id3.delete()
	except ID3NoHeaderError:
		id3 = ID3()
	
	# Artist
	id3.add(TPE1(encoding=3, text=artist))
	
	# Artistsort
	id3.add(TSOP(encoding=3, text=artist))
	
	# Band
	id3.add(TPE2(encoding=3, text=artist))
	
	# Composer
	id3.add(TCOM(encoding=3, text=artist))
	
	# Album
	id3.add(TALB(encoding=3, text=album))
	
	# Albumsort
	id3.add(TSOA(encoding=3, text=album))
	
	# Track
	id3.add(TRCK(encoding=3, text=tracks))
	
	# Title
	id3.add(TIT2(encoding=3, text=title))
	
	# Year
	id3.add(TDRC(encoding=3, text=year))
	
	# Genre
	id3.add(TCON(encoding=3, text=genre))
	
	# BPMs
	id3.add(TBPM(encoding=3, text=bpms))

	# Compilation
	if (compilation):
		id3.add(TCMP(encoding=3, text='1'))
	else:
		id3.add(TCMP(encoding=3, text='0'))
	
	# Cover
	image = str(mp3_dirname + '/Cover.jpg')
	try:
		imagefile = open(image, 'rb').read()
		id3.add(APIC(3, 'image/jpeg', 3, 'Cover', imagefile))
	except:
		print("Warning. No Cover.jpg in directory " + mp3_dirname + ".")
	
	# Save tags to file
	id3.save(mp3_filename, v2_version=4, v1=2)



# -------------------- Process mp3 --------------------
def process_mp3(mp3_filename):
	mp3_basename = os.path.basename(mp3_filename)
	mp3_dirname = os.path.dirname(mp3_filename)
	
	try:
		with fragile(audioread.audio_open(mp3_filename)) as f:
			# Test mp3 file
			if (__DEBUG__): print('\nFile: %s' %(mp3_filename))
			if (__DEBUG__): print('Info: %i channels, %i Hz, %.1f seconds.' %(f.channels, f.samplerate, f.duration))
			f.close()
			
			# Count BPM
			if (__BPM_DISABLED__ == False):
				# Convert MP3 to WAV
				bpms = bpm_count(mp3_filename)
				bpms = str(round(bpms, 3))
			else:
				bpms = "0";
			
			# Update mp3 tags
			mp3_info = mp3_basename.split(" - ")
			if (len(mp3_info) == 4):
				# Remove unwanted characters
				mp3_info[0] = re.sub(pattern='.*/', repl='', string=mp3_info[0])
				mp3_info[-1] = re.sub(pattern='.mp3$', repl='', string=mp3_info[-1])
				
				# Determine track number
				track = False
				for i in range(0, len(mp3_info)):
					if ((mp3_info[i].isdigit()) and ((len(mp3_info[i])==2) or (len(mp3_info[i])==3)) and (i != 0)):
						track = mp3_info[i]
						break
				if (track == False):
					ERROR("Error: Track number in " + mp3_filename + " could not be identified.")
					raise fragile.Break
				
				# Structure: Artist - Album - Track - Title
				if (mp3_info.index(track) == 2):
					track_position = 2
					artist = mp3_info[0]
					album = mp3_info[1]
					title = mp3_info[3]
					compilation = False
				# Structure: Compilation - Track - Artist - Title
				elif (mp3_info.index(track) == 1):
					track_position = 1
					album = mp3_info[0]
					artist = mp3_info[2]
					title = mp3_info[3]
					compilation = True
				else:
					ERROR("Error: Position of track " + mp3_info.index(track) + " in " + mp3_filename + " could not be identified.")
					raise fragile.Break
				
				# Get number of total tracks in path
				tracks = []
				mp3_dirfiles = sorted([f for f in glob.glob(mp3_dirname + '/*.mp3')])
				for i in mp3_dirfiles:
					mp3_dirfile = os.path.basename(i)
					mp3_dirinfo = mp3_dirfile.split(" - ")
					tracks.append(mp3_dirinfo[track_position])
				tracks = str(track + '/' + max(tracks))
				
				# Determine publication date (year)
				try:
					year = re.findall('\((.*?)\)', mp3_dirname)
					year = re.sub(r'.* ', '', year[-1])
				except:
					print("Warning: Could not extract year information from" + mp3_filename + ". Setting to current year.")
					year = time.strftime("%Y")
				
				# Print out tags
				if (__DEBUG__):
					print("Artist: %s" %(artist))
					print("Album: %s" %(album))
					print("Tracks: %s" %(tracks))
					print("Title: %s" %(title))
					print("Year: %s" %(year))
					print("Genre: %s" %(genre))
					print("BPMs: %s" %(bpms))
					print("Compilation: %s" %(compilation))
				else:
					print(mp3_basename)
				
				# Write tags to mp3 file
				if (__DRY_RUN__ == False):
					try:
						mp3_tag(mp3_dirname, mp3_filename, artist, album, track, tracks, title, year, genre, bpms, compilation)
					except:
						ERROR("Error: Failed to write tags to " + mp3_filename + ".")
						raise fragile.Break
			else:
				ERROR("Error: Names for tags in file " + mp3_filename + " could not be detected.")
				raise fragile.Break
	except:
		ERROR("Error: File " + mp3_filename + " could not be decoded.")



# -------------------- MAIN --------------------
if __name__ == "__main__" :
	# Iterate through acquired list of files
	files = list(flatten(args.files))
	
	mp3_files = []
	
	for i in files:
		mp3_files.extend(sorted([f for f in glob.glob(i + '/**/*.mp3', recursive=True)]))
	
	# Multiprocessing
	if (__DEBUG__): print(f'Number of cores: {__CPU__}')
	
	# Process mp3 files
	pool = multiprocessing.Pool(processes=__CPU__)
	pool.map(func=process_mp3, iterable=mp3_files, chunksize=1)
	pool.close()
	pool.join()


