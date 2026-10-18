-- Cleaned trip-level view: one row per plausible yellow-taxi trip, tagged by CBD segment.
CREATE OR REPLACE VIEW trips AS
WITH t AS (
    SELECT
        r.*,
        strptime(regexp_extract(r.filename, '(\d{4}-\d{2})\.parquet', 1), '%Y-%m')::DATE AS file_month,
        date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0 AS minutes
    FROM raw r
)
SELECT
    file_month,
    year(file_month)  AS yr,
    month(file_month) AS mon,
    tpep_pickup_datetime::DATE AS pickup_date,
    hour(tpep_pickup_datetime)  AS pickup_hour,
    CASE WHEN isodow(tpep_pickup_datetime) <= 5 THEN 'Weekday' ELSE 'Weekend' END AS day_type,
    PULocationID, DOLocationID,
    CASE
        WHEN pu.in_cbd AND dz.in_cbd THEN 'Inside zone'
        WHEN pu.in_cbd OR  dz.in_cbd THEN 'Into / out of zone'
        ELSE 'Outside zone'
    END AS segment,
    trip_distance, minutes,
    trip_distance / (minutes / 60.0) AS mph,
    fare_amount, total_amount,
    coalesce(cbd_congestion_fee, 0) AS cbd_fee,
    request_source
FROM t
JOIN zones pu ON pu.LocationID = t.PULocationID
JOIN zones dz ON dz.LocationID = t.DOLocationID
WHERE date_trunc('month', tpep_pickup_datetime)::DATE = file_month   -- drop mis-dated records
  AND minutes BETWEEN 1 AND 180
  AND trip_distance BETWEEN 0.1 AND 60
  AND trip_distance / (minutes / 60.0) BETWEEN 1 AND 70
  AND fare_amount >= 0
  AND PULocationID NOT IN (264, 265) AND DOLocationID NOT IN (264, 265);  -- unknown zones
