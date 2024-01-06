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
    dag_id='fantasy_premier_league',
    default_args=default_args,
    description='To extract data from FPL and upload it into Azure',
    catchup=False, # Specify whether to catchu for missed runs
    schedule_interval=timedelta(days=1),
)


def extract_data_from_api(**kwargs):
    ti = kwargs['ti']
    api_result = ti.xcom_pull(task_ids='fetch_fpl_api_data')
    logging.info("API Result:", api_result)

    if not api_result:
        logging.error("API result not found in XCom")

    api_result_dict = json.loads(api_result)
    
    return api_result_dict['events'], api_result_dict['teams'], api_result_dict['elements'], api_result_dict['element_types']


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


def get_old_date(**kwargs):
    container_name = 'bronze'
    az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
    list_of_files = az_hook.get_blobs_list_recursive(container_name=container_name) #To get the first level blob name
    
    date_counts = set()
    for path in list_of_files:
        parts = path.split('/')
        if len(parts) > 2 and parts[2].isdigit() and "current" in parts:
            date_counts.add(parts[2])

    datetime_dates = [datetime.strptime(date, "%d%m%Y") for date in date_counts]
    min_date = min(datetime_dates)
    non_recent_date = min_date.strftime("%d%m%Y")
    logging.info(f"The old date is {non_recent_date}")

    current_date = datetime.now().strftime("%d%m%Y")

    if non_recent_date != current_date:
        kwargs['ti'].xcom_push(key='my_key', value=non_recent_date)
        logging.info(f"Date {non_recent_date} is pushed to xcom.")
    else:
        logging.info("Value is same as current date. Not pushing.")



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
            logging.info(f"Folder name is {folder_name}")
            blob_name = f"{folder_name}_{formatted_current_date}.json"
            blob_path = f"{folder_name}/current/{formatted_current_date}/{blob_name}"
            virtual_folder_path = f"{folder_name}/archive/{formatted_current_date}/"


            temp_dir = tempfile.mkdtemp()
            logging.info(f"Created local temporary folder - {temp_dir}")
            temp_file_path = os.path.join(temp_dir, blob_name)

            az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
            az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=blob_path)
            logging.info(f"File is downloaded at {temp_dir}")

            az_hook.load_file(
                        file_path=temp_file_path,
                        container_name=container_name,
                        blob_name=f"{virtual_folder_path}{blob_name}",
                        overwrite=True
                    )
            logging.info(f"File {blob_name} is copied to archive - {virtual_folder_path}")
    else:
        logging.info("No file is archived")


def delete_file_in_actual_folder(**kwargs):
    # Reference
    # https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/_api/airflow/providers/microsoft/azure/hooks/data_lake/index.html
    # https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/_api/airflow/providers/microsoft/azure/hooks/wasb/index.html

    ti = kwargs['ti']
    formatted_current_date = ti.xcom_pull(task_ids='get_old_date', key='my_key')

    if formatted_current_date is not None:
        container_name = 'bronze'

        file_system_name = 'bronze'


        # Delete directory and the file

        az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
        list_of_files = az_hook.get_blobs_list(container_name=container_name) #To get the first level blob name
        new_list_of_files = [original_string.replace('/', '') for original_string in list_of_files]

        for folder_name in new_list_of_files:
            directory_to_delete = f"{folder_name}/current/{formatted_current_date}"
            adls_hook = AzureDataLakeStorageV2Hook(adls_conn_id=AZURE_BLOB_CONN_ID)
            logging.info("Client is created")
            try:
                adls_hook.delete_directory(file_system_name, directory_to_delete)
                logging.info(f"Folder '{directory_to_delete}' deleted successfully.")
            except Exception as e:
                logging.error(f"Fail to delete folder {directory_to_delete} because of {str(e)}", exc_info=True)
    else:
        logging.info("No file is deleted")


