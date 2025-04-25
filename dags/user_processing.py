#imports
from airflow import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator # type: ignore
from airflow.providers.http.sensors.http import HttpSensor # type: ignore
from airflow.providers.http.operators.http import SimpleHttpOperator 
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

import json
from pandas import json_normalize
from datetime import datetime

def _process_user(ti):
    user = ti.xcom_pull(task_ids="extract_user")
    user = user['results'][0]
    processed_user = json_normalize({
        'firstname': user['name']['first'],
        'lastname': user['name']['last'],
        'country': user['location']['country'],
        'username': user['login']['username'],
        'password': user['login']['password'],
        'email': user['email']
    })
    processed_user.to_csv('/tmp/processed_user.csv', index=None, header=False)

def _store_user():
    '''python function used to interact with database by using the postgres hook '''
    hook = PostgresHook(postgres_conn_id ='postgres') #instantiate postgres hook
    hook.copy_expert(
        sql= "COPY users FROM stdin WITH DELIMITER as ','", #copy users from file into the table users we created in the first task, I guess stdin is the csv? 
        filename='/tmp/processed_user.csv'
    ) #in order to make copy from CSV file into table users


with DAG(
    dag_id = 'user_processing',
    start_date = datetime(2022, 1, 1),
    schedule_interval='@daily',
    catchup=False
)as dag:

#creates a table via Postgres SQL provider 
    create_table = PostgresOperator(
        task_id='create_table',
        postgres_conn_id ='postgres',
        sql = '''
            CREATE TABLE IF NOT EXISTS users (
                firstname TEXT NOT NULL,
                lastname TEXT NOT NULL,
                country TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                email TEXT NOT NULL);
            '''
    ) 
#checks if API is available or not, via API provider
    is_api_available = HttpSensor(
        task_id='is_api_available',
        http_conn_id='user_api',
        endpoint='api/'

    )

    extract_user = SimpleHttpOperator(
        task_id = 'extract_user',
        http_conn_id='user_api',
        endpoint='api/', 
        method='GET', #request the API, not send any data
        response_filter=lambda response: json.loads(response.text), #to extract the data and transform it in a JSON format
        log_response=True #log the response so you can see the response you get in the logs on the UI
    )

    process_user = PythonOperator(
        task_id = 'process_user',
        python_callable=_process_user #run the function
    )

    #uses the postgreshook in order to copy the users from this file into the table
    store_user = PythonOperator(
        task_id='store_user',
        python_callable=_store_user
    )

    create_table >> is_api_available >> extract_user >> process_user >> store_user