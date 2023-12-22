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

def get_silver_old_date_test(**kwargs):
    container_name = 'silver'
    az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
    list_of_files = az_hook.get_blobs_list_recursive(container_name=container_name) #To get the first level blob name
    print(f"List of files - {list_of_files}")
    date_counts = set()
    for path in list_of_files:
        parts = path.split('/')
        print(f"Parts - {parts}")
        if len(parts) > 2 and parts[2].isdigit() and "current" in parts:
            date_counts.add(parts[2])

    datetime_dates = [datetime.strptime(date, "%d%m%Y") for date in date_counts]
    print(datetime_dates)
    min_date = min(datetime_dates)
    non_recent_date = min_date.strftime("%d%m%Y")
    print(non_recent_date)

    kwargs['ti'].xcom_push(key='my_key', value=non_recent_date)


def move_silver_file_into_archive_folder_test(**kwargs):
    ti = kwargs['ti']
    formatted_current_date = ti.xcom_pull(task_ids='get_silver_old_date_test', key='my_key')

    print(f"value {formatted_current_date}")
    
    container_name = 'silver'
    
    az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
    list_of_files = az_hook.get_blobs_list(container_name=container_name) #To get the first level blob name
    new_list_of_files = [original_string.replace('/', '') for original_string in list_of_files]
    print("File is renamed")
    print(new_list_of_files)
 
    for folder_name in  new_list_of_files:
        print(folder_name)
        blob_name = f"{folder_name}_{formatted_current_date}.parquet"
        blob_path = f"{folder_name}/current/{formatted_current_date}/{blob_name}"
        virtual_folder_path = f"{folder_name}/archive/{formatted_current_date}/"


        temp_dir = tempfile.mkdtemp()
        print("Created local temporary folder")
        print(blob_path)
        temp_file_path = os.path.join(temp_dir, blob_name)

        az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
        az_hook.get_file(file_path=temp_file_path, container_name=container_name, blob_name=blob_path)
        print(f"File is downloaded at {temp_dir}")

        az_hook.load_file(
                    file_path=temp_file_path,
                    container_name=container_name,
                    blob_name=f"{virtual_folder_path}{blob_name}",
                    overwrite=True
                )
        print(f"File is copied to archive")


def delete_old_file_in_silver_folder_test(**kwargs):
    # Reference
    # https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/_api/airflow/providers/microsoft/azure/hooks/data_lake/index.html
    # https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/_api/airflow/providers/microsoft/azure/hooks/wasb/index.html

    ti = kwargs['ti']
    formatted_current_date = ti.xcom_pull(task_ids='get_silver_old_date_test', key='my_key')

    container_name = 'silver'

    file_system_name = 'silver'
    

    # Delete directory and the file

    az_hook = WasbHook(wasb_conn_id=AZURE_BLOB_CONN_ID)
    list_of_files = az_hook.get_blobs_list(container_name=container_name) #To get the first level blob name
    new_list_of_files = [original_string.replace('/', '') for original_string in list_of_files]

    for folder_name in new_list_of_files:
        directory_to_delete = f"{folder_name}/current/{formatted_current_date}"
        adls_hook = AzureDataLakeStorageV2Hook(adls_conn_id=AZURE_BLOB_CONN_ID)
        print("Client is created")
        try:
            adls_hook.delete_directory(file_system_name, directory_to_delete)
            print(f"Folder '{directory_to_delete}' deleted successfully.")
        except Exception as e:
            print(f"Fail to delete because of {str(e)}")
    


get_silver_old_date_test = PythonOperator(
    task_id='get_silver_old_date_test',
    python_callable=get_silver_old_date_test,
    provide_context=True,
    dag=dag,
)


move_silver_file_into_archive_folder_test = PythonOperator(
    task_id='move_silver_file_into_archive_folder_test',
    python_callable=move_silver_file_into_archive_folder_test,
    provide_context=True,
    dag=dag,
)


delete_old_file_in_silver_folder_test = PythonOperator(
    task_id='delete_old_file_in_silver_folder_test',
    python_callable=delete_old_file_in_silver_folder_test,
    provide_context=True,
    dag=dag,
)


get_silver_old_date_test >> move_silver_file_into_archive_folder_test >> delete_old_file_in_silver_folder_test


if __name__ == "__main__":
    dag.cli()