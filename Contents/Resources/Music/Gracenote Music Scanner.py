#
# Copyright (c) 2010-2014 Plex Development Team. All rights reserved.
#

import AudioFiles
import urllib
import re, os.path, random
from urllib import urlopen, quote
from xml.dom import minidom
import Media, AudioFiles, Utils
from Utils import SparseList, Log
from UnicodeHelper import toBytes

def Scan(path, files, mediaList, subdirs, language=None, root=None):

  # Scan for audio files.
  AudioFiles.Scan(path, files, mediaList, subdirs, root)
  root_str = root or ''
  loc_str = os.path.join(root_str, path)
  Log('Scanning:  ' + loc_str)
  Log('Files: ' + str(files))

  # Look at the files and determine whether we can do a quick match (minimal tag parsing).
  doQuickMatch = True
  mixed = False

  # Make sure we're looking at a leaf directory (no audio files below here).
  if subdirs:
    Log('Found directories below this one; won\'t attempt quick matching.')
    doQuickMatch = False

  if files:

    # Make sure we're not sitting in the section root.
    parentPath = os.path.split(files[0])[0]
    if parentPath == root:
      Log('File(s) are in section root; doing expensive matching with mixed content.')
      doQuickMatch = False
      mixed = True

    # Make sure we have reliable track indices for all files and there are no dupes.
    tracks = SparseList()
    for f in files:
      try: 
        index = re.search(r'^([0-9]{1,2}).*',os.path.split(f)[-1]).groups(0)[0]
      except:
        doQuickMatch = False
        Log('Couldn\'t find track indices in all filenames; doing expensive matching.')
        break
      if tracks[int(index)]:
        doQuickMatch = False
        mixed = True
        Log('Found duplicate track index: %d; doing expensive matching with mixed content.' % index)
        break
      else:
        tracks[int(index)] = True

    if doQuickMatch:
      
      # Try to extract artist and album from directory structure.
      artist = None
      album = None

      # First, see if we have a a parent that follows the 'artist - album' convention.  Stuff in square brackets tends to be junk.
      parent = os.path.split(parentPath)[1]
      if ' - ' in parent:
        artist = parent.split(' - ')[0]
        album = re.sub('\[.*\]', '', parent.split(' - ')[1])

      # If we have a grandparent directory that's not the section root or VA, use parent for album and grandparent for artist.
      else:
        grandparentPath = os.path.split(parentPath)[0]
        if grandparentPath != root and os.path.split(grandparentPath)[1] != 'Various Artists':
          artist = os.path.split(grandparentPath)[1]
          album = re.sub('\[.*\]', '', parent)
      
      if not artist or not album:
        Log('Couldn\'t determine unique artist or album from parent or grandparent directories; doing expensive matching.')
        doQuickMatch = False

    queryList = []
    resultList = []

    # Directory looks clean, let's build a query list directly from info gleaned from file and directory names.
    if doQuickMatch:
      Log('Building query list for quickmatch with artist: %s, album: %s' % (artist, album))
      for f in files:
        try:
          filename = os.path.splitext(os.path.split(f)[1])[0]
          (head, index, title) = re.split(r'^([0-9]{1,2})', filename)

          # Remove any remaining track-index-related cruft from the head of the track title.
          title = re.sub(r'^[\W\-]+', '', title).strip()

          # Replace underscores and dots with spaces.
          title = re.sub(r'[_\. ]+', ' ', title)
      
          t = Media.Track(artist=artist, album=album, title=title, index=int(index))
          t.parts.append(f)

          Log('\tAdding: %s - %s' % (index, title))
          queryList.append(t)

        except Exception as e:
          Log('Error preparing tracks for quick matching: ' + str(e))
      
      lookup(queryList, resultList, language)

    # Otherwise, let's do old school directory crawling and tag reading for now (WiP).
    else:
      AudioFiles.Process(path, files, mediaList, subdirs, root)
      queryList = list(mediaList)
      lookup(queryList, resultList, language, mixed)

    del mediaList[:]
    for result in resultList:
      mediaList.append(result)

def lookup(queryList, resultList, language=None, fingerprint=False, mixed=False):

  # Build up the query with the contents of the query list.
  args = ''
  parts = {}
  for i, track in enumerate(queryList):
    
    # We need to pass at least a path and an identifier for each track that we know about.
    args += '&tracks[%d].path=%s' % (i, quote(track.parts[0],''))
    args += '&tracks[%d].userData=%d' % (i, i)
    
    # Keep track of the identifier -> part mapping so we can reassemble later.
    parts[i] = track.parts[0]

    if track.name:
      args += '&tracks[%d].title=%s' % (i, quote(track.name,''))    
    if track.title:
      args += '&tracks[%d].title=%s' % (i, quote(track.title,''))
    if track.artist:
      args += '&tracks[%d].artist=%s' % (i, quote(track.artist,''))
    if track.album_artist:
      args += '&tracks[%d].albumArtist=%s' % (i, quote(track.album_artist,''))
    if track.album:
      args += '&tracks[%d].album=%s' % (i, quote(track.album,''))
    if track.index:
      args += '&tracks[%d].index=%s' % (i, track.index)

  fingerprint = 1 if fingerprint else 0
  mixed = 1 if mixed else 0
  url = 'http://127.0.0.1:32400/services/gracenote/search?fingerprint=%d&mixedContent=%d%s&lang=%s' % (fingerprint, mixed, args, language)
  try:
    res = minidom.parse(urlopen(url))
  except Exception, e:
    Log('Error parsing Gracenote response: ' + str(e))

  # See which tracks we got matches for.
  matched_tracks = {track.getAttribute('userData'): track for track in res.getElementsByTagName('Track')}

  # Add Gracenote results to the resultList where we have them.
  for i, query_track in enumerate(queryList):
    if str(i) in matched_tracks:
      try:
        track = matched_tracks[str(i)]
        t = Media.Track(
              index = int(track.getAttribute('index')),
              album = toBytes(track.getAttribute('parentTitle')),
              artist = toBytes(track.getAttribute('originalTitle')),
              title = toBytes(track.getAttribute('title')),
              album_thumb_url = toBytes(track.getAttribute('parentThumb')),
              artist_thumb_url = toBytes(track.getAttribute('grandparentThumb')),
              year = toBytes(track.getAttribute('year')),
              album_artist = toBytes(track.getAttribute('grandparentTitle')),
              guid = toBytes(track.getAttribute('guid')),
              album_guid = toBytes(track.getAttribute('parentGUID')),
              artist_guid = toBytes(track.getAttribute('grandparentGUID')))
        t.parts.append(parts[int(track.getAttribute('userData'))])
        resultList.append(t)
      except Exception, e:
        Log('Error adding track: ' + str(e))
    else:
      resultList.append(query_track)
