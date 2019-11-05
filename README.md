# py3tag
Write tags to mp3 files based on their filenames.

To facilitate the tagging of mp3 files, tags can be generated automatically from the filename of the mp3 file. Since Napster there are some conventions how to properly name mp3 files - which are followed by this script.

For each album of compilation, the script expects an own directory. For albums the scheme `Artist - Album - Tracknumber - Title.mp3` is used whereas for compilations `Album - Tracknumber - Artist - Title.mp3` is used. The script automatically determines the total number of tracks that exist within the directory. Compilation tags used by iTunes are automatically set based on the scheme. If enabled, the script also calculates the BPMs by using the Python library librosa. If `Cover.jpg` exists in the directory it is used as the cover picture for the mp3.

## Version
1.0

## Usage

```
usage: py3tag.py [-h] [-V] [-n] [-v] [-b] [-g Electronic] files [files ...]

Writes tags to mp3 files based on their filenames.

positional arguments:
  files                 List of file(s) and/or directories.

optional arguments:
  -h, --help            show this help message and exit
  -V, --version         Show version.
  -n, --dry-run         Do not do anything, just show what is being done.
  -v, --verbose         Be verbose and show what is being done.
  -b, --disable-bpm     Disable BPM detection.
  -g Electronic, --genre Electronic
                        Genre that is being used. Default is Electronic.
```

## Dependencies
The following Python libraries are needed to run the script. They can be best installed via pip.

* audioread
* numpy
* librosa
* mutagen

## Changes

### Version 1.0:
- initial version

## License
BSD-3
