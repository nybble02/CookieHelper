import os
import sys
import time
import logging
from tokenize import Single

import requests as http_requests
import configparser
from obsws_python import ReqClient

# Rocksniffer States
RS_NOT_FOUND = 0
IN_MENU = 1
LOAD_SONG = 3
IN_SONG = 4
END_SONG = 5

# Create a logger
logger = logging.getLogger("nybb-scene-switch")
logger.setLevel(logging.INFO)

# Log to file
file_handler = logging.FileHandler("nyb-log.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
logger.addHandler(console_handler)

logger.info("Script started")

# Config file path
if getattr(sys, 'frozen', False):  # If running as an .exe
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

config_path = os.path.join(BASE_DIR, 'config.ini')

if not os.path.exists(config_path):
    config = configparser.ConfigParser()
    config["obs"] = {
        "host": "localhost",
        "port": "4455",
        "password": "password"
    }
    config["rocksniffer"] = {
        "host": "localhost",
        "port": "9938"
    }
    config["behaviour"] = {
        "mode": "0",
        "main_scene": "Main Scene",
        "song_scene": "Song Scene",
        "menu_scene": "Menu Scene",
        "sources": "Source 1,Source 2",
        "source_states": "off,on"

    }
    with open(config_path, "w") as config_file:
        config.write(config_file)
    print(f"Created default config at {config_path}")

# Load config
config = configparser.ConfigParser()
config.read(config_path)

OBS_HOST = config.get('obs', 'host')
OBS_PORT = config.getint('obs', 'port')
OBS_PASSWORD = config.get('obs', 'password')

ROCKSNIFF_URL = f"http://{config.get('rocksniffer', 'host')}:{config.getint('rocksniffer', 'port')}/"

MODE = config.getint('behaviour', 'mode')
SONG_SCENE = config.get('behaviour', 'song_scene')
MENU_SCENE = config.get('behaviour', 'menu_scene')
MAIN_SCENE = config.get('behaviour', 'main_scene')
SOURCES = config['behaviour']['sources']
SOURCE_STATES = config['behaviour']['source_states']

source_list = SOURCES.split(',')
source_states_list = SOURCE_STATES.split(',')

source_dict = dict(zip(source_list, source_states_list))

print(source_dict)


def connect_to_obs():
    """Connect to OBS and retry"""
    while True:
        try:
            client = ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD)
            logger.info("Connected to OBS WebSocket")
            return client
        except Exception as e:
            logger.warning(f"OBS WebSocket connection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)

def get_source_id(client, source, scene):
    """Get the scene item ID for a given source in a scene."""
    try:
        response = client.get_scene_item_list(scene)
        for item in response.scene_items:
            if item['sourceName'] == source:
                return item['sceneItemId']
    except Exception as e:
        logger.warning(f"Error getting scene item ID for '{source}' in '{scene}': {e}")
    return None  # Return None if source is not found


def main():
    """Main loop"""
    client = connect_to_obs()
    old_state = None
    prev_scene = None

    while True:
        try:
            current_scene = client.get_current_program_scene().current_program_scene_name
            sniff_resp = http_requests.get(ROCKSNIFF_URL)
            sniff_data = sniff_resp.json()

            current_state = sniff_data['currentState']

            # Toggle Sources
            if MODE == 1:
                if current_scene == MAIN_SCENE:
                    for source in source_list:
                        source_id  = get_source_id(client, source, MAIN_SCENE)

                        if source_id:
                            source_enabled = client.get_scene_item_enabled(MAIN_SCENE, source_id).scene_item_enabled
                            # Disable sources if IN_SONG
                            if current_state in {LOAD_SONG, IN_SONG}:
                                # if source_enabled:
                                #     client.set_scene_item_enabled(MAIN_SCENE, source_id, False)
                                #     logger.info(f"{source} disabled")

                                if source_dict[source] == 'on' :
                                    if not source_enabled:
                                        client.set_scene_item_enabled(MAIN_SCENE, source_id, True)
                                        logger.info(f"{source} enabled")
                                else:
                                    if source_enabled:
                                        client.set_scene_item_enabled(MAIN_SCENE, source_id, False)
                                        logger.info(f"{source} disabled")
                            else:
                                if source_dict[source] == 'on':
                                    if source_enabled:
                                        client.set_scene_item_enabled(MAIN_SCENE, source_id, False)
                                        logger.info(f"{source} disabled")
                                else:
                                    if not source_enabled:
                                        client.set_scene_item_enabled(MAIN_SCENE, source_id, True)
                                        logger.info(f"{source} enabled")
            # Switch Scenes
            else:
                if current_state != old_state:

                    if current_scene in {MENU_SCENE, SONG_SCENE}:  # Only switch if in the expected scenes
                        # new_scene = SONG_SCENE if {LOAD_SONG, IN_SONG} else MENU_SCENE

                        if current_state == LOAD_SONG or current_state == IN_SONG:
                            new_scene = SONG_SCENE
                        else:
                            new_scene = MAIN_SCENE

                        if new_scene != prev_scene:
                            client.set_current_program_scene(new_scene)
                            logger.info(f"Scene Changed {prev_scene} -> {new_scene}")
                            # print(f"Scene Changed {prev_scene} -> {new_scene}")
                            prev_scene = new_scene

                        logger.info(f"State changed {old_state} -> {current_state}")
                        # print(f"State changed {old_state} -> {current_state}")
                        old_state = current_state
                    else:
                        continue
                # if current_scene in {MENU_SCENE, SONG_SCENE}:
                #     new_scene = SONG_SCENE if {LOAD_SONG, IN_SONG} else MENU_SCENE
                #     if new_scene != prev_scene:
                #         client.set_current_program_scene(new_scene)
                #         logger.info(f"Scene Changed {prev_scene} -> {new_scene}")
                #         prev_scene = new_scene


        except http_requests.exceptions.RequestException as e:
            logger.warning(f"Error: {e}")
        except Exception as e:
            logger.warning(f"Error: {e}")

        time.sleep(1)  # Prevent CPU overuse


if __name__ == "__main__":
    main()
