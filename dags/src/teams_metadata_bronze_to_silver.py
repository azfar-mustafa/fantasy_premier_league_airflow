import pytz
from datetime import datetime
import tempfile
import duckdb
import logging
from airflow.providers.microsoft.azure.hooks.wasb import WasbHook
import os

AZURE_BLOB_CONN_ID = 'azure_blob_conn_id'

def teams_metadata_bronze_to_silver():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    formatted_current_date = myt_timestamp.strftime("%d%m%Y")

    temp_dir = tempfile.mkdtemp()
    logging.info(f"Temporary directory is created: {temp_dir}")

    bronze_blob_folder_path = f"teams_metadata/current/{formatted_current_date}"
    blob_name = f"teams_metadata_{formatted_current_date}.json"
    parquet_file_name = f"teams_metadata_{formatted_current_date}.parquet"
    temp_file_path = os.path.join(temp_dir, blob_name)
    bronze_blob_path = os.path.join(bronze_blob_folder_path, blob_name)

    silver_blob_name = f"teams_metadata/current/{formatted_current_date}/{parquet_file_name}"
    silver_parquet_file_full_path = os.path.join(temp_dir, parquet_file_name)

    table_name = "teams_metadata"

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=bronze_blob_path)
    logging.info(f"{blob_name} is downloaded at {temp_dir} from {bronze_blob_folder_path}")

    duckdb.sql(f"CREATE TABLE {table_name} AS SELECT * FROM read_json_auto('{temp_file_path}')")
    logging.info(f"Table {table_name} is created")
    duckdb.sql(f"COPY (SELECT * FROM {table_name}) TO '{silver_parquet_file_full_path}' (FORMAT PARQUET)")
    logging.info(f"Copy data from table {table_name} into file {parquet_file_name}")

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.load_file(
            file_path=silver_parquet_file_full_path,
            container_name='silver',
            blob_name=silver_blob_name,
            overwrite=True
        )
    logging.info(f"File {parquet_file_name} is uploaded into silver container")
    
    os.remove(silver_parquet_file_full_path)
    logging.info(f"{silver_parquet_file_full_path} is removed")

    os.remove(temp_file_path)
    logging.info(f"{temp_file_path} is removed")

    os.rmdir(temp_dir)
    logging.info(f"{temp_dir} is removed")