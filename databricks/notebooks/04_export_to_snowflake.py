# Databricks notebook source
# COMMAND ----------
# DBTITLE 1,PremiumPulse: 04 - Export Gold Data to Snowflake
# MAGIC %md
# MAGIC ### Pipeline Stage: Snowflake Ingestion Bridge
# MAGIC Exports Gold tables (`gold_driver_risk_score`, `gold_dim_driver`, `gold_dim_vehicle`, `gold_fact_trip`)
# MAGIC to Snowflake RAW stage using Parquet export or the Spark-Snowflake Connector.

# COMMAND ----------
dbutils.widgets.text("catalog", "workspace", "Unity Catalog Name")
dbutils.widgets.text("schema", "premiumpulse", "Database / Schema Name")
dbutils.widgets.text("export_path", "/Volumes/workspace/premiumpulse/landing_zone/snowflake_export", "Export Directory")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
export_path = dbutils.widgets.get("export_path")

print(f"Exporting Gold tables from {catalog}.{schema} to {export_path}")

tables = ["gold_driver_risk_score", "gold_dim_driver", "gold_dim_vehicle", "gold_fact_trip"]

for tbl in tables:
    df = spark.table(f"{catalog}.{schema}.{tbl}")
    target_dir = f"{export_path}/{tbl}"
    df.write.format("parquet").mode("overwrite").save(target_dir)
    print(f"Exported {tbl} ({df.count()} rows) -> {target_dir}")

print("[SUCCESS] All Gold tables exported for Snowflake ingestion.")
