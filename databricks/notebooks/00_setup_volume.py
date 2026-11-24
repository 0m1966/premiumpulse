# Databricks notebook source
# COMMAND ----------
# DBTITLE 1,PremiumPulse: 00 - Setup Unity Catalog Volume Landing Zone
# MAGIC %md
# MAGIC ### Setup Pipeline Landing Zone
# MAGIC Creates the Unity Catalog database/schema and landing Volume for raw telematics batch files.

# COMMAND ----------
dbutils.widgets.text("catalog", "workspace", "Unity Catalog Name")
dbutils.widgets.text("schema", "premiumpulse", "Database / Schema Name")
dbutils.widgets.text("volume", "landing_zone", "Landing Volume Name")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")

print(f"Initializing catalog={catalog}, schema={schema}, volume={volume}")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema};")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume};")

volume_path = f"/Volumes/{catalog}/{schema}/{volume}"
print(f"[SUCCESS] Landing zone volume ready at: {volume_path}")
