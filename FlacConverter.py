import coloredlogs
import logging
import os
import shutil
import subprocess
import mutagen.flac
import mutagen.easyid3
import sys


def create_output(d, version):
    if d.find('FLAC') == -1:
        return d + ' [' + version + ']'
    else:
        return d.replace('FLAC', version)


def read_tags(filename):
    meta = mutagen.flac.FLAC(filename)
    logging.debug('Tags for %s: %s', filename, meta.tags)
    return meta.tags


def write_tags(filename, tags):
    logging.info('Tagging file %s ...', filename)
    meta = mutagen.File(filename, easy=True)
    # meta = mutagen.easyid3.EasyID3(filename)
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


def convert(i, o, format):
    flac_command = ['flac', '-c', '-d', i]
    logging.info('Convertion flac %s ...', flac_command)
    process = subprocess.Popen(flac_command, stdout=subprocess.PIPE)

    lame_command = ['lame', '-m', 'j', '-q', '0', '--vbr-new', '-V', '0', '-', o]
    if format == '320':
        lame_command = ['lame', '-m', 'j', '-q', '0', '-b', '320', '-', o]

    logging.debug('... to %s', lame_command)
    output = subprocess.check_output(lame_command, stdin=process.stdout)
    process.wait()

    tags = read_tags(i)
    write_tags(o, tags)


def main(arguments):
    version = 'V0 (VBR)'
    tracker = 'https://flacsfor.me/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/announce'
    directories = arguments[1:]
    logging.debug('Directories %s ...', directories)
    for d in directories:
        d = os.path.abspath(d)
        if not os.path.isdir(d):
            logging.error('%s is not a directory', d)
            continue

        root, d = os.path.split(d)
        logging.debug('%s, %s', root, d)
        input_directory = os.path.join(root, d)
        output_directory = os.path.join(root, create_output(d, version))
        if not os.path.isdir(output_directory):
            logging.debug('Creating directory %s ...', output_directory)
            os.makedirs(output_directory)
        music_files = []
        for (dirpath, dirnames, filenames) in os.walk(input_directory):
            logging.debug('dirpath=%s, dirnames=%s, filenames=%s', dirpath, dirnames, filenames)
            for f in filenames:
                source = os.path.join(dirpath, f)
                destination = os.path.join(output_directory, os.path.relpath(source, input_directory))
                ext = os.path.splitext(source)[1]
                if ext.lower() in ['.flac']:
                    base = os.path.splitext(destination)[0]
                    destination = base + '.mp3'
                    logging.debug('convert(%s, %s)', source, destination)
                    convert(source, destination, version)
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
        logging.debug('Creating torrent file %s ...', command)
        subprocess.call(command)


if __name__ == '__main__':
    coloredlogs.install(level='DEBUG', fmt='%(levelname)s\t%(message)s')
    # logging.basicConfig(format='%(levelname)s\t%(message)s', level=logging.DEBUG)
    main(sys.argv)
