#! /usr/bin/env python3
 
from sys import exit
from json import dump
from datetime import datetime, timedelta
from argparse import ArgumentParser
from requests import get

VERSION = "v0.01"
BASE_URL = "https://beatsaver.com/api/"
LATEST_MAPS = "maps/latest/"

# Without Browser user-agent, we get denied...
FAKE_HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

PLAYLIST = {"playlistTitle":"", 
        "playlistAuthor":"meh",
        "image":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII=",
        "songs":[],
        }

def handle_args():

    parser = ArgumentParser(
                        prog="BSMH", description=f"Maps handler {VERSION}",
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
    return parser.parse_args()

def get_page(page=0):
    #TODO: Handle errors
    return get(f"{BASE_URL}{LATEST_MAPS}{str(page)}", headers=FAKE_HEADERS).json()['docs']

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
    for page in range(int(pages_to_scrap)):
        print(f"Getting page {page+1}")
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
        if args.mapnumber:
            if len(PLAYLIST['songs']) < args.mapnumber:
                PLAYLIST['songs'].append({"hash": map_hash, "songName": map_name})
        else:
            map_upload_time = datetime.strptime(bsmap['uploaded'][:-1], "%Y-%m-%dT%H:%M:%S.%f")
            if map_upload_time > delta:
                PLAYLIST['songs'].append({"hash": map_hash, "songName": map_name})

    with open(f"{PLAYLIST['playlistTitle']}.bplist", "w") as plist_file:
        dump(PLAYLIST, plist_file)


def main():

    args = handle_args()

    if args.mapnumber:
        maps = get_last_x_maps(args.mapnumber)
    else:
        maps = get_last_x_hours_maps(args.last)

    if maps:
        create_playlist(maps, args)

if __name__ == "__main__":
    main()
