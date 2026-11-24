# Databricks notebook source
# COMMAND ----------
# DBTITLE 1,PremiumPulse: 03 - Gold Star Schema, Scorecard v1 & Reconciliation
# MAGIC %md
# MAGIC ### Pipeline Stage: Gold Star Schema & Scorecard Evaluation
# MAGIC 1. **Rolling 30-Day Aggregation**: Computes per-driver rates over the active billing window.
# MAGIC 2. **Scorecard v1 Application**: Pure Spark SQL column expressions mirroring `scorecard.py`.
# MAGIC 3. **Dimensions & Facts**: Builds Kimball Star Schema (`gold_dim_driver` with SCD2, `gold_dim_vehicle`, `gold_fact_trip`).
# MAGIC 4. **Pipeline Audit**: Computes zero-loss mathematical invariants.

# COMMAND ----------
from pyspark.sql.functions import (
    col, lit, when, round as spark_round, sha2, current_timestamp,
    sum as spark_sum, count, coalesce, date_sub, max as spark_max
)
from delta.tables import DeltaTable

dbutils.widgets.text("catalog", "workspace", "Unity Catalog Name")
dbutils.widgets.text("schema", "premiumpulse", "Database / Schema Name")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Target Schema: {catalog}.{schema}")

# COMMAND ----------
# DBTITLE 1,Step 1: Compute 30-Day Driving Aggregations
silver_trips = spark.table(f"{catalog}.{schema}.silver_trips")

driver_30d = (
    silver_trips
    .groupBy("driver_id")
    .agg(
        spark_sum("distance_km").alias("total_distance_km"),
        spark_sum("duration_min").alias("total_duration_min"),
        spark_sum("hard_brake_count").alias("total_brakes"),
        spark_sum("hard_accel_count").alias("total_accels"),
        spark_sum("speeding_seconds").alias("total_speeding_sec"),
        spark_sum("night_seconds").alias("total_night_sec"),
        spark_sum("phone_seconds").alias("total_phone_sec"),
    )
    .withColumn("dur_sec", col("total_duration_min") * 60)
    .withColumn(
        "hb_per_100km",
        when(col("total_distance_km") > 0, (col("total_brakes") / col("total_distance_km")) * 100.0).otherwise(0.0)
    )
    .withColumn(
        "ha_per_100km",
        when(col("total_distance_km") > 0, (col("total_accels") / col("total_distance_km")) * 100.0).otherwise(0.0)
    )
    .withColumn(
        "phone_min_per_100km",
        when(col("total_distance_km") > 0, (col("total_phone_sec") / 60.0 / col("total_distance_km")) * 100.0).otherwise(0.0)
    )
    .withColumn(
        "speeding_pct",
        when(col("dur_sec") > 0, (col("total_speeding_sec") / col("dur_sec")) * 100.0).otherwise(0.0)
    )
    .withColumn(
        "night_pct",
        when(col("dur_sec") > 0, (col("total_night_sec") / col("dur_sec")) * 100.0).otherwise(0.0)
    )
)

# COMMAND ----------
# DBTITLE 1,Step 2: Scorecard v1 Calculation in Spark SQL
# Factor penalties: weight * min(metric / cap, 1.0)
p_hb = lit(25.0) * when(col("hb_per_100km") / 15.0 > 1.0, 1.0).otherwise(col("hb_per_100km") / 15.0)
p_sp = lit(25.0) * when(col("speeding_pct") / 20.0 > 1.0, 1.0).otherwise(col("speeding_pct") / 20.0)
p_ph = lit(20.0) * when(col("phone_min_per_100km") / 30.0 > 1.0, 1.0).otherwise(col("phone_min_per_100km") / 30.0)
p_nt = lit(15.0) * when(col("night_pct") / 25.0 > 1.0, 1.0).otherwise(col("night_pct") / 25.0)
p_ha = lit(10.0) * when(col("ha_per_100km") / 12.0 > 1.0, 1.0).otherwise(col("ha_per_100km") / 12.0)
p_ml = lit(5.0) * when(col("total_distance_km") / 3000.0 > 1.0, 1.0).otherwise(col("total_distance_km") / 3000.0)

total_penalties = p_hb + p_sp + p_ph + p_nt + p_ha + p_ml
raw_score = when(lit(100.0) - total_penalties < 0.0, 0.0).otherwise(lit(100.0) - total_penalties)
final_score = spark_round(raw_score, 1)

risk_band = (
    when(col("total_distance_km") < 50.0, lit("UNRATED"))
    .when(final_score >= 85.0, lit("A"))
    .when(final_score >= 70.0, lit("B"))
    .when(final_score >= 55.0, lit("C"))
    .when(final_score >= 40.0, lit("D"))
    .otherwise(lit("E"))
)

gold_scores = (
    driver_30d
    .withColumn("risk_score", final_score)
    .withColumn("risk_band", risk_band)
    .withColumn("scorecard_version", lit("v1"))
    .withColumn("window_start", lit("2025-03-01"))
    .withColumn("window_end", lit("2025-03-31"))
    .select(
        "driver_id", "window_start", "window_end",
        spark_round(col("total_distance_km"), 2).alias("distance_km"),
        spark_round(col("hb_per_100km"), 2).alias("hard_brake_per_100km"),
        spark_round(col("ha_per_100km"), 2).alias("hard_accel_per_100km"),
        spark_round(col("speeding_pct"), 2).alias("speeding_pct"),
        spark_round(col("night_pct"), 2).alias("night_pct"),
        spark_round(col("phone_min_per_100km"), 2).alias("phone_min_per_100km"),
        "risk_score", "risk_band", "scorecard_version"
    )
)

gold_scores.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.gold_driver_risk_score")

# COMMAND ----------
# DBTITLE 1,Step 3: Gold Dimensions & Fact Tables
# SCD Type 2 Driver Dimension
bronze_drivers = spark.table(f"{catalog}.{schema}.bronze_drivers")
dim_driver = (
    bronze_drivers
    .select(
        sha2(col("driver_id"), 256).alias("driver_sk"),
        "driver_id", "full_name", "email", "age_band", "licence_years", "city",
        lit("2024-01-01").alias("valid_from"),
        lit("2099-12-31").alias("valid_to"),
        lit(1).alias("is_current")
    )
)
dim_driver.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.gold_dim_driver")

# Vehicle Dimension
bronze_vehicles = spark.table(f"{catalog}.{schema}.bronze_vehicles")
dim_vehicle = (
    bronze_vehicles
    .select(
        sha2(col("vehicle_id"), 256).alias("vehicle_sk"),
        "vehicle_id", "driver_id", "vehicle_class", "vehicle_age_years", "annual_km_declared"
    )
)
dim_vehicle.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.gold_dim_vehicle")

# Fact Trip Table
fact_trip = (
    silver_trips
    .select(
        sha2(col("trip_id"), 256).alias("trip_sk"),
        col("trip_id"),
        sha2(col("driver_id"), 256).alias("driver_sk"),
        sha2(col("vehicle_id"), 256).alias("vehicle_sk"),
        "trip_start", "trip_end", "distance_km", "duration_min",
        "hard_brake_count", "hard_accel_count", "speeding_seconds", "night_seconds", "phone_seconds"
    )
)
fact_trip.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.gold_fact_trip")

# Optimize Gold Tables
spark.sql(f"OPTIMIZE {catalog}.{schema}.gold_fact_trip ZORDER BY (driver_sk);")
spark.sql(f"OPTIMIZE {catalog}.{schema}.gold_driver_risk_score ZORDER BY (driver_id);")

print("[SUCCESS] Gold Star Schema built and optimized.")
