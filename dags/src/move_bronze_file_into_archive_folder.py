import tempfile
import logging
from airflow.providers.microsoft.azure.hooks.wasb import WasbHook
import os

AZURE_BLOB_CONN_ID = 'azure_blob_conn_id'


def move_bronze_file_into_archive_folder(**kwargs):
    ti = kwargs['ti']
    formatted_current_date = ti.xcom_pull(task_ids='get_old_date', key='my_key')

    logging.info(f"Date processed is {formatted_current_date}")

    if formatted_current_date is not None:
        container_name = 'bronze'
    
        az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
        list_of_files = az_hook.get_blobs_list(container_name=container_name) #To get the first level blob name
        new_list_of_files = [original_string.replace('/', '') for original_string in list_of_files]
        logging.info("File is renamed")
        logging.info(new_list_of_files)
    
        for folder_name in  new_list_of_files:
            logging.info(f"Processing folder {folder_name}")
            blob_name = f"{folder_name}_{formatted_current_date}.json"
            blob_path = f"{folder_name}/current/{formatted_current_date}/{blob_name}"
            virtual_folder_path = f"{folder_name}/archive/{formatted_current_date}/"


            temp_dir = tempfile.mkdtemp()
            logging.info(f"Created local temporary folder - {temp_dir}")
            temp_file_path = os.path.join(temp_dir, blob_name)

            az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
            az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=blob_path)
            logging.info(f"File {blob_name} is downloaded at {temp_dir}")

            az_hook.load_file(
                        file_path=temp_file_path,
                        container_name=container_name,
                        blob_name=f"{virtual_folder_path}{blob_name}",
                        overwrite=True
                    )
            logging.info(f"File {blob_name} is copied to archive - {virtual_folder_path}")
    else:
        logging.info("No file is archived")