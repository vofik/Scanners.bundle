#
# Copyright (c) 2010-2014 Plex Development Team. All rights reserved.
#

import re
import os.path
from urllib import urlopen, quote
from xml.dom import minidom
from collections import Counter, defaultdict
import Media
import AudioFiles
import mutagen
from Utils import Log, LevenshteinDistance, LevenshteinRatio
from UnicodeHelper import toBytes


DEBUG = True


def Scan(path, files, media_list, subdirs, language=None, root=None):

  # Scan for audio files.
  AudioFiles.Scan(path, files, media_list, subdirs, root)
  root_str = root or ''
  loc_str = os.path.join(root_str, path)
  Log('Scanning: ' + loc_str)
  Log('Files: ' + str(files))
  Log('Subdirs: ' + str(subdirs))

  # Look at the files and determine whether we can do a quick match (minimal tag parsing).
  do_quick_match = True
  mixed = False

  # Make sure we're looking at a leaf directory (no audio files below here).
  if subdirs:
    Log('Found directories below this one; won\'t attempt quick matching.')
    do_quick_match = False

  if files:

    # Make sure we're not sitting in the section root.
    parent_path = os.path.split(files[0])[0]
    if parent_path == root:
      Log('File(s) are in section root; doing expensive matching with mixed content.')
      do_quick_match = False
      mixed = True

    # Make sure we have reliable track indices for all files and there are no dupes.
    tracks = {}
    for f in files:
      try: 
        index = re.search(r'^([0-9]{1,2})[^0-9].*', os.path.split(f)[-1]).groups(0)[0]
      except:
        do_quick_match = False
        Log('Couldn\'t find track indices in all filenames; doing expensive matching.')
        break
      if tracks.get(index):
        do_quick_match = False
        mixed = True
        Log('Found duplicate track index: %s; doing expensive matching with mixed content.' % index)
        break
      else:
        tracks[index] = True

    # Make sure we are on the first disc.
    if do_quick_match:
      first_file = files[0]
      try:
        (artist, album, title, track, disc, album_artist, compil) = AudioFiles.getInfoFromTag(first_file, language)
        if disc is not None and disc > 1:
          Log('Skipping quick match because of non-first disc.')
          do_quick_match = False
      except:
        pass

    artist = None
    album = None

    if do_quick_match:
      Log('Doing quick match')
      
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
    fingerprint = False

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
          if strip_artist and len(files) > 2:
            title = re.sub(r'(?i)' + artist, '', title)

          # Remove album title from title if it appears in all of them.
          if strip_album and len(files) > 2:
            title = re.sub(r'(?i)' + album, '', title)

          # Remove any remaining index-, artist-, and album-related cruft from the head of the track title.
          title = re.sub(r'^[\W\-]+', '', title).strip()
      
          t = Media.Track(artist=toBytes(artist), album=toBytes(album), title=toBytes(title), index=int(index))
          t.parts.append(f)

          Log('\tAdding: %s - %s' % (index, title))
          query_list.append(t)

        except Exception as e:
          Log('Error preparing tracks for quick matching: ' + str(e))

    # Otherwise, let's do old school directory crawling and tag reading for now (WiP).
    else:
      AudioFiles.Process(path, files, media_list, subdirs, root)
      query_list = list(media_list)
      fingerprint = True
    
    # Preprocess for multi-discs.
    discs = preprocess_tracks(query_list)
    
    # OK, perform the lookup for each disc.
    match1 = albums1 = match2 = albums2 = 0
    for tracks in discs:
      (match, albums) = lookup(tracks, result_list, language=language, fingerprint=fingerprint, mixed=mixed)
      match1 += match
      albums1 += albums
      
    # If the match looked complicated, try it the other way.
    if albums1 > 1 or match1 < 75:
      match2 = albums2 = 0
      other_result_list = []
      for tracks in discs:
        (match, albums) = lookup(tracks, other_result_list, language=language, fingerprint=not fingerprint, mixed=mixed)
        match2 += match
        albums2 += albums
      
      if albums2 <= albums1 and match2 >= match1:
        Log('The other way was a better match, keeping.')
        result_list = other_result_list
        
    # If we have a crappy match, don't use it.
    if max(match1, match2) < 50.0:
      Log('That was terrible, let''s not use it')
      result_list = []

    # Finalize the results.
    del media_list[:]
    if len(result_list) > 0:
      # Gracenote results.
      for result in result_list:
        media_list.append(result)
    else:
      # We bailed during the GN lookup, fall back to tags.
      AudioFiles.Process(path, files, media_list, subdirs, root)

