from datetime import datetime
import logging
from airflow.providers.microsoft.azure.hooks.wasb import WasbHook

AZURE_BLOB_CONN_ID = 'azure_blob_conn_id'

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