def current_season_history_bronze_to_silver():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    formatted_current_date = myt_timestamp.strftime("%d%m%Y")

    temp_dir = tempfile.mkdtemp()
    logging.info(f"Temporary directory is created: {temp_dir}")

    bronze_blob_folder_path = f"current_season_history/current/{formatted_current_date}"
    blob_name = f"current_season_history_{formatted_current_date}.json"
    parquet_file_name = f"current_season_history_{formatted_current_date}.parquet"
    temp_file_path = os.path.join(temp_dir, blob_name)
    bronze_blob_path = os.path.join(bronze_blob_folder_path, blob_name)

    silver_blob_name = f"current_season_history/current/{formatted_current_date}/{parquet_file_name}"
    silver_parquet_file_full_path = os.path.join(temp_dir, parquet_file_name)

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=bronze_blob_path)
    logging.info(f"{blob_name} is downloaded at {temp_dir} from {bronze_blob_folder_path}")

    duckdb.sql(f"CREATE TABLE current_season_history AS SELECT * FROM read_json_auto('{temp_file_path}')")
    logging.info(f"Table current_season_history is created")
    duckdb.sql(f"COPY (SELECT * FROM current_season_history) TO '{silver_parquet_file_full_path}' (FORMAT PARQUET)")
    logging.info(f"Copy data from table current_season_history into file {parquet_file_name}")

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


def player_metadata_bronze_to_silver():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    formatted_current_date = myt_timestamp.strftime("%d%m%Y")

    temp_dir = tempfile.mkdtemp()
    logging.info(f"Temporary directory is created: {temp_dir}")

    bronze_blob_folder_path = f"player_metadata/current/{formatted_current_date}"
    blob_name = f"player_metadata_{formatted_current_date}.json"
    parquet_file_name = f"player_metadata_{formatted_current_date}.parquet"
    temp_file_path = os.path.join(temp_dir, blob_name)
    bronze_blob_path = os.path.join(bronze_blob_folder_path, blob_name)

    silver_blob_name = f"player_metadata/current/{formatted_current_date}/{parquet_file_name}"
    silver_parquet_file_full_path = os.path.join(temp_dir, parquet_file_name)

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=bronze_blob_path)
    logging.info(f"{blob_name} is downloaded at {temp_dir} from {bronze_blob_folder_path}")

    duckdb.sql(f"CREATE TABLE player_metadata AS SELECT *, CONCAT(first_name, ' ', second_name) as full_name, now_cost/10 as latest_price FROM read_json_auto('{temp_file_path}')")
    logging.info(f"Table player_metadata is created")
    duckdb.sql(f"COPY (SELECT * FROM player_metadata) TO '{silver_parquet_file_full_path}' (FORMAT PARQUET)")
    logging.info(f"Copy data from table player_metadata into file {parquet_file_name}")

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


def position_metadata_bronze_to_silver():
    current_utc_timestamp = datetime.utcnow()
    utc_timezone = pytz.timezone('UTC')
    myt_timezone = pytz.timezone('Asia/Kuala_Lumpur')
    myt_timestamp = utc_timezone.localize(current_utc_timestamp).astimezone(myt_timezone)
    formatted_current_date = myt_timestamp.strftime("%d%m%Y")

    temp_dir = tempfile.mkdtemp()
    logging.info(f"Temporary directory is created: {temp_dir}")

    bronze_blob_folder_path = f"position_metadata/current/{formatted_current_date}"
    blob_name = f"position_metadata_{formatted_current_date}.json"
    parquet_file_name = f"position_metadata_{formatted_current_date}.parquet"
    temp_file_path = os.path.join(temp_dir, blob_name)
    bronze_blob_path = os.path.join(bronze_blob_folder_path, blob_name)

    silver_blob_name = f"position_metadata/current/{formatted_current_date}/{parquet_file_name}"
    silver_parquet_file_full_path = os.path.join(temp_dir, parquet_file_name)

    az_hook = WasbHook.get_hook(AZURE_BLOB_CONN_ID)
    az_hook.get_file(file_path=temp_file_path, container_name='bronze', blob_name=bronze_blob_path)
    logging.info(f"{blob_name} is downloaded at {temp_dir} from {bronze_blob_folder_path}")

    duckdb.sql(f"CREATE TABLE position_metadata AS SELECT * FROM read_json_auto('{temp_file_path}')")
    logging.info(f"Table position_metadata is created")
    duckdb.sql(f"COPY (SELECT * FROM position_metadata) TO '{silver_parquet_file_full_path}' (FORMAT PARQUET)")
    logging.info(f"Copy data from table position_metadata into file {parquet_file_name}")

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


