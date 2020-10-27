#! /usr/bin/env python3
 
from sys import exit, stdout
from json import dump, load
from datetime import datetime, timedelta
from argparse import ArgumentParser
from shutil import copyfileobj, rmtree, unpack_archive
from pathlib import Path
from requests import get

BASE_URL = "https://beatsaver.com/api/"
LATEST_MAPS = "maps/latest/"
DOWNLOAD_HASH = "download/hash/"
MAP_BY_HASH = "maps/by-hash/"

# Without Browser user-agent, we get denied...
FAKE_HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

PLAYLIST = {"playlistTitle":"", 
        "playlistAuthor":"meh",
        "image":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII=",
        "songs":[],
        }

ILLEGAL_CHARS = (
    '<', '>', ':', '/', '\\', '|', '?', '*', '"',
    '\u0000', '\u0001', '\u0002', '\u0003', '\u0004', '\u0005', '\u0006', '\u0007',
    '\u0008', '\u0009', '\u000a', '\u000b', '\u000c', '\u000d', '\u000e', '\u000d',
    '\u000f', '\u0010', '\u0011', '\u0012', '\u0013', '\u0014', '\u0015', '\u0016',
    '\u0017', '\u0018', '\u0019', '\u001a', '\u001b', '\u001c', '\u001d', '\u001f'
)


def progressbar(it, prefix="", size=60, file=stdout):
    count = len(it)
    def show(j):
        x = int(size*j/count)
        file.write("%s[%s%s] %i/%i\r" % (prefix, "#"*x, "."*(size-x), j, count))
        file.flush()        
    show(0)
    for i, item in enumerate(it):
        yield item
        show(i+1)
    file.write("\n")
    file.flush()

def handle_args():

    parser = ArgumentParser(
                        prog="BSMH", description="Maps handler",
                            )
    parser.add_argument(
                "-l",
                "--last",
                type=int,
                default=24,
                )
    parser.add_argument(
                "-m",
                "--mapnumber",
                type=int,
                )
    parser.add_argument(
                "-t",
                "--playlisttitle",
                type=str,
                )
    parser.add_argument(
                "-d",
                "--download",
                type=bool,
                )
    parser.add_argument(
                "--maps_dir",
                type=str,
                default=".",
                )
    parser.add_argument(
                "-r",
                "--remove",
                type=bool,
                )
    parser.add_argument(
                "-p",
                "--playlist",
                type=str,
                )
    return parser.parse_args()

def get_page(page=0):
    #TODO : Handle errors
    return get(f"{BASE_URL}{LATEST_MAPS}{str(page)}", headers=FAKE_HEADERS).json()['docs']

def get_map(map_hash):
    return get(f"{BASE_URL}{MAP_BY_HASH}{map_hash}", headers=FAKE_HEADERS).json()

def check_time(time_now, maps, last_hours):
    most_recent = maps[0]['uploaded']
    less_recent = maps[-1]['uploaded']
    delta = time_now - timedelta(hours=last_hours)
    most_recent = datetime.strptime(most_recent[:-1],"%Y-%m-%dT%H:%M:%S.%f")
    less_recent = datetime.strptime(less_recent[:-1],"%Y-%m-%dT%H:%M:%S.%f")

    return delta, most_recent, less_recent

def get_last_x_maps(nb_maps):
    # Just get the last X maps 
    # There are 10 maps per page
    pages_to_scrap =  nb_maps / 10
    if nb_maps % 10 != 0:
        pages_to_scrap += 1
    print(f"We must scrap {str(int(pages_to_scrap))} pages")
    maps = []

    for page in progressbar(range(int(pages_to_scrap)), "Getting page number : "):
        maps.extend(get_page(page))
    return maps

def get_last_x_hours_maps(last_hours):
    now = datetime.utcnow() 

    maps = get_page()

    delta, most_recent, less_recent = check_time(now, maps, last_hours)

    if most_recent < delta:
        print(f"No new maps in the last {last_hours}h, sorry.")
        exit(0)
    elif less_recent > delta:
        print("We must scrap new pages")
        page = 1
        while less_recent > delta:
            print(f"Getting page {page}")
            maps.extend(get_page(page))
            delta, most_recent, less_recent = check_time(now, maps, last_hours)
            page += 1

    return maps

