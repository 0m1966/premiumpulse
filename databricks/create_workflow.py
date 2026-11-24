"""Programmatically creates and deploys the PremiumPulse Medallion Workflow Job.

Uses databricks-sdk to provision an idempotent, 5-task DAG:
setup_volume -> bronze_autoloader -> silver_trips -> gold_risk_scores -> export_to_snowflake
"""

import sys
from premiumpulse.config.settings import get_settings


def deploy_workflow() -> bool:
    """Deploy or update Databricks Workflow Job."""
    settings = get_settings()

    print("=" * 60)
    print("PremiumPulse: Databricks Workflow Job Deployment")
    print("=" * 60)

    if not settings.is_databricks_configured:
        print("[INFO] Databricks credentials are not configured in your .env file.")
        print("Required variables: DATABRICKS_HOST, DATABRICKS_TOKEN")
        print("The offline local pipeline and snapshot mode are fully active.")
        print("When connecting to a live workspace, configure .env and rerun this script.")
        print("=" * 60)
        return False

    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service import jobs

        w = WorkspaceClient(
            host=settings.DATABRICKS_HOST,
            token=settings.DATABRICKS_TOKEN,
        )

        job_name = "PremiumPulse-Telematics-Pipeline"
        print(f"Connecting to {settings.DATABRICKS_HOST}...")
        ws_user = w.current_user.me().user_name
        base_nb_path = f"/Users/{ws_user}/PremiumPulse/notebooks"

        base_params = {
            "catalog": settings.DATABRICKS_CATALOG,
            "schema": settings.DATABRICKS_SCHEMA,
            "volume": settings.DATABRICKS_VOLUME,
        }

        task_setup = jobs.Task(
            task_key="setup_volume",
            description="Initializes landing volume and database schema",
            notebook_task=jobs.NotebookTask(
                notebook_path=f"{base_nb_path}/00_setup_volume",
                base_parameters=base_params,
            ),
        )

        task_bronze = jobs.Task(
            task_key="bronze_autoloader",
            description="Ingests raw events with Auto Loader schema evolution",
            depends_on=[jobs.TaskDependency(task_key="setup_volume")],
            notebook_task=jobs.NotebookTask(
                notebook_path=f"{base_nb_path}/01_bronze_autoloader",
                base_parameters=base_params,
            ),
        )

        task_silver = jobs.Task(
            task_key="silver_trips",
            description="Cleans events, sessionizes trips, routes rejected records",
            depends_on=[jobs.TaskDependency(task_key="bronze_autoloader")],
            notebook_task=jobs.NotebookTask(
                notebook_path=f"{base_nb_path}/02_silver_trips",
                base_parameters=base_params,
            ),
        )

        task_gold = jobs.Task(
            task_key="gold_risk_scores",
            description="Calculates Scorecard v1 points and builds Star Schema",
            depends_on=[jobs.TaskDependency(task_key="silver_trips")],
            notebook_task=jobs.NotebookTask(
                notebook_path=f"{base_nb_path}/03_gold_risk_scores",
                base_parameters=base_params,
            ),
        )

        task_export = jobs.Task(
            task_key="export_to_snowflake",
            description="Exports Gold tables to Parquet for Snowflake staging",
            depends_on=[jobs.TaskDependency(task_key="gold_risk_scores")],
            notebook_task=jobs.NotebookTask(
                notebook_path=f"{base_nb_path}/04_export_to_snowflake",
                base_parameters=base_params,
            ),
        )

        tasks = [task_setup, task_bronze, task_silver, task_gold, task_export]

        print(f"Creating or updating Databricks Job: {job_name} with 5 tasks...")
        existing_jobs = list(w.jobs.list(name=job_name))
        if existing_jobs:
            job_id = existing_jobs[0].job_id
            w.jobs.reset(job_id=job_id, new_settings=jobs.JobSettings(name=job_name, tasks=tasks))
            print(f"[SUCCESS] Updated existing Workflow Job ID: {job_id}")
        else:
            created = w.jobs.create(name=job_name, tasks=tasks)
            print(f"[SUCCESS] Created new Workflow Job ID: {created.job_id}")

        return True

    except Exception as exc:
        print(f"[ERROR] Failed to deploy Databricks Workflow: {exc}")
        return False


if __name__ == "__main__":
    success = deploy_workflow()
    sys.exit(0 if success else 1)
