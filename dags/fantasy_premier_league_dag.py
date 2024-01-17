from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.http_operator import SimpleHttpOperator

from src.fantasyPremierLeague_fileProcessing import FantasyPremierLeague


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
    python_callable=FantasyPremierLeague.upload_to_blob,
    op_kwargs = ['ti'],
    provide_context=True,
    dag=dag,
)

extract_data_from_api_task = PythonOperator(
    task_id='extract_data_from_api',
    python_callable=FantasyPremierLeague.extract_data_from_api,
    provide_context=True,
    dag=dag,
)

download_file_from_blob_task = PythonOperator(
    task_id='download_file_from_blob',
    python_callable=FantasyPremierLeague.download_file_from_blob,
    provide_context=True,
    dag=dag,
)


get_old_date_task = PythonOperator(
    task_id='get_old_date',
    python_callable=FantasyPremierLeague.get_old_date,
    provide_context=True,
    dag=dag
)


move_bronze_file_into_archive_folder_task = PythonOperator(
    task_id='move_bronze_file_into_archive_folder',
    python_callable=FantasyPremierLeague.move_bronze_file_into_archive_folder,
    provide_context=True,
    dag=dag,
)


delete_file_in_actual_folder_task = PythonOperator(
    task_id='delete_file_in_actual_folder',
    python_callable=FantasyPremierLeague.delete_file_in_actual_folder,
    provide_context=True,
    dag=dag,
)


current_season_history_bronze_to_silver_task = PythonOperator(
    task_id='current_season_history_bronze_to_silver',
    python_callable=FantasyPremierLeague.current_season_history_bronze_to_silver,
    provide_context=True,
    dag=dag,
)


player_metadata_bronze_to_silver_task = PythonOperator(
    task_id='player_metadata_bronze_to_silver',
    python_callable=FantasyPremierLeague.player_metadata_bronze_to_silver,
    provide_context=True,
    dag=dag,
)


position_metadata_bronze_to_silver_task = PythonOperator(
    task_id='position_metadata_bronze_to_silver',
    python_callable=FantasyPremierLeague.position_metadata_bronze_to_silver,
    provide_context=True,
    dag=dag,
)


teams_metadata_bronze_to_silver_task = PythonOperator(
    task_id='teams_metadata_bronze_to_silver',
    python_callable=FantasyPremierLeague.teams_metadata_bronze_to_silver,
    provide_context=True,
    dag=dag,
)


get_silver_old_date_task = PythonOperator(
    task_id='get_silver_old_date',
    python_callable=FantasyPremierLeague.get_silver_old_date,
    provide_context=True,
    dag=dag,
)


move_silver_file_into_archive_folder_task = PythonOperator(
    task_id='move_silver_file_into_archive_folder',
    python_callable=FantasyPremierLeague.move_silver_file_into_archive_folder,
    provide_context=True,
    dag=dag,
)


delete_old_file_in_silver_folder_task = PythonOperator(
    task_id='delete_old_file_in_silver_folder',
    python_callable=FantasyPremierLeague.delete_old_file_in_silver_folder,
    provide_context=True,
    dag=dag,
)

# Reference
# https://cloudshuttle.com.au/blog/2022-10/setting_up_airflow
# https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/_api/airflow/providers/microsoft/azure/hooks/wasb/index.html
# https://dzone.com/articles/simplehttpoperator-in-apache-airflow

fetch_fpl_api_data_task >> extract_data_from_api_task >> upload_to_blob_task >> download_file_from_blob_task  >> get_old_date_task >> move_bronze_file_into_archive_folder_task >> delete_file_in_actual_folder_task >> [current_season_history_bronze_to_silver_task, player_metadata_bronze_to_silver_task, position_metadata_bronze_to_silver_task, teams_metadata_bronze_to_silver_task] >> get_silver_old_date_task >> move_silver_file_into_archive_folder_task >> delete_old_file_in_silver_folder_task

if __name__ == "__main__":
    dag.cli()