def get_silver_old_date(**kwargs):
    container_name = 'silver'
    az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
    list_of_files = az_hook.get_blobs_list_recursive(container_name=container_name) #To get the first level blob name
    logging.info(f"List of files - {list_of_files}")
    date_counts = set()
    for path in list_of_files:
        parts = path.split('/')
        logging.info(f"Parts - {parts}")
        if len(parts) > 2 and parts[2].isdigit() and "current" in parts:
            date_counts.add(parts[2])

    datetime_dates = [datetime.strptime(date, "%d%m%Y") for date in date_counts]
    logging.info(datetime_dates)
    min_date = min(datetime_dates)
    non_recent_date = min_date.strftime("%d%m%Y")
    logging.info(non_recent_date)

    current_date = datetime.now().strftime("%d%m%Y")

    if non_recent_date != current_date:
        kwargs['ti'].xcom_push(key='my_key', value=non_recent_date)
        logging.info(f"Date {non_recent_date} is pushed to xcom.")
    else:
        logging.info("Value is same as current date. Not pushing.")


def move_silver_file_into_archive_folder(**kwargs):
    ti = kwargs['ti']
    formatted_current_date = ti.xcom_pull(task_ids='get_silver_old_date', key='my_key')

    logging.info(f"Date processed is {formatted_current_date}")

    if formatted_current_date is not None:
            container_name = 'silver'

            az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
            list_of_files = az_hook.get_blobs_list(container_name=container_name) #To get the first level blob name
            new_list_of_files = [original_string.replace('/', '') for original_string in list_of_files]
            logging.info("File is renamed")
            logging.info(new_list_of_files)

            for folder_name in  new_list_of_files:
                logging.info(folder_name)
                blob_name = f"{folder_name}_{formatted_current_date}.parquet"
                blob_path = f"{folder_name}/current/{formatted_current_date}/{blob_name}"
                virtual_folder_path = f"{folder_name}/archive/{formatted_current_date}/"


                temp_dir = tempfile.mkdtemp()
                logging.info(f"Created local temporary folder - {temp_dir}")
                temp_file_path = os.path.join(temp_dir, blob_name)
                logging.info(f"Created full path to download blob into local temporary folder - {temp_file_path}")

                az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
                az_hook.get_file(file_path=temp_file_path, container_name=container_name, blob_name=blob_path)
                logging.info(f"File is downloaded at {temp_dir}")

                az_hook.load_file(
                            file_path=temp_file_path,
                            container_name=container_name,
                            blob_name=f"{virtual_folder_path}{blob_name}",
                            overwrite=True
                        )
                logging.info(f"File {blob_name} is copied to archive")
    else:
        logging.info("No file is archived")


def delete_old_file_in_silver_folder(**kwargs):
    # Reference
    # https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/_api/airflow/providers/microsoft/azure/hooks/data_lake/index.html
    # https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/_api/airflow/providers/microsoft/azure/hooks/wasb/index.html

    ti = kwargs['ti']
    formatted_current_date = ti.xcom_pull(task_ids='get_silver_old_date', key='my_key')
    logging.info(f"Date processed is {formatted_current_date}")

    container_name = 'silver'

    file_system_name = 'silver'
    

    # Delete directory and the file

    az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
    list_of_files = az_hook.get_blobs_list(container_name=container_name) #To get the first level blob name
    new_list_of_files = [original_string.replace('/', '') for original_string in list_of_files]

    for folder_name in new_list_of_files:
        directory_to_delete = f"{folder_name}/current/{formatted_current_date}"
        adls_hook = AzureDataLakeStorageV2Hook(adls_conn_id=AZURE_BLOB_CONN_ID)
        logging.info("Client is created")
        try:
            adls_hook.delete_directory(file_system_name, directory_to_delete)
            logging.info(f"Folder '{directory_to_delete}' deleted successfully.")
        except Exception as e:
            logging.error(f"Fail to delete directory {directory_to_delete} because of {str(e)}")



