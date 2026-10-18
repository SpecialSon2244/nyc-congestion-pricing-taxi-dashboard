"""Aggregate ~100M raw TLC trip records into small, committed Parquet tables.

DuckDB streams the monthly Parquet files out-of-core; Polars handles the tidy zone table.
"""
from pathlib import Path
import duckdb
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
SQL = ROOT / "sql"

AGGREGATES = {
    "daily": """
        SELECT pickup_date AS date, segment, count(*) AS trips,
               sum(total_amount) AS revenue, sum(cbd_fee) AS cbd_fees
        FROM trips GROUP BY ALL ORDER BY ALL""",
    "monthly": """
        SELECT file_month AS month, segment, count(*) AS trips,
               avg(fare_amount) AS avg_fare, avg(total_amount) AS avg_total,
               avg(trip_distance) AS avg_miles, avg(minutes) AS avg_minutes,
               median(mph) AS median_mph, sum(cbd_fee) AS cbd_fees,
               avg((cbd_fee > 0)::INT) AS fee_share
        FROM trips GROUP BY ALL ORDER BY ALL""",
    "speed_hourly": """
        SELECT yr, mon, day_type, pickup_hour AS hour, segment,
               count(*) AS trips, median(mph) AS median_mph
        FROM trips GROUP BY ALL ORDER BY ALL""",
    "zone_monthly": """
        SELECT file_month AS month, PULocationID AS LocationID, count(*) AS trips,
               median(mph) AS median_mph
        FROM trips GROUP BY ALL ORDER BY ALL""",
    # Same calendar months in every year (latest year is partial), exact medians.
    "period_summary": """
        WITH last AS (SELECT max(mon) AS m FROM trips WHERE yr = (SELECT max(yr) FROM trips))
        SELECT yr, segment, day_type, count(*) AS trips,
               quantile_cont(mph, 0.25) AS p25_mph, median(mph) AS median_mph,
               quantile_cont(mph, 0.75) AS p75_mph,
               median(minutes) AS median_minutes, avg(total_amount) AS avg_total,
               sum(cbd_fee) AS cbd_fees, (SELECT m FROM last) AS months_included
        FROM trips WHERE mon <= (SELECT m FROM last)
        GROUP BY ALL ORDER BY ALL""",
}


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'; SET threads=4; SET preserve_insertion_order=false;")
    con.execute("""CREATE VIEW raw AS SELECT * FROM read_parquet('data/raw/yellow_tripdata_*.parquet',
                   filename=true, union_by_name=true)""")

    zones = pl.from_arrow(con.execute((SQL / "cbd_zones.sql").read_text()).arrow())
    zones.write_parquet(PROC / "zones.parquet")
    print("CBD zones:", zones.filter(pl.col("in_cbd")).height)
    con.register("zones", zones.to_arrow())

    con.execute((SQL / "clean_trips.sql").read_text())
    raw_n = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    for name, query in AGGREGATES.items():
        con.execute(f"COPY ({query}) TO '{PROC / (name + '.parquet')}' (FORMAT parquet)")
        print("wrote", name)
    clean_n = con.execute(f"SELECT sum(trips) FROM '{PROC / 'daily.parquet'}'").fetchone()[0]
    (PROC / "row_counts.txt").write_text(f"raw_rows={raw_n}\nclean_rows={clean_n}\n")
    print(f"raw rows {raw_n:,} -> clean {clean_n:,} ({clean_n / raw_n:.1%})")


if __name__ == "__main__":
    import os
    os.chdir(ROOT)
    main()
