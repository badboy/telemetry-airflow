"""
This is a processing job on top of BHR pings, migrated from Databricks and now running
as a scheduled Dataproc task.

BHR is related to the Background Hang Monitor in desktop Firefox.
See [bug 1675103](https://bugzilla.mozilla.org/show_bug.cgi?id=1675103)

The [job source](https://github.com/mozilla/python_mozetl/blob/main/mozetl/bhr_collection)
is maintained in the mozetl repository.
"""

import datetime

from airflow import DAG
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
from operators.task_sensor import ExternalTaskCompletedSensor
from airflow.operators.subdag_operator import SubDagOperator

from utils.dataproc import moz_dataproc_pyspark_runner, get_dataproc_parameters
from utils.tags import Tag

default_args = {
    "owner": "bewu@mozilla.com",
    "depends_on_past": False,
    "start_date": datetime.datetime(2020, 11, 26),
    "email": [
        "telemetry-alerts@mozilla.com",
        "bewu@mozilla.com",
        "dothayer@mozilla.com",
    ],
    "email_on_failure": True,
    "email_on_retry": True,
    "retries": 1,
    "retry_delay": datetime.timedelta(minutes=30),
}

tags = [Tag.ImpactTier.tier_1]

with DAG(
        "bhr_collection",
        default_args=default_args,
        schedule_interval="0 5 * * *",
        doc_md=__doc__,
        tags=tags,
) as dag:
    # Jobs read from/write to s3://telemetry-public-analysis-2/bhr/data/hang_aggregates/
    write_aws_conn_id = 'aws_dev_telemetry_public_analysis_2_rw'
    aws_access_key, aws_secret_key, _ = AwsBaseHook(aws_conn_id=write_aws_conn_id, client_type='s3').get_credentials()

    wait_for_bhr_ping = ExternalTaskCompletedSensor(
        task_id="wait_for_bhr_ping",
        external_dag_id="copy_deduplicate",
        external_task_id="copy_deduplicate_all",
        execution_delta=datetime.timedelta(hours=4),
        check_existence=True,
        mode="reschedule",
        pool="DATA_ENG_EXTERNALTASKSENSOR",
        email_on_retry=False,
        dag=dag,
    )

    params = get_dataproc_parameters("google_cloud_airflow_dataproc")

    bhr_collection = SubDagOperator(
        task_id="bhr_collection",
        dag=dag,
        subdag=moz_dataproc_pyspark_runner(
            parent_dag_name=dag.dag_id,
            image_version="1.5-debian10",
            dag_name="bhr_collection",
            default_args=default_args,
            cluster_name="bhr-collection-{{ ds }}",
            job_name="bhr-collection",
            python_driver_code="https://raw.githubusercontent.com/mozilla/python_mozetl/main/mozetl/bhr_collection/bhr_collection.py",
            init_actions_uris=["gs://dataproc-initialization-actions/python/pip-install.sh"],
            additional_metadata={"PIP_PACKAGES": "boto3==1.16.20 click==7.1.2"},
            additional_properties={
                "spark:spark.jars": "gs://spark-lib/bigquery/spark-bigquery-latest_2.12.jar",
                "spark-env:AWS_ACCESS_KEY_ID": aws_access_key,
                "spark-env:AWS_SECRET_ACCESS_KEY": aws_secret_key
            },
            py_args=[
                "--date", "{{ ds }}",
                "--sample-size", "0.5",
            ],
            idle_delete_ttl=14400,
            num_workers=6,
            worker_machine_type="n1-highmem-4",
            gcp_conn_id=params.conn_id,
            service_account=params.client_email,
            storage_bucket=params.storage_bucket,
        )
    )

    wait_for_bhr_ping >> bhr_collection
