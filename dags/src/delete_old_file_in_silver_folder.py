import logging
from airflow.providers.microsoft.azure.hooks.wasb import WasbHook
from airflow.providers.microsoft.azure.hooks.data_lake import AzureDataLakeStorageV2Hook


AZURE_BLOB_CONN_ID = 'azure_blob_conn_id'


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
            logging.info(f"Folder '{directory_to_delete}' deleted in silver container successfully.")
        except Exception as e:
            logging.error(f"Fail to delete directory {directory_to_delete} because of {str(e)}")