def preprocess_tracks(query_list):
  tracks_by_disc = defaultdict(list)
  
  # See if we have multiple disks, first checking tags.
  discs = set([t.disc for t in query_list if t.disc is not None])
  if len(discs) > 1:
    for t in query_list:
      tracks_by_disc[t.disc].append(t)
    return tracks_by_disc.values()
  
  # Otherwise, let's sort by filename, and see if we have clusters of tracks.
  sorted_tracks = sorted(query_list, key=lambda track: track.parts[0])
  disc = 1
  last_index = 0
  for t in sorted_tracks:
    if t.index < last_index:
      disc += 1
      if t.index != 1:
        Log("Disc %d didn't start with first track, we won't use this method." % disc)
        tracks_by_disc = defaultdict(list)
        break
    tracks_by_disc[disc].append(t)
    last_index = t.index
  
  if len(tracks_by_disc) > 1:
    return tracks_by_disc.values()
  
  # Otherwise, let's consider it a single disc.
  return [query_list]


def has_sane_track_indexes(query_list):
  indexes = []
  for track in query_list:
    indexes.append(track.index)
  
  # See if we have contiguous tracks.
  contiguous = True
  indexes.sort()
  for i, index in enumerate(indexes):
    if i + 1 != index:
      contiguous = False
      break
  
  # See if they're unique.
  unique = (len(query_list) == len(set(indexes)))

  return contiguous or unique


