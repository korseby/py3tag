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

# Fix librosa deprecation issues with numpy
np.complex = np.complex_
np.float = float
import librosa

# Use mutagen for reading tags
from mutagen.id3 import ID3, ID3NoHeaderError, PictureType, TPE1, TSOP, TPE2, TCOM, TALB, TSOA, TRCK, TIT2, TDRC, TCON, TBPM, TCMP, APIC, error
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Tags, MP4Info, MP4Cover, MP4FreeForm, AtomDataType

# Fix colors on windos
if sys.platform.lower() == "win32":
	os.system('color')



# -------------------- Global variables --------------------
# Parse arguments
parser = argparse.ArgumentParser(description='Writes tags to mp3, flac, and m4a files based on their filenames.')
parser.add_argument('-V', '--version', action='version', version='py3tag 1.2',
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



# -------------------- Print warning message in yellow --------------------
def WARNING(msg):
	print("\033[93m{}\033[00m" .format(msg), file=sys.stderr)



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
def bpm_count(audio_filename):
	# Example from http://librosa.github.io/librosa/generated/librosa.beat.tempo.html
	
	# Convert using audioread
	y, sr = audioread_load(path=audio_filename, offset=0.0, duration=None, dtype=np.float32)
	
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
		WARNING("Warning. No Cover.jpg in directory " + mp3_dirname + ".")
	
	# Save tags to file
	id3.save(mp3_filename, v2_version=4, v1=2)



# -------------------- Update flac tags --------------------
def flac_tag(flac_dirname, flac_filename, artist, album, track, tracks, title, year, genre, bpms, compilation):
	# Delete existing tags
	id3 = FLAC(flac_filename)
	id3.clear_pictures()
	id3.delete()
	
	# Artist, Composer
	id3["ARTIST"] = artist
	id3["ALBUM_ARTIST"] = artist
	id3["ALBUMARTIST"] = artist
	id3["COMPOSER"] = artist
	
	# Artistsort
	id3["SORT_ARTIST"] = artist
	id3["SORT_COMPOSER"] = artist
	id3["SORT_ALBUM_ARTIST"] = artist
	id3["ARTISTSORT"] = artist
	id3["ALBUMARTISTSORT"] = artist
	id3["COMPOSERSORT"] = artist
	id3["soar"] = artist
	id3["soaa"] = artist
	id3["soco"] = artist
	
	# Album
	id3["ALBUM"] = album
	
	# Albumsort
	id3["SORT_ALBUM"] = album
	id3["ALBUMSORT"] = album
	
	# Track
	id3["TRACKNUMBER"] = tracks
	id3["TRACK"] = tracks
	id3["DISCNUMBER"] = '1/1'
	
	# Title
	id3["TITLE"] = title
	
	# Year
	id3["YEAR_OF_RELEASE"] = year
	id3["DATE"] = year
	
	# Genre
	id3["GENRE"] = genre
	
	# BPMs
	id3["BPM"] = bpms
	id3["tmpo"] = bpms

	# Compilation
	if (compilation):
		id3["COMPILATION"] = '1'
	else:
		id3["COMPILATION"] = '0'
	
	# Cover
	id3.clear_pictures()
	try:
		image = Picture()
		image.data = open(str(flac_dirname + '/Cover.jpg'), 'rb').read()
		image.type = PictureType.COVER_FRONT
		image.mime = "image/jpeg"
		id3.add_picture(image)
	except:
		WARNING("Warning. No Cover.jpg in directory " + flac_dirname + ".")
	
	# Save tags to file
	id3.save(filename=flac_filename, deleteid3=True)



# -------------------- Update m4a tags --------------------
def m4a_tag(m4a_dirname, m4a_filename, artist, album, track, tracks, title, year, genre, bpms, compilation):
	# Print tags first
	#m4a = MP4(m4a_filename)
	#print(m4a.pprint())
	
	# Delete existing tags
	id3 = MP4Tags()
	id3.delete(m4a_filename)
	
	# Artist, Composer
	id3['\xa9ART'] = artist
	id3['aART'] = artist
	id3['\xa9wrt'] = artist
	
	# Artistsort
	id3['soaa'] = artist
	id3['soar'] = artist
	id3['soco'] = artist
	
	# Album
	id3['\xa9alb'] = album
	
	# Albumsort
	id3['soal'] = album
	
	# Track
	id3['trkn'] = [(int(track), int(re.sub(pattern='.*\/', repl='', string=tracks)))]
	id3['disk'] = [(1, 1)]
	
	# Title
	id3['\xa9nam'] = title
	id3['sonm'] = title
	
	# Year
	id3['\xa9day'] = year
	
	# Genre
	id3['\xa9gen'] = genre
	
	# BPMs, Gapless album
	id3['tmpo'] = [(int(round(float(bpms), 0)))]
	id3['pgap'] = True

	# Compilation
	if (compilation):
		id3['cpil'] = True
	else:
		id3['cpil'] = False
	
	# Cover
	try:
		with open(str(m4a_dirname + '/Cover.jpg'), 'rb') as f:
			id3["covr"] = [ MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG) ]
	except:
		WARNING("Warning. No Cover.jpg in directory " + m4a_dirname + ".")
	
	# Save tags to file
	id3.save(m4a_filename)



