#
# Copyright (c) 2010-2014 Plex Development Team. All rights reserved.
#

import AudioFiles
import urllib
import re, os.path, random
from urllib import urlopen, quote
from xml.dom import minidom
from collections import Counter
import Media, AudioFiles, Utils
from Utils import SparseList, Log
from UnicodeHelper import toBytes
import mutagen
from hashlib import sha1

DEBUG = False

def Scan(path, files, mediaList, subdirs, language=None, root=None):

  # Scan for audio files.
  AudioFiles.Scan(path, files, mediaList, subdirs, root)
  root_str = root or ''
  loc_str = os.path.join(root_str, path)
  Log('Scanning:  ' + loc_str)
  Log('Files: ' + str(files))

  # Look at the files and determine whether we can do a quick match (minimal tag parsing).
  do_quick_match = True
  mixed = False

  # Make sure we're looking at a leaf directory (no audio files below here).
  if subdirs:
    Log('Found directories below this one; won\'t attempt quick matching.')
    do_quick_match = False

  if files:

    # Make sure we're not sitting in the section root.
    parentPath = os.path.split(files[0])[0]
    if parentPath == root:
      Log('File(s) are in section root; doing expensive matching with mixed content.')
      do_quick_match = False
      mixed = True

    # Make sure we have reliable track indices for all files and there are no dupes.
    tracks = SparseList()
    for f in files:
      try: 
        index = re.search(r'^([0-9]{1,2}).*',os.path.split(f)[-1]).groups(0)[0]
      except:
        do_quick_match = False
        Log('Couldn\'t find track indices in all filenames; doing expensive matching.')
        break
      if tracks[int(index)]:
        do_quick_match = False
        mixed = True
        Log('Found duplicate track index: %s; doing expensive matching with mixed content.' % index)
        break
      else:
        tracks[int(index)] = True

    artist = None
    album = None

    if do_quick_match:
      
      # See if we have some consensus on artist/album by reading a few tags.
      for i in range(3):
        if i < len(files):
          tags = mutagen.File(files[i], easy=True)

          this_artist = tags['artist'][0] if 'artist' in tags else tags['albumartist'][0] if 'albumartist' in tags else tags['TPE2'][0] if 'TPE2' in tags else None
          this_album = tags['album'][0] if 'album' in tags else None

          if artist and artist != this_artist:
            Log('Found different artists in tags (%s vs. %s); doing expensive matching.' % (artist, this_artist))
            do_quick_match = False
            break

          if album and album != this_album:
            Log('Found different albums in tags (%s vs. %s); doing expensive matching.' % (artist, this_artist))
            do_quick_match = False
            break

          artist = this_artist
          album = this_album
      
      if not artist or not album:
        Log('Couldn\'t determine unique artist or album from tags; doing expensive matching.')
        do_quick_match = False

    query_list = []
    result_list = []

    # Directory looks clean, let's build a query list directly from info gleaned from file names.
    if do_quick_match:
      Log('Building query list for quickmatch with artist: %s, album: %s' % (artist, album))

      # Determine if the artist and/or album appears in all filenames, since we'll want to strip these out for clean titles.
      strip_artist = True if len([f for f in files if artist.lower() in os.path.basename(f).decode('utf-8').lower()]) == len(files) else False
      strip_album = True if len([f for f in files if album.lower() in os.path.basename(f).decode('utf-8').lower()]) == len(files) else False

      for f in files:
        try:
          filename = os.path.splitext(os.path.split(f)[1])[0]
          (head, index, title) = re.split(r'^([0-9]{1,2})', filename)

          # Replace underscores and dots with spaces.
          title = re.sub(r'[_\. ]+', ' ', title)

          # Things in parens seem to confuse Gracenote, so let's strip them out.
          title = re.sub(r' ?\(.*\)', '', title)

          # Remove artist name from title if it appears in all of them.
          if strip_artist:
            title = re.sub(r'(?i)' + artist, '', title)

          # Remove album title from title if it appears in all of them.
          if strip_album:
            title = re.sub(r'(?i)' + album, '', title)

          # Remove any remaining index-, artist-, and album-related cruft from the head of the track title.
          title = re.sub(r'^[\W\-]+', '', title).strip()
      
          t = Media.Track(artist=artist, album=album, title=title, index=int(index))
          t.parts.append(f)

          Log('\tAdding: %s - %s' % (index, title))
          query_list.append(t)

        except Exception as e:
          Log('Error preparing tracks for quick matching: ' + str(e))
      
      lookup(query_list, result_list, language=language)

    # Otherwise, let's do old school directory crawling and tag reading for now (WiP).
    else:
      AudioFiles.Process(path, files, mediaList, subdirs, root)
      query_list = list(mediaList)
      lookup(query_list, result_list, language=language, fingerprint=True, mixed=mixed)

    del mediaList[:]
    for result in result_list:
      mediaList.append(result)

