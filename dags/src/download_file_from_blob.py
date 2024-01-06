import pytz
from datetime import datetime
import tempfile
import json
import logging
from airflow.providers.microsoft.azure.hooks.wasb import WasbHook
import os
import requests

AZURE_BLOB_CONN_ID = 'azure_blob_conn_id'


def download_file_from_blob():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    formatted_current_date = myt_timestamp.strftime("%d%m%Y")

    temp_dir = tempfile.mkdtemp()
    logging.info(f"Temporary directory created: {temp_dir}")

    blob_path = f"player_metadata/current/{formatted_current_date}/player_metadata_{formatted_current_date}.json"
    blob_name = f"player_metadata_{formatted_current_date}.json"
    temp_file_path = os.path.join(temp_dir, blob_name)

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=blob_path)
    logging.info(f"File is downloaded at {temp_dir}")

    with open(temp_file_path, "r") as json_file:
        main_json_file = json.load(json_file)

    os.remove(temp_file_path)
    logging.info(f"File {blob_name} is deleted in local temporary directory - {temp_dir}")


    current_season_history_file_name = f"current_season_history_{formatted_current_date}.json"
    all_dict = []
    player_id_local_file_path = os.path.join(temp_dir, current_season_history_file_name)

    for id_player in main_json_file:
        player_id = id_player.get("id")
        #player_id = 100
    
        url = f"https://fantasy.premierleague.com/api/element-summary/{player_id}/"
        
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            player_data = response.json()
            current_season_past_fixture = player_data['history']
            all_dict.extend(current_season_past_fixture)
            logging.info(f"Added player id {player_id} in dictionary.")


    with open(player_id_local_file_path, 'w') as local_file_player_id:
        json.dump(all_dict, local_file_player_id, indent=4)
        logging.info(f"{player_id_local_file_path} is created")

    current_season_history_blob_name = f"current_season_history/current/{formatted_current_date}/{current_season_history_file_name}"
    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.load_file(
            file_path=player_id_local_file_path,
            container_name='bronze',
            blob_name=current_season_history_blob_name,
            overwrite=True
        )
    logging.info(f"File {current_season_history_file_name} is uploaded at into Bronze container")
    

    os.remove(player_id_local_file_path)
    logging.info(f"File {current_season_history_file_name} is deleted in local temporary directory - {temp_dir}")

    os.rmdir(temp_dir)
    logging.info(f"Local temporary directory - {temp_dir} is deleted")