def create_playlist(maps, args):
    if args.playlisttitle:
        PLAYLIST['playlistTitle'] = args.playlisttitle
    else:
        PLAYLIST['playlistTitle'] = f"last_{args.mapnumber}_maps" if args.mapnumber else f"last_{args.last}h_maps" 

    now = datetime.utcnow() 
    delta = now - timedelta(hours=args.last)
    for bsmap in maps:
        map_hash = bsmap['hash']
        map_name = bsmap['name']
        map_key = bsmap['key']
        mapper = bsmap["metadata"]["levelAuthorName"]
        map_dict = {"hash": map_hash, "songName": map_name, "key": map_key, "mapper": mapper}
        if args.mapnumber:
            if len(PLAYLIST['songs']) < args.mapnumber:
                #"uploader":{"_id":"5dd5a3cef07e3c0006059d2f","username":"halcyon10"} 
                PLAYLIST['songs'].append(map_dict)
        else:
            map_upload_time = datetime.strptime(bsmap['uploaded'][:-1], "%Y-%m-%dT%H:%M:%S.%f")
            if map_upload_time > delta:
                PLAYLIST['songs'].append(map_dict)

    with open(f"{PLAYLIST['playlistTitle']}.bplist", "w") as plist_file:
        dump(PLAYLIST, plist_file)

def download_songs(output_directory="."):
    output_dir = Path(output_directory)

    nb_maps = len(PLAYLIST['songs'])
    print(f"There are {str(nb_maps)} in this playlist.")
    for i, bsmap in enumerate(PLAYLIST['songs']):
        print(f"Processing {str(i+1)}/{str(nb_maps)}...")

        # Use same naming convention as ModAssistant 
        # They use this : https://github.com/Assistant/ModAssistant/blob/e3726cbc63a5e4229f660cebc8bacf4ac32fbb27/ModAssistant/Classes/External%20Interfaces/BeatSaver.cs#L119 
        # string zip = Path.Combine(Utils.BeatSaberPath, CustomSongsFolder, Map.hash) + ".zip";
        # string mapName = string.Concat(($"{Map.key} ({Map.metadata.songName} - {Map.metadata.levelAuthorName})")
        #        .Split(ModAssistant.Utils.Constants.IllegalCharacters));
        songname = f"{bsmap['key']} ({bsmap['songName']} - {bsmap['mapper']})"
        songname_file = ''.join(char for char in songname if not char in ILLEGAL_CHARS)
        # They also use pure hash for the zip file :
        zip_file = f"{bsmap['hash']}.zip"

        file_to_dl = Path('.') / zip_file
        if not file_to_dl.exists():
            print(f"   - File doesn't exist, downloading {songname}, please wait...")
            with get(f"{BASE_URL}{DOWNLOAD_HASH}{bsmap['hash']}", headers=FAKE_HEADERS, stream=True) as r:
                with open(f"{zip_file}", 'wb') as f:
                    copyfileobj(r.raw, f)
        else:
            print(f"{songname} zip file already downloaded")

        out_dir = output_dir / songname_file
        if not out_dir.exists():
            print(f"        * Unzipping {zip_file} to {songname_file}...")
            #with ZipFile(f"{zip_file}", 'r') as zip_ref:
            #    zip_ref.extractall(output_dir / )
            unpack_archive(f"{zip_file}", out_dir)
        else:
            print(f"        * {songname} zip file already unzipped")

        print(f"        * Removing {songname} zip file to cleanup a lil' bit...")
        file_to_dl.unlink()



def remove_all_maps_from_playlist_in_dir(playlist, directory):
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"Songs directory {directory} doesn't exist :o")
        exit(1)

    try:
        with open(playlist) as plist_file:
            print(f"Removing all the songs from the playlist {playlist}")
            plist = load(plist_file)
            for bsmap in plist['songs']:
                # See 'download_songs' function for naming convention used
                try:
                    songname = f"{bsmap['key']} ({bsmap['songName']} - {bsmap['mapper']})"
                except KeyError:
                    # In case the playlist didn't have all the needed infos
                    remote_map = get_map(bsmap['hash'])
                    songname = f"{remote_map['key']} ({remote_map['name']} - {bsmap['metadata']['levelAuthorName']})"
                songname_file = ''.join(char for char in songname if not char in ILLEGAL_CHARS)
                map_dir = dir_path / songname_file
                if map_dir.exists():
                    print(f"    Removing {map_dir}")
                    rmtree(map_dir)
    except FileNotFoundError:
        print(f"Playlist file '{playlist}' was not found.")
        exit(1)

def main():

    args = handle_args()

    if args.remove:
        if not args.playlist:
            print("Please, specify the playlist file of the songs you wish to remove")
            exit(1)
        remove_all_maps_from_playlist_in_dir(args.playlist, args.maps_dir)
        exit(0)

    if args.mapnumber:
        maps = get_last_x_maps(args.mapnumber)
    else:
        maps = get_last_x_hours_maps(args.last)

    if maps:
        create_playlist(maps, args)
        if args.download:
            download_songs(args.maps_dir)

if __name__ == "__main__":
    main()