def lookup(query_list, result_list, language=None, fingerprint=False, mixed=False):

  # Build up the query with the contents of the query list.
  args = ''
  parts = {}
  for i, track in enumerate(query_list):
    
    # We need to pass at least a path and an identifier for each track that we know about.
    args += '&tracks[%d].path=%s' % (i, quote(track.parts[0],''))
    args += '&tracks[%d].userData=%d' % (i, i)
    
    # Keep track of the identifier -> part mapping so we can reassemble later.
    parts[i] = track.parts[0]

    if track.name:
      args += '&tracks[%d].title=%s' % (i, quote(toBytes(track.title or track.name),''))
    if track.artist and track.artist != 'Various Artists':
      args += '&tracks[%d].artist=%s' % (i, quote(toBytes(track.artist),''))
    if track.album_artist:
      args += '&tracks[%d].albumArtist=%s' % (i, quote(toBytes(track.album_artist),''))
    if track.album and track.album != '[Unknown Album]':
      args += '&tracks[%d].album=%s' % (i, quote(toBytes(track.album),''))
    if track.index:
      args += '&tracks[%d].index=%s' % (i, track.index)

  fingerprint = 1 if fingerprint else 0
  mixed = 1 if mixed else 0
  Log('Running Gracenote match with fingerprinting: %d and mixedContent: %d' % (fingerprint, mixed))
  url = 'http://127.0.0.1:32400/services/gracenote/search?fingerprint=%d&mixedContent=%d%s&lang=%s' % (fingerprint, mixed, args, language)
  try:
    res = minidom.parse(urlopen(url))
  except Exception, e:
    Log('Error parsing Gracenote response: ' + str(e))

  # See which tracks we got matches for.
  matched_tracks = {track.getAttribute('userData'): track for track in res.getElementsByTagName('Track')}

  # If we didn't match all tracks, or we got mixed artists/albums, redo with fingerprinting.
  unique_artists = len(set([t[1].getAttribute('grandparentTitle') for t in matched_tracks.items()]))
  unique_albums = len(set([t[1].getAttribute('parentTitle') for t in matched_tracks.items()]))
  unique_indices = len(set([t[1].getAttribute('index') for t in matched_tracks.items()]))

  if DEBUG:
    Log('Raw track matches:')
    for track in [match[1] for match in matched_tracks.items()]:
      Log(track.toxml())

  Log('Found %d unique artist(s) and %d unique album(s); matched %d of %d tracks with %d unique indices.' % (unique_artists, unique_albums, len(res.getElementsByTagName('Track')), len(query_list), unique_indices))
  if (len(matched_tracks) < len(query_list) or unique_artists > 1 or unique_albums > 1 or unique_indices != len(matched_tracks)) and fingerprint == False and mixed == False:
    Log('Re-running with fingerprinting.')
    lookup(query_list, result_list, language, True, mixed)
    return
  
  # Look through the results and determine some consensus metadata so we can do a better job of keeping rogue and unmatched tracks together.
  artist_consensus = Counter([(t[1].getAttribute('grandparentGUID'), t[1].getAttribute('grandparentTitle'), t[1].getAttribute('grandparentThumb')) for t in matched_tracks.items()]).most_common()[0][0]
  album_consensus = Counter([(t[1].getAttribute('parentGUID'), t[1].getAttribute('parentTitle'), t[1].getAttribute('parentThumb')) for t in matched_tracks.items()]).most_common()[0][0]
  year_consensus = Counter([t[1].getAttribute('year') for t in matched_tracks.items()]).most_common()[0][0]
  consensus_track = Media.Track(album_guid=album_consensus[0], album=album_consensus[1], album_thumb_url=album_consensus[2], disc='1', artist=artist_consensus[1], artist_guid=artist_consensus[0], artist_thumb_url=artist_consensus[2], year=year_consensus)
  
  # Add Gracenote results to the result_list where we have them.
  for i, query_track in enumerate(query_list):
    if str(i) in matched_tracks:
      try:
        track = matched_tracks[str(i)]

        # If the track index changed, and we didn't perfectly match everything, consider this a bad sign that something went wrong during fingerprint matching and abort.
        if query_track.index and int(track.getAttribute('index') or -1) != query_track.index and (len(matched_tracks) < len(query_list) or unique_albums > 1 or len(matched_tracks) != unique_indices):
          Log('Track index changed (%s -> %s) and match was not perfect, using merged hints.' % (query_track.index, track.getAttribute('index')))
          result_list.append(merge_hints(query_track, consensus_track, parts[i]))
          continue

        t = Media.Track(
              index = int(track.getAttribute('index')),
              album = toBytes(track.getAttribute('parentTitle')),
              artist = toBytes(track.getAttribute('originalTitle') or track.getAttribute('grandparentTitle')),
              title = toBytes(track.getAttribute('title')),
              disc = toBytes(track.getAttribute('parentIndex')),
              album_thumb_url = toBytes(track.getAttribute('parentThumb')),
              artist_thumb_url = toBytes(track.getAttribute('grandparentThumb')),
              year = toBytes(track.getAttribute('year')),
              guid = toBytes(track.getAttribute('guid')),
              album_guid = toBytes(track.getAttribute('parentGUID')),
              artist_guid = toBytes(track.getAttribute('grandparentGUID')))

        # Set the album_artist if we got a track artist and it differs from the album's primary contributor.
        if track.getAttribute('originalTitle') and track.getAttribute('grandparentTitle') != t.artist:
          t.album_artist = toBytes(track.getAttribute('grandparentTitle'))

        t.parts.append(parts[int(track.getAttribute('userData'))])

        if DEBUG:
          t.name = t.name + ' [GN MATCH]'
          if t.album_thumb_url == 'http://':
            t.album_thumb_url = 'https://dl.dropboxusercontent.com/u/8555161/no_album.png'
          if t.artist_thumb_url == 'http://':
            t.artist_thumb_url == 'https://dl.dropboxusercontent.com/u/8555161/no_artist.png'
          Log('Adding matched track: ' + str(t))

        result_list.append(t)

      except Exception, e:
        Log('Error adding track: ' + str(e))

    else:
      Log('Didn\'t get a track match for %s at path: %s' % ((query_track.title or query_track.name), query_track.parts[0]))
            
      if unique_albums == 1 and unique_artists == 1:
        Log('Other positive Gracenote matches were all from the same artist and album (%s, %s); merging with Gracenote hints.' % (consensus_track.artist, consensus_track.album))
        result_list.append(merge_hints(query_track, consensus_track, parts[i]))
      else:
        result_list.append(query_track)


def merge_hints(query_track, consensus_track, part):

  merged_track = Media.Track(
    index = int(query_track.index),
    album = toBytes(consensus_track.album),
    artist = toBytes(consensus_track.artist),
    title = toBytes(query_track.name),
    disc = toBytes(consensus_track.disc),
    year = toBytes(consensus_track.year),
    guid = toBytes('com.plexapp.agents.gracenote://track/' + sha1(query_track.name or query_track.title).hexdigest()),
    album_guid = toBytes(consensus_track.album_guid),
    artist_guid = toBytes(consensus_track.artist_guid))

  merged_track.parts.append(part)

  if DEBUG:
    # merged_track.album_thumb_url = 'https://dl.dropboxusercontent.com/u/8555161/no_album_match.png'
    # merged_track.artist_thumb_url = 'https://dl.dropboxusercontent.com/u/8555161/no_artist_match.png'
    merged_track.album_thumb_url = toBytes(consensus_track.album_thumb_url)
    merged_track.artist_thumb_url = toBytes(consensus_track.artist_thumb_url)
    merged_track.name = toBytes(merged_track.name + ' [MERGED GN MISS]')
    Log('Query track: ' + str(query_track))
    Log('Merged track: ' + str(merged_track))

  return merged_track