# -------------------- Process audio file --------------------
def process_audio(audio_filename):
	audio_basename = os.path.basename(audio_filename)
	audio_dirname = os.path.dirname(audio_filename)
	audio_suffix = re.sub(pattern='.*\.', repl='', string=str(audio_filename))
	
	with audioread.audio_open(audio_filename) as f:
		# Test audio file
		if (__DEBUG__): print('\nFile: %s' %(audio_filename))
		if (__DEBUG__): print('Info: %i channels, %i Hz, %.1f seconds.' %(f.channels, f.samplerate, f.duration))
		f.close()
		
		# Count BPM
		if (__BPM_DISABLED__ == False):
			# Convert audio to WAV
			bpms = bpm_count(audio_filename)
			bpms = str(round(bpms, 3))
		else:
			bpms = "0";
		
		# Update audio tags
		audio_info = audio_basename.split(" - ")
		if (len(audio_info) == 4):
			# Remove unwanted characters
			audio_info[0] = re.sub(pattern='.*/', repl='', string=audio_info[0])
			audio_info[-1] = re.sub(pattern='\..*', repl='', string=audio_info[-1])
			
			# Determine track number
			track = False
			for i in range(0, len(audio_info)):
				if ((audio_info[i].isdigit()) and ((len(audio_info[i])==2) or (len(audio_info[i])==3)) and (i != 0)):
					track = audio_info[i]
					break
			if (track == False):
				ERROR("Error: Track number in " + audio_filename + " could not be identified.")
				raise fragile.Break
			
			# Structure: Artist - Album - Track - Title
			if (audio_info.index(track) == 2):
				track_position = 2
				artist = audio_info[0]
				album = audio_info[1]
				title = audio_info[3]
				compilation = False
			# Structure: Compilation - Track - Artist - Title
			elif (audio_info.index(track) == 1):
				track_position = 1
				album = audio_info[0]
				artist = audio_info[2]
				title = audio_info[3]
				compilation = True
			else:
				ERROR("Error: Position of track " + audio_info.index(track) + " in " + audio_filename + " could not be identified.")
				raise fragile.Break
			
			# Get number of total tracks in path
			tracks = []
			audio_dirfiles = sorted(filter(lambda p: p.suffix in {".mp3", ".flac", ".m4a"}, Path(audio_dirname).glob("**/*")))
			for i in audio_dirfiles:
				audio_dirfile = os.path.basename(i)
				audio_dirinfo = audio_dirfile.split(" - ")
				tracks.append(audio_dirinfo[track_position])
			tracks = str(track + '/' + max(tracks))
			
			# Determine publication date (year)
			try:
				year = re.findall('\((.*?)\)', audio_dirname)
				year = re.sub(r'.* ', '', year[-1])
			except:
				WARNING("Warning: Could not extract year information from " + audio_filename + ". Setting to current year.")
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
				print(audio_basename)
			
			# Write tags to audio file
			if (__DRY_RUN__ == False):
				try:
					if (audio_suffix == "mp3"):
						mp3_tag(audio_dirname, audio_filename, artist, album, track, tracks, title, year, genre, bpms, compilation)
					elif (audio_suffix == "flac"):
						flac_tag(audio_dirname, audio_filename, artist, album, track, tracks, title, year, genre, bpms, compilation)
					elif (audio_suffix == "m4a"):
						m4a_tag(audio_dirname, audio_filename, artist, album, track, tracks, title, year, genre, bpms, compilation)
				except:
					ERROR("Error: Failed to write tags to " + audio_filename + ".")
					raise fragile.Break
		else:
			ERROR("Error: Names for tags in file " + audio_filename + " could not be detected.")
			raise fragile.Break



# -------------------- MAIN --------------------
if __name__ == "__main__" :
	# Iterate through acquired list of files
	files = list(flatten(args.files))
	
	audio_files = []
	
	for i in files:
		audio_files.extend(sorted(filter(lambda p: p.suffix in {".mp3", ".flac", ".m4a"}, Path(i).glob("**/*"))))
	audio_files = [str(Path(i)) for i in audio_files]
	
	# Multiprocessing
	if (__DEBUG__): print(f'Number of cores: {__CPU__}')
	
	# Process audio files
	pool = multiprocessing.Pool(processes=__CPU__)
	pool.map(func=process_audio, iterable=audio_files, chunksize=1)
	pool.close()
	pool.join()


