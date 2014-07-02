#
# Copyright (c) 2010-2014 Plex Development Team. All rights reserved.
#

<<<<<<< HEAD
import AudioFiles
import urllib
=======
import re, os.path
from urllib import urlopen, quote
>>>>>>> First steps toward optimizing GN scanner (WIP).
from xml.dom import minidom
import Media, AudioFiles, Utils
from UnicodeHelper import toBytes

def Scan(path, files, mediaList, subdirs, language=None, root=None):

  # Scan for audio files.
  AudioFiles.Scan(path, files, mediaList, subdirs, root)

  # Look at the files and determine whether we can do a quick match (minimal tag parsing).
  doQuickMatch = True

  # Make sure we're looking at a leaf directory (no audio files below here).
  if subdirs:
    print 'Found music files below this directory; won\'t attempt quick matching.'
    doQuickMatch = False

  # Make sure we have reliable track indices for all files and there are no dupes.
  if files:
    tracks = Utils.SparseList()
    for f in files:
      try: 
        index = re.search(r'^([0-9]{1,2}).*',os.path.split(f)[-1]).groups(0)[0]
      except: 
        doQuickMatch = False
        print 'Couldn\'t find track indices in all filenames; doing expensive matching.'
      if tracks[int(index)]:
        doQuickMatch = False
        print 'Found duplicate track index: %d; doing expensive matching.' % int(index)
      else:
        tracks[int(index)] = True

    # Make sure we're not sitting in the section root.
    parentPath = os.path.split(files[0])[0]
    if parentPath == root:
      print 'File(s) are in section root; doing expensive matching.'
      doQuickMatch = False

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
      print 'Couldn\'t determine unique artist or album from parent or grandparent directories; doing expensive matching.'
      doQuickMatch = False

    queryList = []
    resultList = []

    # Directory looks clean, let's build a query list directly from info gleaned from file and directory names.
    if doQuickMatch:
      print 'Building query list for quickmatch with artist: %s, album: %s' % (artist, album)
      for f in files:
        try:
          filename = os.path.splitext(os.path.split(f)[1])[0]
          (head, index, title) = re.split(r'^([0-9]{1,2})', filename)
          title = re.sub(r'[_\-\.]','',title).strip()
      
          t = Media.Track(artist=artist, album=album, title=title, index=int(index))
          t.parts.append(f)

          print '\tAdding: %s - %s' % (index, title)
          queryList.append(t)

        except Exception as e:
          print str(e)
      
      lookup(queryList, resultList, language)

    # Otherwise, let's do old school directory crawling and tag reading for now (WiP).
    else:
      AudioFiles.Process(path, files, mediaList, subdirs, root)
      queryList = list(mediaList)
      lookup(queryList, resultList, language)

    # print 'query list: ' + str(queryList)
    # print 'result list: ' + str(resultList)
    # print 'media list: ' + str(mediaList)

    for track in resultList:
      mediaList.append(track)

def lookup(queryList, resultList, language=None, fingerprint=False, mixed=False):

  # Build up the query with the contents of the query list.
  args = ''
  parts = {}
  for i, track in enumerate(queryList):
    
    # We need to pass at least a path and an identifier for each track that we know about.
    args += '&tracks[%d].path=%s' % (i, quote(track.parts[0],''))
    args += '&tracks[%d].userData=%d' % (i, track.index)
    
    # Keep track of the identifier -> part mapping so we can reassemble later.
    parts[track.index] = track.parts[0]
    
    if track.title:
      args += '&tracks[%d].title=%s' % (i, quote(track.name,''))
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

  print 'Requesting: ' + url
  res = minidom.parse(urlopen(url))
  print 'Got result: \n' + res.toprettyxml()
  # Add the results to the result list.
  for track in res.getElementsByTagName('Track'):
    try:
<<<<<<< HEAD

      index = int(track.getAttribute('userData'))

      if mediaList[index].album != track.getAttribute('parentTitle'):
        print 'updating album: ' + mediaList[index].album + ' -> ' + track.getAttribute('parentTitle')
        mediaList[index].album = track.getAttribute('parentTitle')

      if mediaList[index].artist != track.getAttribute('originalTitle'):
        print 'updating track artist: ' + mediaList[index].artist + ' -> ' + track.getAttribute('originalTitle')
        mediaList[index].artist = track.getAttribute('originalTitle')

      if mediaList[index].title != track.getAttribute('title'):
        print 'updating title: ' + mediaList[index].title + ' -> ' + track.getAttribute('title')
        mediaList[index].title = track.getAttribute('title')

      if str(mediaList[index].index) != track.getAttribute('index'):
        print 'updating index: ' + str(mediaList[index].index) + ' -> ' + track.getAttribute('index')
        mediaList[index].index = int(track.getAttribute('index'))

      if str(mediaList[index].year) != track.getAttribute('year'):
        print 'updating year: ' + str(mediaList[index].year) + ' -> ' + track.getAttribute('year')
        mediaList[index].year = int(track.getAttribute('year'))

      if mediaList[index].album_artist != track.getAttribute('grandparentTitle') and mediaList[index].album_artist:
        print 'updating album artist: ' + mediaList[index].album_artist + ' -> ' + track.getAttribute('grandparentTitle')
        mediaList[index].album_artist = track.getAttribute('grandparentTitle')

      print 'guid: ' + track.getAttribute('guid')
      mediaList[index].guid = str(track.getAttribute('guid'))

      print 'parent guid: ' + track.getAttribute('parentGUID')
<<<<<<< HEAD
      mediaList[index].album_guid = str(track.getAttribute('parentGUID'))
=======
      mediaList[index].album_guid = toBytes(track.getAttribute('parentGUID'))

      print 'grandparent guid: ' + track.getAttribute('grandparentGUID')
      mediaList[index].artist_guid = toBytes(track.getAttribute('grandparentGUID'))

      print 'final hints: ' + str(mediaList[index])
>>>>>>> Add language to search request, pass up artist_guid.

=======
      t = Media.Track(
            index = int(track.getAttribute('userData')),
            album = toBytes(track.getAttribute('parentTitle')),
            artist = toBytes(track.getAttribute('originalTitle')),
            title = toBytes(track.getAttribute('title')),
            year = toBytes(track.getAttribute('year')),
            album_artist = toBytes(track.getAttribute('grandparentTitle')),
            guid = toBytes(track.getAttribute('guid')),
            album_guid = toBytes(track.getAttribute('parentGUID')),
            artist_guid = toBytes(track.getAttribute('grandparentGUID')))
      t.parts.append(parts[int(track.getAttribute('userData'))])
      resultList.append(t)
>>>>>>> Fixes and more progress on fast scanning.
    except Exception, e:
      print str(e)