def lookup(query_list, result_list, language=None, fingerprint=False, mixed=False, multiple=False):

  # See if input looks like a sane album
  sane_input_tracks = has_sane_track_indexes(query_list)

  # Build up the query with the contents of the query list.
  args = ''
  parts = {}
  for i, track in enumerate(query_list):
    
    # We need to pass at least a path and an identifier for each track that we know about.
    args += '&tracks[%d].path=%s' % (i, quote(track.parts[0], ''))
    args += '&tracks[%d].userData=%d' % (i, i)
    
    # Keep track of the identifier -> part mapping so we can reassemble later.
    parts[i] = track.parts[0]

    if track.name:
      args += '&tracks[%d].title=%s' % (i, quote(toBytes(track.title or track.name), ''))
    if track.artist and track.artist != 'Various Artists':
      args += '&tracks[%d].artist=%s' % (i, quote(toBytes(track.artist), ''))
    if track.album_artist:
      args += '&tracks[%d].albumArtist=%s' % (i, quote(toBytes(track.album_artist), ''))
    if track.album and track.album != '[Unknown Album]':
      args += '&tracks[%d].album=%s' % (i, quote(toBytes(track.album), ''))
    if track.index:
      args += '&tracks[%d].index=%s' % (i, track.index)
    if track.disc:
      args += '&tracks[%d].parentIndex=%s' % (i, track.disc)

  Log('Running Gracenote match with fingerprinting: %d and mixedContent: %d and multiple: %d' % (fingerprint, mixed, multiple))
  url = 'http://127.0.0.1:32400/services/gracenote/search?fingerprint=%d&mixedContent=%d&multiple=%d%s&lang=%s' % (fingerprint, mixed, multiple, args, language)
  try:
    res = minidom.parse(urlopen(url))
  except Exception, e:
    Log('Error parsing Gracenote response: ' + str(e))
    return (0, 0)

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

  # Look through the results and determine some consensus metadata so we can do a better job of keeping rogue and 
  # unmatched tracks together. We're going to weight matches in the first third of the tracks twice as high, for 
  # cases in which matches come through for the last half of tracks.
  #
  sorted_items = sorted(matched_tracks.items(), key= lambda t: int(t[1].getAttribute('parentIndex') or 1)*100 + int(t[1].getAttribute('index') or -1))
  sorted_items = sorted_items[0:len(sorted_items)/3] + sorted_items
  
  artist_list = [(t[1].getAttribute('grandparentGUID'), t[1].getAttribute('grandparentTitle'), t[1].getAttribute('grandparentThumb')) for t in sorted_items]
  artist_consensus = Counter(artist_list).most_common()[0][0] if len(artist_list) > 0 else ('', '', '')

  album_list = [(t[1].getAttribute('parentGUID'), t[1].getAttribute('parentTitle'), t[1].getAttribute('parentThumb')) for t in sorted_items]
  album_consensus = Counter(album_list).most_common()[0][0] if len(album_list) > 0 else ('', '', '')
  
  year_list = [t[1].getAttribute('year') for t in sorted_items]
  year_consensus = Counter(year_list).most_common()[0][0] if len(year_list) > 0 else -1

  if DEBUG:
    Log('Found artists: ' + str(Counter(artist_list).most_common()))
    Log('Found albums: ' + str(Counter(album_list).most_common()))
    Log('Found years: ' + str(Counter(year_list).most_common()))
  
  consensus_track = Media.Track(album_guid=album_consensus[0], album=album_consensus[1], album_thumb_url=album_consensus[2], disc='1', artist=artist_consensus[1], artist_guid=artist_consensus[0], artist_thumb_url=artist_consensus[2], year=year_consensus)

  # Add Gracenote results to the result_list where we have them.
  tracks_without_matches = []
  perfect_matches = 0
  
  for i, query_track in enumerate(query_list):
    if str(i) in matched_tracks:
      try:
        track = matched_tracks[str(i)]

        # Index doesn't match and disc doesn't match.
        Log("Checking (%s -> %s) and track (%s -> %s) mismatched, we're going to treat this as a bad match." % (query_track.disc, track.getAttribute('parentIndex'), int(track.getAttribute('index') or -1), query_track.index))
        if (query_track.index and int(track.getAttribute('index') or -1) != query_track.index) and (query_track.disc and track.getAttribute('parentIndex') and query_track.disc != track.getAttribute('parentIndex')):
          Log("Both disc (%s -> %s) and track (%s -> %s) mismatched, we're going to treat this as a bad match." % (query_track.disc, track.getAttribute('parentIndex'), int(track.getAttribute('index') or -1), query_track.index))
          tracks_without_matches.append((query_track, parts[i]))
          continue

        # If the track index changed, and we didn't perfectly match everything, consider this a bad sign that something
        # went wrong during fingerprint matching and abort.
        #
        if (not query_track.index or query_track.index and int(track.getAttribute('index') or -1) != query_track.index) and (len(matched_tracks) < len(query_list) or unique_albums > 1 or len(matched_tracks) != unique_indices):
          Log('Track index changed (%s -> %s) and match was not perfect, using merged hints.' % (query_track.index, track.getAttribute('index')))
          result_list.append(merge_hints(query_track, consensus_track, parts[i]))
          continue

        # If we had sane input, but some tracks got put into a different album, don't allow that.
        if sane_input_tracks and track.getAttribute('parentGUID') != consensus_track.album_guid:
          Log('Had sane input but track %s got split, using merged hints.' % track.getAttribute('index'))
          result_list.append(merge_hints(query_track, consensus_track, parts[i]))
          continue

        t = Media.Track(
          index=int(track.getAttribute('index')),
          album=toBytes(track.getAttribute('parentTitle')),
          artist=toBytes(track.getAttribute('originalTitle') or track.getAttribute('grandparentTitle')),
          title=toBytes(track.getAttribute('title')),
          disc=toBytes(track.getAttribute('parentIndex')),
          album_thumb_url=toBytes(track.getAttribute('parentThumb')),
          artist_thumb_url=toBytes(track.getAttribute('grandparentThumb')),
          year=toBytes(track.getAttribute('year')),
          guid=toBytes(track.getAttribute('guid')),
          album_guid=toBytes(track.getAttribute('parentGUID')),
          artist_guid=toBytes(track.getAttribute('grandparentGUID')))

        # Set the album_artist if we got a track artist and it differs from the album's primary contributor.
        if track.getAttribute('originalTitle') and toBytes(track.getAttribute('grandparentTitle')) != t.artist:
          t.album_artist = toBytes(track.getAttribute('grandparentTitle'))

        t.parts.append(parts[int(track.getAttribute('userData'))])

        if DEBUG:
          t.name += ' [GN MATCH]'
          if t.album_thumb_url == 'http://':
            t.album_thumb_url = 'https://dl.dropboxusercontent.com/u/8555161/no_album.png'
          if t.artist_thumb_url == 'http://':
            t.artist_thumb_url = 'https://dl.dropboxusercontent.com/u/8555161/no_artist.png'
          Log('Adding matched track: ' + str(t))

        result_list.append(t)
        perfect_matches += 1

      except Exception, e:
        Log('Error adding track: ' + str(e))

    else:
      Log('Didn\'t get a track match for %s at path: %s' % ((query_track.title or query_track.name), query_track.parts[0]))

      if unique_albums == 1 and unique_artists == 1:
        Log('Other positive Gracenote matches were all from the same artist and album (%s, %s); merging with Gracenote hints.' % (consensus_track.artist, consensus_track.album))
        result_list.append(merge_hints(query_track, consensus_track, parts[i]))
      else:
        Log('No matches, just appending query track')
        tracks_without_matches.append((query_track, parts[i]))
        
  # Now consider the unmatched tracks. If they were the minority, then just merge them in.
  if len(tracks_without_matches) / float(len(query_list)) < 0.3:
    Log('Minority of tracks were unmatched, hooking them back up.')
    result_list.extend([merge_hints(tup[0], consensus_track, tup[1]) for tup in tracks_without_matches])
  else:
    Log('The majority of tracks were unmatched, letting them be.')
    result_list.extend([tup[0] for tup in tracks_without_matches])
    
  # Last, but not least, let's clean up the results. Multi-disc album titles have cruft in them.
  for t in result_list:
    t.album = re.sub('[ \-:]*\[*disc [0-9]\][ \-]*', '', t.album, flags=re.IGNORECASE).strip()

  # Compute a score.
  match_percentage = (perfect_matches / float(len(query_list))) * 100.0
  number_of_albums = len(set([track.album_guid for track in result_list]))
  
  Log("STAT MATCH PERCENTAGE: %f" % match_percentage)
  Log("STAT ALBUMS MATCHED: %d" % number_of_albums)
  
  return (match_percentage, number_of_albums)

def merge_hints(query_track, consensus_track, part):

  merged_track = Media.Track(
    index=int(query_track.index) if query_track.index is not None else -1,
    album=toBytes(consensus_track.album),
    artist=toBytes(consensus_track.artist),
    title=toBytes(query_track.name),
    disc=toBytes(consensus_track.disc),
    year=toBytes(consensus_track.year),
    album_guid=toBytes(consensus_track.album_guid),
    artist_guid=toBytes(consensus_track.artist_guid))

  merged_track.parts.append(part)

  if DEBUG:
    # merged_track.album_thumb_url = 'https://dl.dropboxusercontent.com/u/8555161/no_album_match.png'
    # merged_track.artist_thumb_url = 'https://dl.dropboxusercontent.com/u/8555161/no_artist_match.png'
    merged_track.album_thumb_url = toBytes(consensus_track.album_thumb_url)
    merged_track.artist_thumb_url = toBytes(consensus_track.artist_thumb_url)
    merged_track.name = toBytes(merged_track.name + ' [MERGED GN MISS]')
    Log('Query track: ', toBytes(query_track))
    Log('Consensus track: ', toBytes(consensus_track))
    Log('Merged track: ', toBytes(merged_track))

  return merged_track
