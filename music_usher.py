#!/usr/bin/env python
'''Organise music/audio files libraries.

This script takes in a directory of audio files and copies/moves
the files to another directory organising them in the following
directory structure:

    Artists > Albums > Track Number. Track Name

At the top level of the destination directory will be the Artists'
directories, each of which will contain Albums that contain the
audio files.

NOTE: Module organises mp3 and ogg files only.
'''
import logging
import re
import os
import shutil

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError


LOGGER = logging.getLogger(__name__)

MEDIA_FILES_REGEX = re.compile(r'.*\.(mp3|ogg)$', re.IGNORECASE)

DRY_RUN = False
MOVE_EXPORT = False     # Move files in export else just copy them


class Library:

    def __init__(self, path, autoload=True):
        LOGGER.debug('Initialising library: %s', path)
        self.path = path
        self.discographies = {}   # Map of artist to their Discographies
        if autoload: self.load()

    def load(self):
        LOGGER.debug('Loading files from %s', self.path)
        for parent_dir, _dirs, files in os.walk(self.path):
            LOGGER.debug('Loading media files in sub directory: %s', parent_dir)
            files = filter(lambda f: MEDIA_FILES_REGEX.match(f), files)
            for file_ in files:
                track = Track(os.path.join(parent_dir, file_))
                track_artist = track.get_artist()
                track_album = track.get_album()
                discography = self.get_discography(track_artist, create=True)
                album = discography.get_album(track_album, create=True)
                album.add(track)

    def export(self, path):
        '''Write library to specified directory.

        The library is written in the following organisation:
            Artist > Album > Track Number. Track Name

        NOTE: All conflicting tracks found, have a number appended to their
        name as in:

            Track Number. Track Name (1)
        '''
        LOGGER.debug('Exporting library to %s', path)
        if not os.path.isdir(path):
            LOGGER.debug('Creating library directory: %s')
            if not DRY_RUN: os.makedirs(path)

        for discography in self:
            discography.export(path)

    def get_discography(self, artist, create=False):
        if artist not in self.discographies and create:
            LOGGER.debug('Creating discography: %s', artist)
            self.discographies[artist] = Discography(artist)
        return self.discographies.get(artist, None)

    def __iter__(self):
        return iter(self.discographies.values())


class Discography:
    '''Collection of Albums by the same Artist.'''

    def __init__(self, artist):
        LOGGER.debug('Initialising discography: %s', artist)
        self.albums = dict()
        self.artist = artist

    def get_album(self, album, create=False):
        '''Retrieve an album from this Discography.
        
        If `create` is set to True, the album is created
        and added to this Discography if not found,
        otherwise None is returned if album is not found.
        '''
        if album not in self.albums and create:
            LOGGER.debug('Creating album: %s - %s', self.artist, album)
            self.albums[album] = Album(self.artist, album)
        return self.albums.get(album, None)

    def export(self, path):
        '''Write Discography to given path.
        
        The discography is exported as a directory containing
        sub directories of the following structure:

            Artist > Albums > Track Number. Track Name

        Where Artist is the name of this discography.
        '''
        LOGGER.debug('Exporting %s to %s', self, path)
        export_path = os.path.join(path, self.artist)
        if not os.path.isdir(export_path):
            LOGGER.debug('Creating discography directory: %s', export_path)
            if not DRY_RUN: os.makedirs(export_path)

        for album in self:
            album.export(export_path)

    def __iter__(self):
        return iter(self.albums.values())

    def __str__(self):
        return 'Discography(/{0})'.format(self.artist)


class Album:
    def __init__(self, artist, name):
        LOGGER.debug('Initialising album: %s - %s', artist, name)
        self.tracks = set()
        self.artist = artist
        self.name = name

    def add(self, track):
        '''Add a track to this discography.'''

        track_artist = track.get_artist()
        if track_artist != self.artist:
            LOGGER.warn('Track artist (%s) does not match album artist (%s): ',
                        track_artist, self.artist)
        self.tracks.add(track)

    def export(self, path):
        '''Export album to given path.'''

        LOGGER.debug('Exporting %s to %s', self, path)
        export_path = os.path.join(path, self.name)
        if not os.path.isdir(export_path):
            LOGGER.debug('Creating album directory: %s', export_path)
            if not DRY_RUN: os.makedirs(export_path)

        for track in self:
            track.export(export_path)

    def __str__(self):
        return 'Album(/{0}/{1})'.format(self.artist, self.name)

    def __iter__(self):
        return iter(self.tracks)


class Track:
    def __init__(self, path):
        LOGGER.debug('Initialising track: %s', path)
        self.path = path
        trunk, self.type = os.path.splitext(path)

        try:
            self.metadata = EasyID3(self.path)
        except ID3NoHeaderError:
            self.metadata = {'title': os.path.basename(trunk)}
            LOGGER.exception('File %s has no ID3 tag', path)

    def get_path(self):
        '''Returns the file system path to the source file.'''

        return self.path

    def get_type(self):
        '''Returns the audio file type (eg mp3).'''

        return self.type or 'mp3'

    def get_album(self):
        return self._get_metadata('album') or 'Unknown Album'

    def get_artist(self):
        return (self._get_metadata('albumartist')
                or self._get_metadata('artist')
                or 'Unknown Artist')

    def get_title(self):
        return self._get_metadata('title')

    def get_track_number(self):
        track_number = self._get_metadata('tracknumber')
        if track_number:
            return re.sub(r'/\d+$', '', track_number) # We don't want total tracks counter
        return  ''    # Would None make sense here?

    def _get_metadata(self, name):
        '''Get the associated file's metadata (eg title, artist).'''

        metadatum = self.metadata.get(name)
        if isinstance(metadatum, (str, type(None))):
            return metadatum
        return ' & '.join(metadatum)

    def export(self, path):
        '''Save file to disk.'''

        LOGGER.debug('Exporting %s to %s', self, path)
        track_no = self.get_track_number()
        track_title = self.get_title()
        if track_no:
            filename = '{0}. {1}.{2}'.format(track_no, track_title, self.get_type())
        else:
            filename = '{0}.{1}'.format(track_title, self.get_type())
        export_path = os.path.join(path, filename)
        if not DRY_RUN:
            if MOVE_EXPORT:
                LOGGER.debug('Moving %s to %s', self.path, export_path)
                shutil.move(self.path, export_path)
            else:
                LOGGER.debug('Copying %s to %s', self.path, export_path)
                shutil.copy(self.path, export_path)
        return os.path.join(path, filename)

    def __str__(self):
        return 'Track(/{0}/{1}/{2}. {3})'.format(
            self.get_artist(), self.get_album(), self.get_track_number(),
            self.get_title()
        )


def main():
    import sys
    import argparse

    global DRY_RUN, LOGGER, MOVE_EXPORT

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate', action='store_true',
                        help="Simulate run - don't actually export anything")
    parser.add_argument('--move', action='store_true',
                        help="Move files when exporting - don't copy them")
    parser.add_argument('--verbose', action='store_true',
                        help='Make a whole lot of noise')
    parser.add_argument('source', type=str, help='Library to be exported')
    parser.add_argument('target', type=str, help='Library to export to')

    args = parser.parse_args(sys.argv[1:])  # Don't want the script name
    DRY_RUN = args.simulate
    MOVE_EXPORT = args.move

    if DRY_RUN or args.verbose:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        LOGGER.addHandler(stream_handler)
        LOGGER.setLevel(logging.DEBUG)
        LOGGER.debug('Running in verbose mode...')

    library = Library(args.source)
    library.export(args.target)


if __name__ == '__main__':
    main()
