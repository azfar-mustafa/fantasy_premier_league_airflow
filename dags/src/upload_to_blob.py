import pytz
from datetime import datetime
import tempfile
import json
import logging
from airflow.providers.microsoft.azure.hooks.wasb import WasbHook
import os

AZURE_BLOB_CONN_ID = 'azure_blob_conn_id'

def upload_to_blob(**kwargs):
    # To add idempotence concept before data is uploaded to blob.
    ti = kwargs['ti']
    new_dict = ti.xcom_pull(task_ids='extract_data_from_api')

    metadata = ['events_metadata', 'teams_metadata', 'player_metadata', 'position_metadata']

    container_name = 'bronze'

    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    formatted_current_date = myt_timestamp.strftime("%d%m%Y")

    try:
        zipped_api = zip(metadata, new_dict)
        for attribute_name, data in zipped_api:
            virtual_folder_path = f"{attribute_name}/current/{formatted_current_date}/"
            blob_name = f"{attribute_name}_{formatted_current_date}.json"
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
                json.dump(data, temp_file, indent=4)
                temp_file_path = temp_file.name
            logging.info(f"Temporary file created: {temp_file_path}")
            az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
            az_hook.load_file(
                file_path=temp_file_path,
                container_name=container_name,
                blob_name=f"{virtual_folder_path}{blob_name}",
                overwrite=True
            )
            os.remove(temp_file_path)
            logging.info(f"Temporary file removed: {temp_file_path}")
            logging.info(f"File uploaded into Bronze container in Azure Blob Storage: {container_name}/{blob_name}")
    except Exception as e:
        logging.error(f"Error uploading file into Bronze container in Azure Blob Storage: {e}", exc_info=True)