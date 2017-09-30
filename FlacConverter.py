import argparse
import coloredlogs
import logging
import os
import shutil
import subprocess
import mutagen.flac
import mutagen.easyid3
import sys


def which(cmd, mode=os.F_OK | os.X_OK, path=None):
    """Given a command, mode, and a PATH string, return the path which
    conforms to the given mode on the PATH, or None if there is no such
    file.

    `mode` defaults to os.F_OK | os.X_OK. `path` defaults to the result
    of os.environ.get("PATH"), or can be overridden with a custom search
    path.

    """
    # Check that a given file can be accessed with the correct mode.
    # Additionally check that `file` is not a directory, as on Windows
    # directories pass the os.access check.
    def _access_check(fn, mode):
        return (os.path.exists(fn) and os.access(fn, mode)
                and not os.path.isdir(fn))

    # If we're given a path with a directory part, look it up directly rather
    # than referring to PATH directories. This includes checking relative to the
    # current directory, e.g. ./script
    if os.path.dirname(cmd):
        if _access_check(cmd, mode):
            return cmd
        return None

    if path is None:
        path = os.environ.get("PATH", os.defpath)
    if not path:
        return None
    path = path.split(os.pathsep)

    if sys.platform == "win32":
        # The current directory takes precedence on Windows.
        if not os.curdir in path:
            path.insert(0, os.curdir)

        # PATHEXT is necessary to check on Windows.
        pathext = os.environ.get("PATHEXT", "").split(os.pathsep)
        # See if the given file matches any of the expected path extensions.
        # This will allow us to short circuit when given "python.exe".
        # If it does match, only test that one, otherwise we have to try
        # others.
        if any(cmd.lower().endswith(ext.lower()) for ext in pathext):
            files = [cmd]
        else:
            files = [cmd + ext for ext in pathext]
    else:
        # On other platforms you don't have things like PATHEXT to tell you
        # what file suffixes are executable, so just pass on cmd as-is.
        files = [cmd]

    seen = set()
    for dir in path:
        normdir = os.path.normcase(dir)
        if not normdir in seen:
            seen.add(normdir)
            for thefile in files:
                name = os.path.join(dir, thefile)
                if _access_check(name, mode):
                    return name
    return None


def create_output(d, version):
    if d.find('FLAC') == -1:
        return d + ' [' + version + ']'
    else:
        return d.replace('FLAC', version)


def read_tags(filename):
    meta = mutagen.flac.FLAC(filename)
    logging.debug('Tags for %s: %s', filename, meta.tags)
    return meta.tags


def write_mp3_tags(filename, tags):
    logging.info('Tagging file %s ...', filename)
    meta = mutagen.File(filename, easy=True)
    # meta = mutagen.easyid3.EasyID3(filename)
    meta.add_tags()
    for tag, value in tags.iteritems():
        if tag in ["album", "composer", "genre", "date", "lyricist", "title", "version", "artist", "tracknumber"]:
            meta[tag] = value
    meta.save()
    logging.debug('with tags %s', meta.tags)


def write_flac_tags(filename, tags):
    logging.info('Tagging file %s ...', filename)
    meta = mutagen.flac.FLAC(filename)
    meta.add_tags()
    for tag, value in tags.iteritems():
        meta[tag] = value
    meta.save()
    logging.debug('with tags %s', meta.tags)


def null_value(value, default):
    if value is None or value == '':
        return default
    else:
        return value


def convert_mp3(i, o, format):
    flac_command = ['flac', '-c', '-d', i]
    logging.info('Conversion flac %s ...', flac_command)
    process = subprocess.Popen(flac_command, stdout=subprocess.PIPE)

    lame_command = ['lame', '-m', 'j', '-q', '0', '--vbr-new', '-V', '0', '-', o]
    if format == '320':
        lame_command = ['lame', '-m', 'j', '-q', '0', '-b', '320', '-', o]

    logging.debug('... to %s', lame_command)
    output = subprocess.Popen(lame_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=process.stdout)
    stdout, stderr = output.communicate()
    if stdout:
        logging.debug(stdout)
    if stderr:
        logging.debug(stderr)

    process.wait()

    tags = read_tags(i)
    write_mp3_tags(o, tags)


