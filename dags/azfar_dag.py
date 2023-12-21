from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.providers.microsoft.azure.hooks.wasb import WasbHook
from airflow.providers.microsoft.azure.operators.adls import ADLSDeleteOperator
from airflow.operators.http_operator import SimpleHttpOperator
from airflow.providers.microsoft.azure.hooks.data_lake import AzureDataLakeStorageV2Hook
import requests
import json
import logging
import tempfile
import os
import pytz
import duckdb
from collections import defaultdict

AZURE_BLOB_CONN_ID = 'azure_blob_conn_id'

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023,11,1),
    'retries': 0,
    'retry_delay': timedelta(minutes=5),
}


dag = DAG(
    dag_id='fantasy_premier_league_debug',
    default_args=default_args,
    description='To extract data from FPL and upload it into Azure',
    catchup=False, # Specify whether to catchu for missed runs
    schedule_interval=timedelta(days=1),
)

def current_season_history_bronze_to_silver_test():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    #formatted_current_date = myt_timestamp.strftime("%d%m%Y")
    formatted_current_date = '11122023'

    temp_dir = tempfile.mkdtemp()
    print(f"Temporary directory is created: {temp_dir}")

    bronze_blob_folder_path = f"current_season_history/current/{formatted_current_date}"
    blob_name = f"current_season_history_{formatted_current_date}.json"
    parquet_file_name = f"current_season_history_{formatted_current_date}.parquet"
    temp_file_path = os.path.join(temp_dir, blob_name)
    bronze_blob_path = os.path.join(bronze_blob_folder_path, blob_name)

    silver_blob_name = f"current_season_history/current/{formatted_current_date}/{parquet_file_name}"
    silver_parquet_file_full_path = os.path.join(temp_dir, parquet_file_name)

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=bronze_blob_path)
    print(f"{blob_name} is downloaded at {temp_dir} from {bronze_blob_folder_path}")

    duckdb.sql(f"CREATE TABLE current_season_history AS SELECT * FROM read_json_auto('{temp_file_path}')")
    print(f"Table current_season_history is created")
    duckdb.sql(f"COPY (SELECT * FROM current_season_history) TO '{silver_parquet_file_full_path}' (FORMAT PARQUET)")
    print(f"Copy data from table current_season_history into file {parquet_file_name}")

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.load_file(
            file_path=silver_parquet_file_full_path,
            container_name='silver',
            blob_name=silver_blob_name,
            overwrite=True
        )
    print(f"File {parquet_file_name} is uploaded into silver container")
    
    os.remove(silver_parquet_file_full_path)
    print(f"{silver_parquet_file_full_path} is removed")

    os.remove(temp_file_path)
    print(f"{temp_file_path} is removed")

    os.rmdir(temp_dir)
    print(f"{temp_dir} is removed")


def player_metadata_bronze_to_silver_test():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    #formatted_current_date = myt_timestamp.strftime("%d%m%Y")
    formatted_current_date = '11122023'

    temp_dir = tempfile.mkdtemp()
    print(f"Temporary directory is created: {temp_dir}")

    bronze_blob_folder_path = f"player_metadata/current/{formatted_current_date}"
    blob_name = f"player_metadata_{formatted_current_date}.json"
    parquet_file_name = f"player_metadata_{formatted_current_date}.parquet"
    temp_file_path = os.path.join(temp_dir, blob_name)
    bronze_blob_path = os.path.join(bronze_blob_folder_path, blob_name)

    silver_blob_name = f"player_metadata/current/{formatted_current_date}/{parquet_file_name}"
    silver_parquet_file_full_path = os.path.join(temp_dir, parquet_file_name)

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=bronze_blob_path)
    print(f"{blob_name} is downloaded at {temp_dir} from {bronze_blob_folder_path}")

    duckdb.sql(f"CREATE TABLE player_metadata AS SELECT *, CONCAT(first_name, ' ', second_name) as full_name, now_cost/10 as latest_price FROM read_json_auto('{temp_file_path}')")
    print(f"Table player_metadata is created")
    duckdb.sql(f"COPY (SELECT * FROM player_metadata) TO '{silver_parquet_file_full_path}' (FORMAT PARQUET)")
    print(f"Copy data from table player_metadata into file {parquet_file_name}")

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.load_file(
            file_path=silver_parquet_file_full_path,
            container_name='silver',
            blob_name=silver_blob_name,
            overwrite=True
        )
    print(f"File {parquet_file_name} is uploaded into silver container")
    
    os.remove(silver_parquet_file_full_path)
    print(f"{silver_parquet_file_full_path} is removed")

    os.remove(temp_file_path)
    print(f"{temp_file_path} is removed")

    os.rmdir(temp_dir)
    print(f"{temp_dir} is removed")


