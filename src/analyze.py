"""Compute headline findings and export static Plotly charts from the processed Parquet tables."""
from pathlib import Path
import json

import duckdb
import plotly.express as px
import plotly.graph_objects as go
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
PROC, IMG = ROOT / "data" / "processed", ROOT / "images"
SEG_ORDER = ["Inside zone", "Into / out of zone", "Outside zone"]
COLORS = {"Inside zone": "#d62728", "Into / out of zone": "#ff7f0e", "Outside zone": "#1f77b4",
          "2024": "#9e9e9e", "2025": "#1f77b4", "2026": "#d62728"}
LAUNCH = "2025-01-05"
TEMPLATE = "plotly_white"


def read(name: str) -> pl.DataFrame:
    return pl.read_parquet(PROC / f"{name}.parquet")


def pct(new: float, old: float) -> float:
    return round((new / old - 1) * 100, 1)


def save(fig: go.Figure, name: str) -> None:
    fig.update_layout(template=TEMPLATE, font=dict(size=14), margin=dict(l=60, r=30, t=90, b=60))
    fig.write_image(IMG / name, width=1200, height=675, scale=2)
    print("chart", name)


def main() -> None:
    IMG.mkdir(exist_ok=True)
    zones, daily, monthly = read("zones"), read("daily"), read("monthly")
    hourly, zone_m, summary = read("speed_hourly"), read("zone_monthly"), read("period_summary")
    months_n = int(summary["months_included"][0])
    years = sorted(summary["yr"].unique().to_list())
    window = f"Jan–{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][months_n - 1]}"

    # --- Trips, same months each year
    trips = summary.group_by("yr", "segment").agg(pl.col("trips").sum()).sort("yr", "segment")
    tot = trips.group_by("yr").agg(pl.col("trips").sum()).sort("yr")
    t = dict(zip(tot["yr"], tot["trips"]))
    seg_trips = {f"{r['segment']}|{r['yr']}": r["trips"] for r in trips.iter_rows(named=True)}

    # --- Weekday speed: inside zone vs outside zone (difference-in-differences style)
    wk = summary.filter(pl.col("day_type") == "Weekday")
    mph = {f"{r['segment']}|{r['yr']}": round(r["median_mph"], 2) for r in wk.iter_rows(named=True)}
    mins = {f"{r['segment']}|{r['yr']}": round(r["median_minutes"], 1) for r in wk.iter_rows(named=True)}
    fare = {f"{r['segment']}|{r['yr']}": round(r["avg_total"], 2) for r in wk.iter_rows(named=True)}

    # Peak hours (fee peak period 5am–9pm weekdays), trip-weighted average of monthly hourly medians
    peak = (hourly.filter((pl.col("mon") <= months_n) & (pl.col("day_type") == "Weekday")
                          & pl.col("hour").is_between(7, 19))
            .group_by("yr", "segment")
            .agg(((pl.col("median_mph") * pl.col("trips")).sum() / pl.col("trips").sum()).alias("mph")))
    peak_mph = {f"{r['segment']}|{r['yr']}": round(r["mph"], 2) for r in peak.iter_rows(named=True)}

    # --- CBD fees collected on yellow taxi trips
    fees_year = (daily.with_columns(pl.col("date").dt.year().alias("yr"))
                 .group_by("yr").agg(pl.col("cbd_fees").sum(), pl.col("date").max().alias("through")).sort("yr"))

    # --- Zone growth, first full year of pricing vs year before (same months)
    zg = (zone_m.with_columns(pl.col("month").dt.year().alias("yr"), pl.col("month").dt.month().alias("mon"))
          .filter(pl.col("mon") <= months_n)
          .group_by("LocationID", "yr").agg(pl.col("trips").sum())
          .pivot(on="yr", index="LocationID", values="trips")
          .join(zones.select("LocationID", "Borough", "Zone", "in_cbd"), on="LocationID"))
    zg = zg.with_columns(((pl.col("2025") / pl.col("2024") - 1) * 100).alias("growth_25_vs_24"),
                         ((pl.col("2026") / pl.col("2024") - 1) * 100).alias("growth_26_vs_24"))
    big = zg.filter(pl.col("2024") >= 20_000)
    cbd_growth = zg.filter(pl.col("in_cbd")).select(pl.col("2024").sum(), pl.col("2025").sum(), pl.col("2026").sum()).row(0)

    boro = (zone_m.with_columns(pl.col("month").dt.year().alias("yr"), pl.col("month").dt.month().alias("mon"))
            .filter(pl.col("mon") <= months_n).join(zones.select("LocationID", "Borough"), on="LocationID")
            .filter(pl.col("Borough").is_in(["Manhattan", "Queens", "Brooklyn", "Bronx"]))
            .group_by("Borough", "yr").agg(pl.col("trips").sum()).sort("Borough", "yr"))
    boro_d = {f"{r['Borough']}|{r['yr']}": int(r["trips"]) for r in boro.iter_rows(named=True)}

    raw_counts = dict(l.split("=") for l in (PROC / "row_counts.txt").read_text().split())
    findings = {
        "data": {"raw_rows": int(raw_counts["raw_rows"]), "clean_rows": int(raw_counts["clean_rows"]),
                 "first_month": str(monthly["month"].min()), "last_month": str(monthly["month"].max()),
                 "cbd_zones": zones.filter(pl.col("in_cbd")).height,
                 "comparison_window": window, "years": years},
        "trips_window": {str(y): int(t[y]) for y in years},
        "trips_change_pct": {"2025_vs_2024": pct(t[2025], t[2024]), "2026_vs_2025": pct(t[2026], t[2025]),
                             "2026_vs_2024": pct(t[2026], t[2024])},
        "trips_by_segment_window": seg_trips,
        "segment_change_2025_vs_2024_pct": {s: pct(seg_trips[f"{s}|2025"], seg_trips[f"{s}|2024"]) for s in SEG_ORDER},
        "cbd_pickups_window": dict(zip(["2024", "2025", "2026"], map(int, cbd_growth))),
        "weekday_median_mph": mph,
        "weekday_median_minutes": mins,
        "weekday_peak_7_19_mph": peak_mph,
        "weekday_avg_total_usd": fare,
        "speed_change_pct": {s: {"2025_vs_2024": pct(mph[f"{s}|2025"], mph[f"{s}|2024"]),
                                 "2026_vs_2024": pct(mph[f"{s}|2026"], mph[f"{s}|2024"])} for s in SEG_ORDER},
        "inside_minus_outside_speed_change_pp": {
            "2025_vs_2024": round(pct(mph["Inside zone|2025"], mph["Inside zone|2024"]) - pct(mph["Outside zone|2025"], mph["Outside zone|2024"]), 1),
            "2026_vs_2024": round(pct(mph["Inside zone|2026"], mph["Inside zone|2024"]) - pct(mph["Outside zone|2026"], mph["Outside zone|2024"]), 1)},
        "pickups_by_borough_window": boro_d,
        "cbd_fees_usd": {str(r["yr"]): {"total": round(r["cbd_fees"]), "through": str(r["through"])}
                         for r in fees_year.iter_rows(named=True) if r["cbd_fees"] > 0},
        "top_growth_zones_2025_vs_2024": big.sort("growth_25_vs_24", descending=True).head(5)
            .select("Zone", "Borough", pl.col("growth_25_vs_24").round(1)).to_dicts(),
        "bottom_growth_zones_2025_vs_2024": big.sort("growth_25_vs_24").head(5)
            .select("Zone", "Borough", pl.col("growth_25_vs_24").round(1)).to_dicts(),
    }
    (ROOT / "findings.json").write_text(json.dumps(findings, indent=2))
    print(json.dumps(findings, indent=2))

    # 1. Daily trips, 7-day rolling, by segment
    d = (daily.sort("date").group_by_dynamic("date", every="1d", group_by="segment").agg(pl.col("trips").sum())
         .sort("segment", "date").with_columns(pl.col("trips").rolling_mean(7).over("segment").alias("trips_7d")))
    fig = px.line(d.to_pandas(), x="date", y="trips_7d", color="segment", color_discrete_map=COLORS,
                  category_orders={"segment": SEG_ORDER},
                  labels={"trips_7d": "Trips per day (7-day avg)", "date": "", "segment": ""},
                  title="NYC yellow taxi trips per day, by relation to the Congestion Relief Zone")
    fig.add_vline(x=LAUNCH, line_dash="dash", line_color="black")
    fig.add_annotation(x=LAUNCH, y=1.02, yref="paper", text="Congestion pricing starts (5 Jan 2025)", showarrow=False, xanchor="left")
    fig.update_layout(legend=dict(orientation="h", y=-0.12))
    save(fig, "01_daily_trips.png")

    # 2. Weekday hourly speed inside the zone
    h = (hourly.filter((pl.col("mon") <= months_n) & (pl.col("day_type") == "Weekday") & (pl.col("segment") == "Inside zone"))
         .group_by("yr", "hour").agg(((pl.col("median_mph") * pl.col("trips")).sum() / pl.col("trips").sum()).alias("mph"))
         .sort("yr", "hour").with_columns(pl.col("yr").cast(pl.Utf8)))
    fig = px.line(h.to_pandas(), x="hour", y="mph", color="yr", color_discrete_map=COLORS, markers=True,
                  labels={"hour": "Pickup hour", "mph": "Median trip speed (mph)", "yr": ""},
                  title=f"Weekday taxi speed for trips inside the zone, {window} each year")
    fig.add_vrect(x0=5, x1=21, fillcolor="grey", opacity=0.08, line_width=0, annotation_text="peak toll hours", annotation_position="top left")
    save(fig, "02_hourly_speed_inside_zone.png")

    # 3. Speed change vs 2024, inside vs outside, monthly
    m = (monthly.with_columns(pl.col("month").dt.year().alias("yr"), pl.col("month").dt.month().alias("mon"))
         .filter(pl.col("segment").is_in(["Inside zone", "Outside zone"])))
    base = m.filter(pl.col("yr") == 2024).select("mon", "segment", pl.col("median_mph").alias("base"))
    m = (m.filter(pl.col("yr") > 2024).join(base, on=["mon", "segment"])
         .with_columns(((pl.col("median_mph") / pl.col("base") - 1) * 100).alias("chg")).sort("month"))
    fig = px.bar(m.to_pandas(), x="month", y="chg", color="segment", barmode="group", color_discrete_map=COLORS,
                 labels={"chg": "Median speed vs same month 2024 (%)", "month": "", "segment": ""},
                 title="Did taxis inside the zone speed up more than taxis elsewhere?")
    fig.add_hline(y=0, line_color="black")
    fig.update_layout(legend=dict(orientation="h", y=-0.12))
    save(fig, "03_speed_change_vs_2024.png")

    # 4. Map: pickup growth by Manhattan zone, CBD outlined
    geo = json.loads((PROC / "taxi_zones.geojson").read_text())
    man_ids = set(zones.filter(pl.col("Borough") == "Manhattan")["LocationID"].to_list())
    cbd_ids = set(zones.filter(pl.col("in_cbd"))["LocationID"].to_list())
    geo_man = {"type": "FeatureCollection", "features": [f for f in geo["features"] if f["id"] in man_ids]}
    mp = zg.filter((pl.col("Borough") == "Manhattan") & (pl.col("2024") >= 1_000)).with_columns(
        pl.col("growth_25_vs_24").clip(-40, 40).alias("growth_clipped"))
    fig = px.choropleth(mp.to_pandas(), geojson=geo_man, locations="LocationID", color="growth_clipped",
                        color_continuous_scale="RdBu_r", range_color=(-40, 40), hover_name="Zone",
                        hover_data={"growth_25_vs_24": ":.1f", "growth_clipped": False},
                        labels={"growth_clipped": "% change"},
                        title=f"Manhattan taxi pickups, {window} 2025 vs 2024 (black outline = toll zone)")
    cbd_geo = {"type": "FeatureCollection", "features": [f for f in geo_man["features"] if f["id"] in cbd_ids]}
    fig.add_trace(go.Choropleth(geojson=cbd_geo, locations=sorted(cbd_ids), z=[0] * len(cbd_ids),
                                colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
                                marker_line_color="black", marker_line_width=1.6, hoverinfo="skip"))
    fig.update_geos(visible=False, projection_type="mercator",
                    lonaxis_range=[-74.03, -73.90], lataxis_range=[40.70, 40.88])
    fig.update_layout(template=TEMPLATE, font=dict(size=14), margin=dict(l=20, r=20, t=80, b=20))
    fig.write_image(IMG / "04_manhattan_zone_map.png", width=900, height=1000, scale=2)
    print("chart 04_manhattan_zone_map.png")

    # 5. Pickups by borough (shows the outer-borough surge that muddies the "outside" comparison)
    fig = px.bar(boro.with_columns(pl.col("yr").cast(pl.Utf8)).to_pandas(), x="Borough", y="trips", color="yr",
                 barmode="group", color_discrete_map=COLORS, text_auto=".3s",
                 labels={"trips": f"Yellow taxi pickups, {window}", "Borough": "", "yr": ""},
                 title="Pickups by borough: Brooklyn and the Bronx roughly tripled in 2025", log_y=True)
    save(fig, "05_pickups_by_borough.png")

    # 6. Monthly CBD fees from yellow taxis
    f = monthly.group_by("month").agg(pl.col("cbd_fees").sum()).filter(pl.col("cbd_fees") > 0).sort("month")
    fig = px.bar(f.to_pandas(), x="month", y="cbd_fees", labels={"cbd_fees": "CBD fees on yellow taxi trips (USD)", "month": ""},
                 title="Congestion fees charged on yellow taxi trips per month ($0.75 per trip)",
                 color_discrete_sequence=["#d62728"])
    save(fig, "06_monthly_cbd_fees.png")


if __name__ == "__main__":
    main()
