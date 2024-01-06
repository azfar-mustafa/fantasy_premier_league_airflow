from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python_operator import PythonOperator

# Define default_args dictionary to specify default parameters for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Define the DAG
dag = DAG(
    'remote_logging_test',
    default_args=default_args,
    description='A simple DAG to test remote logging',
    schedule_interval=timedelta(days=1),
)

# Define a Python function to be executed by the task
def print_hello():
    print("Hello, this is a test message!")

# Create a PythonOperator task
task_print_hello = PythonOperator(
    task_id='print_hello_task',
    python_callable=print_hello,
    dag=dag,
)

# Set the task dependencies
task_print_hello

if __name__ == "__main__":
    dag.cli()