def position_metadata_bronze_to_silver_test():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    #formatted_current_date = myt_timestamp.strftime("%d%m%Y")
    formatted_current_date = '11122023'

    temp_dir = tempfile.mkdtemp()
    print(f"Temporary directory is created: {temp_dir}")

    bronze_blob_folder_path = f"position_metadata/current/{formatted_current_date}"
    blob_name = f"position_metadata_{formatted_current_date}.json"
    parquet_file_name = f"position_metadata_{formatted_current_date}.parquet"
    temp_file_path = os.path.join(temp_dir, blob_name)
    bronze_blob_path = os.path.join(bronze_blob_folder_path, blob_name)

    silver_blob_name = f"position_metadata/current/{formatted_current_date}/{parquet_file_name}"
    silver_parquet_file_full_path = os.path.join(temp_dir, parquet_file_name)

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=bronze_blob_path)
    print(f"{blob_name} is downloaded at {temp_dir} from {bronze_blob_folder_path}")

    duckdb.sql(f"CREATE TABLE position_metadata AS SELECT * FROM read_json_auto('{temp_file_path}')")
    print(f"Table position_metadata is created")
    duckdb.sql(f"COPY (SELECT * FROM position_metadata) TO '{silver_parquet_file_full_path}' (FORMAT PARQUET)")
    print(f"Copy data from table position_metadata into file {parquet_file_name}")

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.load_file(
            file_path=silver_parquet_file_full_path,
            container_name='silver',
            blob_name=silver_blob_name,
            overwrite=True
        )
    print(f"File {parquet_file_name} is uploaded into silver container")
    
    os.remove(silver_parquet_file_full_path)
    print(f"{silver_parquet_file_full_path} is removed")

    os.remove(temp_file_path)
    print(f"{temp_file_path} is removed")

    os.rmdir(temp_dir)
    print(f"{temp_dir} is removed")


def teams_metadata_bronze_to_silver_test():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    #formatted_current_date = myt_timestamp.strftime("%d%m%Y")
    formatted_current_date = '11122023'

    temp_dir = tempfile.mkdtemp()
    print(f"Temporary directory is created: {temp_dir}")

    bronze_blob_folder_path = f"teams_metadata/current/{formatted_current_date}"
    blob_name = f"teams_metadata_{formatted_current_date}.json"
    parquet_file_name = f"teams_metadata_{formatted_current_date}.parquet"
    temp_file_path = os.path.join(temp_dir, blob_name)
    bronze_blob_path = os.path.join(bronze_blob_folder_path, blob_name)

    silver_blob_name = f"teams_metadata/current/{formatted_current_date}/{parquet_file_name}"
    silver_parquet_file_full_path = os.path.join(temp_dir, parquet_file_name)

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=bronze_blob_path)
    print(f"{blob_name} is downloaded at {temp_dir} from {bronze_blob_folder_path}")

    duckdb.sql(f"CREATE TABLE teams_metadata AS SELECT * FROM read_json_auto('{temp_file_path}')")
    print(f"Table teams_metadata is created")
    duckdb.sql(f"COPY (SELECT * FROM teams_metadata) TO '{silver_parquet_file_full_path}' (FORMAT PARQUET)")
    print(f"Copy data from table teams_metadata into file {parquet_file_name}")

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.load_file(
            file_path=silver_parquet_file_full_path,
            container_name='silver',
            blob_name=silver_blob_name,
            overwrite=True
        )
    print(f"File {parquet_file_name} is uploaded into silver container")
    
    os.remove(silver_parquet_file_full_path)
    print(f"{silver_parquet_file_full_path} is removed")

    os.remove(temp_file_path)
    print(f"{temp_file_path} is removed")

    os.rmdir(temp_dir)
    print(f"{temp_dir} is removed")


    


current_season_history_bronze_to_silver_test = PythonOperator(
    task_id='current_season_history_bronze_to_silver_test',
    python_callable=current_season_history_bronze_to_silver_test,
    provide_context=True,
    dag=dag,
)

player_metadata_bronze_to_silver_test = PythonOperator(
    task_id='player_metadata_bronze_to_silver_test',
    python_callable=player_metadata_bronze_to_silver_test,
    provide_context=True,
    dag=dag,
)

position_metadata_bronze_to_silver_test = PythonOperator(
    task_id='position_metadata_bronze_to_silver_test',
    python_callable=position_metadata_bronze_to_silver_test,
    provide_context=True,
    dag=dag,
)

teams_metadata_bronze_to_silver_test = PythonOperator(
    task_id='teams_metadata_bronze_to_silver_test',
    python_callable=teams_metadata_bronze_to_silver_test,
    provide_context=True,
    dag=dag,
)

current_season_history_bronze_to_silver_test >> player_metadata_bronze_to_silver_test >> position_metadata_bronze_to_silver_test >> teams_metadata_bronze_to_silver_test


if __name__ == "__main__":
    dag.cli()