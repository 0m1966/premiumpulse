# Databricks notebook source
# COMMAND ----------
# DBTITLE 1,PremiumPulse: 01 - Bronze Auto Loader Ingestion
# MAGIC %md
# MAGIC ### Pipeline Stage: Bronze Ingestion
# MAGIC Ingests telematics event files and driver/vehicle master tables using Databricks Auto Loader (`cloudFiles`).
# MAGIC 
# MAGIC Principles:
# MAGIC 1. **Append-Only**: Raw Bronze tables are never mutated.
# MAGIC 2. **Metadata Enrichment**: Enriched with `_source_file` and `_ingested_at`.
# MAGIC 3. **Schema Evolution**: Automatically tracks column schema evolution (`schemaEvolutionMode=addNewColumns`).
# MAGIC 4. **Incremental**: `.trigger(availableNow=True)` for bounded, cost-effective serverless execution.

# COMMAND ----------
from pyspark.sql.functions import current_timestamp, col

dbutils.widgets.text("catalog", "workspace", "Unity Catalog Name")
dbutils.widgets.text("schema", "premiumpulse", "Database / Schema Name")
dbutils.widgets.text("volume", "landing_zone", "Landing Volume Name")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")

volume_base = f"/Volumes/{catalog}/{schema}/{volume}"
checkpoint_base = f"/Volumes/{catalog}/{schema}/{volume}/_checkpoints"

# COMMAND ----------
# DBTITLE 1,Ingest Bronze Drivers Master
print("Ingesting Bronze Drivers...")
drivers_stream = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "csv")
    .option("cloudFiles.inferColumnTypes", "true")
    .option("cloudFiles.schemaLocation", f"{checkpoint_base}/bronze_drivers_schema")
    .option("header", "true")
    .load(f"{volume_base}/drivers*.csv")
    .withColumn("_source_file", col("_metadata.file_path"))
    .withColumn("_ingested_at", current_timestamp())
)

query_drivers = (
    drivers_stream.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", f"{checkpoint_base}/bronze_drivers_chk")
    .trigger(availableNow=True)
    .toTable(f"{catalog}.{schema}.bronze_drivers")
)
query_drivers.awaitTermination()
print(f"Bronze Drivers count: {spark.table(f'{catalog}.{schema}.bronze_drivers').count()}")

# COMMAND ----------
# DBTITLE 1,Ingest Bronze Vehicles Master
print("Ingesting Bronze Vehicles...")
vehicles_stream = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "csv")
    .option("cloudFiles.inferColumnTypes", "true")
    .option("cloudFiles.schemaLocation", f"{checkpoint_base}/bronze_vehicles_schema")
    .option("header", "true")
    .load(f"{volume_base}/vehicles*.csv")
    .withColumn("_source_file", col("_metadata.file_path"))
    .withColumn("_ingested_at", current_timestamp())
)

query_vehicles = (
    vehicles_stream.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", f"{checkpoint_base}/bronze_vehicles_chk")
    .trigger(availableNow=True)
    .toTable(f"{catalog}.{schema}.bronze_vehicles")
)
query_vehicles.awaitTermination()
print(f"Bronze Vehicles count: {spark.table(f'{catalog}.{schema}.bronze_vehicles').count()}")

# COMMAND ----------
# DBTITLE 1,Ingest Bronze Telematics Events (Batches + Schema Drift)
print("Ingesting Bronze Telematics Events with Auto Loader Schema Evolution...")
events_stream = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "csv")
    .option("cloudFiles.inferColumnTypes", "true")
    .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
    .option("cloudFiles.schemaLocation", f"{checkpoint_base}/bronze_events_schema")
    .option("header", "true")
    .load(f"{volume_base}/events_*.csv")
    .withColumn("_source_file", col("_metadata.file_path"))
    .withColumn("_ingested_at", current_timestamp())
)

query_events = (
    events_stream.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", f"{checkpoint_base}/bronze_events_chk")
    .trigger(availableNow=True)
    .toTable(f"{catalog}.{schema}.bronze_telematics_events")
)
query_events.awaitTermination()
print(f"Bronze Telematics Events count: {spark.table(f'{catalog}.{schema}.bronze_telematics_events').count()}")
