#
# Copyright (c) 2010-2014 Plex Development Team. All rights reserved.
#

import AudioFiles
import urllib
from xml.dom import minidom

def Scan(path, files, mediaList, subdirs, language=None, root=None):

  # Scan for audio files.
  AudioFiles.Scan(path, files, mediaList, subdirs, root)

  # Read tags, etc. and build up the mediaList
  AudioFiles.Process(path, files, mediaList, subdirs, root)

  # Run the Gracenote search and add the GNID hint if we get one.
  args = {}
  for i, track in enumerate(mediaList):
    args['tracks[%d].path' % i]        = track.parts[0]
    args['tracks[%d].userData' % i]    = i
    args['tracks[%d].track' % i]       = track.name
    args['tracks[%d].artist' % i]      = track.artist
    args['tracks[%d].albumArtist' % i] = track.album_artist
    args['tracks[%d].album' % i]       = track.album
    args['tracks[%d].index' % i]       = track.index
    args['lang']                       = language

  querystring = urllib.urlencode(args).replace('%5B','[').replace('%5D',']')
  url = 'http://127.0.0.1:32400/services/gracenote/search?fingerprint=1&' + querystring
  res = minidom.parse(urllib.urlopen(url))

  for track in res.getElementsByTagName('Track'):
    try:

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

    except Exception, e:
      print str(e)
