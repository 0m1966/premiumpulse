# Databricks notebook source
# COMMAND ----------
# DBTITLE 1,PremiumPulse: 02 - Silver Cleaning, Trip Sessionization & Quality Guardrails
# MAGIC %md
# MAGIC ### Pipeline Stage: Silver Cleaning & Sessionization
# MAGIC 1. **Deduplication**: `row_number() OVER (PARTITION BY event_id ORDER BY _ingested_at DESC) = 1`
# MAGIC 2. **Data Quality Validation**: Speed bounds, GPS limits, non-null timestamps. Rejected rows route to `silver_rejected_events`.
# MAGIC 3. **Trip Sessionization**: 15-minute gap threshold via `lag()` + cumulative sum window over `(driver_id, vehicle_id)`.
# MAGIC 4. **Distance Calculation**: Pure Spark SQL Haversine expression (no UDF).
# MAGIC 5. **Conditional Aggregation**: Computes trip-level risk metrics.

# COMMAND ----------
from pyspark.sql.functions import (
    col, to_timestamp, row_number, when, lit, lag, sum as spark_sum,
    count, min as spark_min, max as spark_max, avg as spark_avg,
    asin, sqrt, sin, cos, radians, hour, current_timestamp
)
from pyspark.sql.window import Window

dbutils.widgets.text("catalog", "workspace", "Unity Catalog Name")
dbutils.widgets.text("schema", "premiumpulse", "Database / Schema Name")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Target Schema: {catalog}.{schema}")

# COMMAND ----------
# DBTITLE 1,Step 1: Deduplication & Quality Filtering on Bronze Events
bronze_events = spark.table(f"{catalog}.{schema}.bronze_telematics_events")

# Deduplicate by event_id
dedup_window = Window.partitionBy("event_id").orderBy(col("_ingested_at").desc())
events_dedup = (
    bronze_events
    .withColumn("row_num", row_number().over(dedup_window))
    .withColumn("is_duplicate", col("row_num") > 1)
)

# Quality Rule Classifications
events_tagged = (
    events_dedup
    .withColumn("ts_parsed", to_timestamp(col("event_ts"), "yyyy-MM-dd HH:mm:ss"))
    .withColumn(
        "reject_reason",
        when(col("is_duplicate"), lit("ERR_DUPLICATE_EVENT_ID"))
        .when(col("ts_parsed").isNull(), lit("ERR_NULL_EVENT_TS"))
        .when((col("speed_kmh") < 0.0) | (col("speed_kmh") > 250.0), lit("ERR_INVALID_SPEED"))
        .when((col("latitude") < -90.0) | (col("latitude") > 90.0) | (col("longitude") < -180.0) | (col("longitude") > 180.0), lit("ERR_INVALID_GPS"))
        .otherwise(lit(None))
    )
)

# Route Defective Records to silver_rejected_events
rejected_df = (
    events_tagged
    .filter(col("reject_reason").isNotNull())
    .select("event_id", "driver_id", "vehicle_id", "event_ts", "reject_reason", "_ingested_at")
)
rejected_df.write.format("delta").mode("append").saveAsTable(f"{catalog}.{schema}.silver_rejected_events")

# Filter Clean Events
clean_events = (
    events_tagged
    .filter(col("reject_reason").isNull())
    .select(
        "event_id", "driver_id", "vehicle_id", "trip_hint",
        col("ts_parsed").alias("event_ts"),
        col("latitude").cast("double"),
        col("longitude").cast("double"),
        col("speed_kmh").cast("double"),
        col("speed_limit_kmh").cast("double"),
        col("accel_ms2").cast("double"),
        when(col("phone_in_use").cast("string").isin("1", "true", "True"), lit(1)).otherwise(lit(0)).alias("phone_in_use"),
    )
)

# COMMAND ----------
# DBTITLE 1,Step 2: Sessionize Trips (15-Minute Inactivity Window)
driver_time_win = Window.partitionBy("driver_id", "vehicle_id").orderBy("event_ts")

events_with_lag = (
    clean_events
    .withColumn("prev_ts", lag("event_ts", 1).over(driver_time_win))
    .withColumn("gap_seconds", col("event_ts").cast("long") - col("prev_ts").cast("long"))
    .withColumn("is_new_trip", when((col("gap_seconds") > 900) | col("prev_ts").isNull(), lit(1)).otherwise(lit(0)))
)

trip_session_win = Window.partitionBy("driver_id", "vehicle_id").orderBy("event_ts").rowsBetween(Window.unboundedPreceding, Window.currentRow)

sessionized_events = (
    events_with_lag
    .withColumn("session_idx", spark_sum("is_new_trip").over(trip_session_win))
    .withColumn("generated_trip_id", col("trip_hint")) # Or concat(driver_id, lit("_TRP_"), session_idx)
)

# Haversine distance step between consecutive points
events_with_coords = (
    sessionized_events
    .withColumn("prev_lat", lag("latitude", 1).over(driver_time_win))
    .withColumn("prev_lon", lag("longitude", 1).over(driver_time_win))
)

# Pure Spark SQL Haversine Distance (in Kilometers)
haversine_km = (
    lit(2.0) * lit(6371.0) * asin(
        sqrt(
            sin(radians(col("latitude") - col("prev_lat")) / lit(2.0)) ** 2 +
            cos(radians(col("prev_lat"))) * cos(radians(col("latitude"))) *
            (sin(radians(col("longitude") - col("prev_lon")) / lit(2.0)) ** 2)
        )
    )
)

events_with_dist = events_with_coords.withColumn(
    "step_distance_km",
    when(col("prev_lat").isNull() | (col("is_new_trip") == 1), lit(0.0)).otherwise(haversine_km)
)

# COMMAND ----------
# DBTITLE 1,Step 3: Aggregate Trip Metrics into silver_trips
silver_trips_df = (
    events_with_dist
    .groupBy("generated_trip_id", "driver_id", "vehicle_id")
    .agg(
        spark_min("event_ts").alias("trip_start"),
        spark_max("event_ts").alias("trip_end"),
        spark_sum(when(col("step_distance_km").isNotNull(), col("step_distance_km")).otherwise(lit(0.0))).alias("distance_km"),
        (count("*") * 30 / 60).cast("int").alias("duration_min"),
        spark_sum(when(col("accel_ms2") <= -3.0, 1).otherwise(0)).alias("hard_brake_count"),
        spark_sum(when(col("accel_ms2") >= 3.0, 1).otherwise(0)).alias("hard_accel_count"),
        spark_sum(when(col("speed_kmh") > (col("speed_limit_kmh") + 10.0), 30).otherwise(0)).alias("speeding_seconds"),
        spark_sum(when(hour("event_ts").isin(0, 1, 2, 3), 30).otherwise(0)).alias("night_seconds"),
        spark_sum(when(col("phone_in_use") == 1, 30).otherwise(0)).alias("phone_seconds"),
    )
    .withColumnRenamed("generated_trip_id", "trip_id")
    .withColumn("_silver_at", current_timestamp())
)

silver_trips_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.silver_trips")
print(f"Silver Trips count: {spark.table(f'{catalog}.{schema}.silver_trips').count()}")
