import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "roombeacon",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


def task_healthcheck() -> str:
    """In thông điệp xác nhận trạng thái hoạt động của Airflow orchestration."""
    message = "RoomBeacon Airflow Orchestration is OK"
    print(message)
    return message


def task_print_env() -> str:
    """In tên môi trường hiện tại từ biến môi trường."""
    env_name = os.getenv("ROOMBEACON_ENV", "development")
    output = f"Current Environment: {env_name}"
    print(output)
    return output


with DAG(
    dag_id="roombeacon_system_healthcheck",
    default_args=default_args,
    description="System DAG kiểm tra trạng thái hoạt động của RoomBeacon Airflow",
    schedule_interval=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["system", "healthcheck", "roombeacon"],
) as dag:
    t1 = PythonOperator(
        task_id="check_airflow_status",
        python_callable=task_healthcheck,
    )

    t2 = PythonOperator(
        task_id="print_environment_name",
        python_callable=task_print_env,
    )

    t1 >> t2