fetch_fpl_api_data_task = SimpleHttpOperator(
    task_id='fetch_fpl_api_data',
    http_conn_id='fpl_api',
    method='GET',
    endpoint='/api/bootstrap-static/',
    headers={"Content-Type": "application/json"},
    dag=dag,
)

upload_to_blob_task = PythonOperator(
    task_id='upload_to_blob',
    python_callable=upload_to_blob,
    provide_context=True,
    dag=dag,
)


extract_data_from_api_task = PythonOperator(
    task_id='extract_data_from_api',
    python_callable=extract_data_from_api,
    provide_context=True,
    dag=dag,
)


download_file_from_blob_task = PythonOperator(
    task_id='download_file_from_blob',
    python_callable=download_file_from_blob,
    provide_context=True,
    dag=dag,
)


move_bronze_file_into_archive_folder = PythonOperator(
    task_id='move_bronze_file_into_archive_folder',
    python_callable=move_bronze_file_into_archive_folder,
    provide_context=True,
    dag=dag,
)


delete_file_in_actual_folder = PythonOperator(
    task_id='delete_file_in_actual_folder',
    python_callable=delete_file_in_actual_folder,
    provide_context=True,
    dag=dag,
)


get_old_date = PythonOperator(
    task_id='get_old_date',
    python_callable=get_old_date,
    provide_context=True,
    dag=dag
)


current_season_history_bronze_to_silver = PythonOperator(
    task_id='current_season_history_bronze_to_silver',
    python_callable=current_season_history_bronze_to_silver,
    provide_context=True,
    dag=dag,
)

player_metadata_bronze_to_silver = PythonOperator(
    task_id='player_metadata_bronze_to_silver',
    python_callable=player_metadata_bronze_to_silver,
    provide_context=True,
    dag=dag,
)

position_metadata_bronze_to_silver = PythonOperator(
    task_id='position_metadata_bronze_to_silver',
    python_callable=position_metadata_bronze_to_silver,
    provide_context=True,
    dag=dag,
)

teams_metadata_bronze_to_silver = PythonOperator(
    task_id='teams_metadata_bronze_to_silver',
    python_callable=teams_metadata_bronze_to_silver,
    provide_context=True,
    dag=dag,
)


get_silver_old_date = PythonOperator(
    task_id='get_silver_old_date',
    python_callable=get_silver_old_date,
    provide_context=True,
    dag=dag,
)


move_silver_file_into_archive_folder = PythonOperator(
    task_id='move_silver_file_into_archive_folder',
    python_callable=move_silver_file_into_archive_folder,
    provide_context=True,
    dag=dag,
)


delete_old_file_in_silver_folder = PythonOperator(
    task_id='delete_old_file_in_silver_folder',
    python_callable=delete_old_file_in_silver_folder,
    provide_context=True,
    dag=dag,
)

# Reference
# https://cloudshuttle.com.au/blog/2022-10/setting_up_airflow
# https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/_api/airflow/providers/microsoft/azure/hooks/wasb/index.html
# https://dzone.com/articles/simplehttpoperator-in-apache-airflow

fetch_fpl_api_data_task >> extract_data_from_api_task >> upload_to_blob_task >> download_file_from_blob_task  >> get_old_date >> move_bronze_file_into_archive_folder >> delete_file_in_actual_folder >> [current_season_history_bronze_to_silver, player_metadata_bronze_to_silver, position_metadata_bronze_to_silver, teams_metadata_bronze_to_silver] >> get_silver_old_date >> move_silver_file_into_archive_folder >> delete_old_file_in_silver_folder

if __name__ == "__main__":
    dag.cli()