def convert_flac(i, o, bitrate):
    sox_command = ['sox', i, '-b', '16', o, 'rate', bitrate, 'dither', '-s']
    logging.info('Conversion flac %s ...', sox_command)

    output = subprocess.Popen(sox_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = output.communicate()
    if stdout:
        logging.debug(stdout)
    if stderr:
        logging.error(stderr)

    output.wait()


def check_command(command):
    path = which(command)
    if not path:
        logging.fatal('Command %s is not installed', command)
        return False

    logging.debug('Using %s from command %s', path, command)
    return True


def main():
    # Parsing arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-D', '--debug', help='increase output verbosity', action="store_true")
    parser.add_argument('-C', '--check', help='only check command line dependencies', action="store_true")
    parser.add_argument('directories', nargs='*', help='directories to convert')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--V0', help='convert input in mp3 V0 (VBR)', action="store_true")
    group.add_argument('--MP3', help='convert input in mp3 320 kbps', action="store_true")
    group.add_argument('--FLAC', help='convert input in flac 16bits', action="store_true")
    group.add_argument('--ALL', help='convert input in both V0 and 320 formats', action="store_true")

    parser.add_argument('-t', '--tracker', help="tracker to use in torrent", type=str)
    parser.add_argument('-r', '--rate', help="sample rate of audio", type=int)

    arguments = parser.parse_args()

    level_styles = {'info': {'color': 'green'},
                    'notice': {'color': 'magenta'},
                    'verbose': {'color': 'blue'},
                    'success': {'color': 'green', 'bold': True},
                    'spam': {'color': 'blue'},
                    'critical': {'color': 'red', 'bold': True},
                    'error': {'color': 'red'},
                    'debug': {'color': 'blue'},
                    'warning': {'color': 'yellow'}
                    }

    if arguments.debug:
        coloredlogs.install(level='DEBUG', fmt='%(levelname)s\t%(message)s', level_styles=level_styles)
        logging.info('Verbosity turned on')
    else:
        coloredlogs.install(level='INFO', fmt='%(levelname)s\t%(message)s', level_styles=level_styles)
        logging.info('Verbosity turned off')
    # logging.basicConfig(format='%(levelname)s\t%(message)s', level=logging.DEBUG)

    if not check_command('sox'):
        exit(1)
    if not check_command('flac'):
        exit(1)
    if not check_command('lame'):
        exit(1)
    if not check_command('ctorrent'):
        exit(1)

    if arguments.check:
        return 0

    bitrate = arguments.rate
    versions = []
    if arguments.V0:
        versions.append('V0 (VBR)')
    elif arguments.MP3:
        versions.append('320')
    elif arguments.FLAC:
        if not bitrate:
            logging.fatal('rate argument is mandatory with --FLAC option')
            exit(1)
        if bitrate == 48000:
            versions.append('FLAC 16-48')
        elif bitrate == 44100:
            versions.append('FLAC 16-44')
        else:
            versions.append('FLAC 16bit')
    else:
        versions.append('V0 (VBR)')
        versions.append('320')

    if arguments.tracker:
        tracker = arguments.tracker
        logging.debug('Using tracker %s', tracker)
    else:
        import Secret
        tracker = Secret.tracker
        logging.debug('Using tracker %s', tracker)

    directories = arguments.directories
    logging.debug('Directories %s ...', directories)

    for d in directories:
        d = os.path.abspath(d)
        if not os.path.isdir(d):
            logging.error('%s is not a directory', d)
            continue

        root, d = os.path.split(d)
        input_directory = os.path.join(root, d)
        for version in versions:
            output_directory = os.path.join(root, create_output(d, version))
            if not os.path.isdir(output_directory):
                logging.debug('Creating directory %s ...', output_directory)
                os.makedirs(output_directory)

            music_files = []
            for (dirpath, dirnames, filenames) in os.walk(input_directory):
                for f in filenames:
                    source = os.path.join(dirpath, f)
                    destination = os.path.join(output_directory, os.path.relpath(source, input_directory))

                    dirname = os.path.dirname(destination)
                    if not os.path.isdir(dirname):
                        logging.debug('Creating directory %s ...', output_directory)
                        os.makedirs(dirname)

                    ext = os.path.splitext(source)[1]
                    if ext.lower() in ['.flac']:
                        if version.startswith('FLAC'):
                            logging.debug('Convert(%s, %s, %s)', source, destination, version)
                            convert_flac(source, destination, bitrate)
                        else:
                            base = os.path.splitext(destination)[0]
                            destination = base + '.mp3'
                            logging.debug('Convert(%s, %s, %s)', source, destination, version)
                            convert_mp3(source, destination, version)
                        music_files.append(os.path.relpath(destination, output_directory))
                    elif ext.lower() in ['.jpeg', '.jpg', '.png']:
                        logging.debug('shutil.copyfile(%s, %s)', source, destination)
                        shutil.copyfile(source, destination)
            music_files.sort()

            playlist = os.path.join(output_directory, os.path.basename(output_directory) + '.m3u')
            logging.debug('Creating playlist file %s ...', playlist)
            with open(playlist, 'w') as f:
                for music_file in music_files:
                    f.write(music_file)
                    f.write('\n')

            command = ['ctorrent', '-t', '-p', '-u', tracker, '-s', output_directory + '.torrent', output_directory]
            logging.info('Creating torrent file %s ...', command)
            output = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = output.communicate()
            if stdout:
                logging.debug(stdout)
            if stderr:
                logging.error(stderr)

            output.wait()
            logging.info('Conversion done for %s', output_directory)
    return 0

if __name__ == '__main__':
    main()
