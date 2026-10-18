"""Streamlit dashboard: did NYC congestion pricing change yellow-taxi traffic?

All numbers come from the small Parquet tables in data/processed (built by src/prepare.py from
~120M TLC trip records). Queries run in DuckDB; reshaping in Polars; charts in Plotly.
"""
from pathlib import Path
import json

import duckdb
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st

PROC = Path(__file__).parent / "data" / "processed"
SEGMENTS = ["Inside zone", "Into / out of zone", "Outside zone"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
YEAR_COLORS = {"2024": "#9e9e9e", "2025": "#1f77b4", "2026": "#d62728"}
SEG_COLORS = {"Inside zone": "#d62728", "Into / out of zone": "#ff7f0e", "Outside zone": "#1f77b4"}

st.set_page_config(page_title="NYC Congestion Pricing × Taxi Data", page_icon="🚕", layout="wide")


@st.cache_resource
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    for name in ["daily", "monthly", "speed_hourly", "zone_monthly", "zones"]:
        c.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{PROC / (name + '.parquet')}')")
    return c


def q(sql: str, params: list | None = None) -> pl.DataFrame:
    return pl.from_arrow(con().execute(sql, params or []).arrow())


@st.cache_data
def geojson() -> dict:
    return json.loads((PROC / "taxi_zones.geojson").read_text())


years = q("SELECT DISTINCT year(month) AS y FROM monthly ORDER BY 1")["y"].to_list()
last_year = years[-1]
last_month_avail = q(f"SELECT max(month(month)) AS m FROM monthly WHERE year(month) = {last_year}")["m"][0]

# ---------------- Sidebar
st.sidebar.header("Filters")
base_year = st.sidebar.selectbox("Baseline year (before pricing)", years, index=0)
cmp_year = st.sidebar.selectbox("Comparison year", years, index=years.index(2025) if 2025 in years else len(years) - 1)
m_from, m_to = st.sidebar.select_slider("Months compared (same months in both years)", options=list(range(1, 13)),
                                        value=(1, int(last_month_avail)), format_func=lambda m: MONTHS[m - 1])
day_type = st.sidebar.radio("Days", ["Weekday", "Weekend", "All"], horizontal=True)
st.sidebar.caption(f"Data: NYC TLC yellow taxi trips, Jan {years[0]} to {MONTHS[last_month_avail - 1]} {last_year}. "
                   "Toll started 5 Jan 2025.")
if cmp_year == last_year and m_to > last_month_avail:
    st.sidebar.warning(f"{last_year} only has data through {MONTHS[last_month_avail - 1]}.")
day_filter = "" if day_type == "All" else f"AND day_type = '{day_type}'"

# ---------------- Header + KPIs
st.title("🚕 Did NYC's congestion pricing change taxi traffic?")
st.markdown("Manhattan's Congestion Relief Zone (below 60th St) started charging on **5 January 2025**. "
            "This dashboard compares ~110M cleaned yellow-taxi trips **inside**, **into/out of**, and **outside** "
            "the zone, matching the same months across years.")

seg = q(f"""SELECT yr, segment, sum(trips) AS trips,
                   sum(median_mph * trips) / sum(trips) AS mph
            FROM speed_hourly WHERE yr IN ({base_year}, {cmp_year}) AND mon BETWEEN {m_from} AND {m_to} {day_filter}
            GROUP BY ALL""")
fare = q(f"""SELECT year(month) AS yr, segment, sum(avg_total * trips) / sum(trips) AS avg_total, sum(cbd_fees) AS fees
             FROM monthly WHERE year(month) IN ({base_year}, {cmp_year}) AND month(month) BETWEEN {m_from} AND {m_to}
             GROUP BY ALL""")


def val(df: pl.DataFrame, col: str, yr: int, segment: str | None = None) -> float:
    f = df.filter(pl.col("yr") == yr)
    if segment:
        f = f.filter(pl.col("segment") == segment)
        return float(f[col][0]) if f.height else float("nan")
    return float(f[col].sum())


def delta(a: float, b: float) -> str:
    return f"{(b / a - 1) * 100:+.1f}% vs {base_year}" if a else "n/a"


k = st.columns(4)
k[0].metric(f"Taxi trips {cmp_year}", f"{val(seg, 'trips', cmp_year) / 1e6:.1f}M",
            delta(val(seg, "trips", base_year), val(seg, "trips", cmp_year)))
k[1].metric("Speed inside zone", f"{val(seg, 'mph', cmp_year, 'Inside zone'):.2f} mph",
            delta(val(seg, "mph", base_year, "Inside zone"), val(seg, "mph", cmp_year, "Inside zone")))
k[2].metric("Speed outside zone", f"{val(seg, 'mph', cmp_year, 'Outside zone'):.2f} mph",
            delta(val(seg, "mph", base_year, "Outside zone"), val(seg, "mph", cmp_year, "Outside zone")))
k[3].metric(f"CBD fees on taxi trips {cmp_year}", f"${val(fare, 'fees', cmp_year) / 1e6:.1f}M")
st.caption("Speed is the trip-weighted average of hourly median trip speeds (distance ÷ meter time). "
           f"Day filter: {day_type} (applies to trip counts and speeds).")

tabs = st.tabs(["📈 Trips over time", "⏱️ Speed by hour", "🗺️ Zone map", "💵 Fares & fees", "🧾 Data & method"])

# ---------------- Trips over time
with tabs[0]:
    c1, c2 = st.columns([3, 1])
    window = c2.slider("Rolling average (days)", 1, 28, 7)
    segs = c2.multiselect("Segments", SEGMENTS, default=SEGMENTS)
    d = q("SELECT date, segment, sum(trips) AS trips FROM daily GROUP BY ALL ORDER BY date")
    d = d.filter(pl.col("segment").is_in(segs)).sort("segment", "date").with_columns(
        pl.col("trips").rolling_mean(window).over("segment").alias("trips_avg"))
    fig = px.line(d.to_pandas(), x="date", y="trips_avg", color="segment", color_discrete_map=SEG_COLORS,
                  labels={"trips_avg": f"Trips per day ({window}-day avg)", "date": "", "segment": ""})
    fig.add_vline(x="2025-01-05", line_dash="dash", line_color="black")
    fig.add_annotation(x="2025-01-05", y=1.03, yref="paper", text="Toll starts", showarrow=False)
    c1.plotly_chart(fig, width="stretch")
    t = seg.group_by("yr", "segment").agg(pl.col("trips").sum()).pivot(on="yr", index="segment", values="trips")
    if str(base_year) in t.columns and str(cmp_year) in t.columns and base_year != cmp_year:
        t = t.with_columns(((pl.col(str(cmp_year)) / pl.col(str(base_year)) - 1) * 100).round(1).alias("change %"))
    c2.dataframe(t, hide_index=True)

# ---------------- Speed by hour
with tabs[1]:
    segment = st.radio("Trip segment", SEGMENTS, horizontal=True)
    h = q(f"""SELECT yr::VARCHAR AS year, hour, sum(median_mph * trips) / sum(trips) AS mph, sum(trips) AS trips
              FROM speed_hourly WHERE segment = ? AND mon BETWEEN {m_from} AND {m_to} {day_filter}
              GROUP BY ALL ORDER BY year, hour""", [segment])
    fig = px.line(h.to_pandas(), x="hour", y="mph", color="year", markers=True, color_discrete_map=YEAR_COLORS,
                  labels={"hour": "Pickup hour", "mph": "Median trip speed (mph)"})
    fig.add_vrect(x0=5, x1=21, fillcolor="grey", opacity=0.08, line_width=0,
                  annotation_text="weekday peak toll hours", annotation_position="top left")
    st.plotly_chart(fig, width="stretch")
    m = q(f"""SELECT month, segment, median_mph FROM monthly WHERE segment IN ('Inside zone', 'Outside zone')""")
    m = m.with_columns(pl.col("month").dt.year().alias("yr"), pl.col("month").dt.month().alias("mon"))
    b = m.filter(pl.col("yr") == base_year).select("mon", "segment", pl.col("median_mph").alias("base"))
    m = m.filter(pl.col("yr") > base_year).join(b, on=["mon", "segment"]).with_columns(
        ((pl.col("median_mph") / pl.col("base") - 1) * 100).alias("chg")).sort("month")
    fig = px.bar(m.to_pandas(), x="month", y="chg", color="segment", barmode="group", color_discrete_map=SEG_COLORS,
                 labels={"chg": f"Median speed vs same month {base_year} (%)", "month": "", "segment": ""},
                 title="Inside vs outside the zone: if the toll sped up traffic, red bars should beat blue")
    fig.add_hline(y=0, line_color="black")
    st.plotly_chart(fig, width="stretch")

# ---------------- Map
with tabs[2]:
    c1, c2 = st.columns([1, 3])
    metric = c1.radio("Metric", ["Pickups % change", "Median speed % change"])
    area = c1.radio("Area", ["Manhattan", "All NYC"])
    min_trips = c1.number_input(f"Min pickups in {base_year}", 0, 100_000, 1_000, step=500)
    z = q(f"""SELECT LocationID, year(month) AS yr, sum(trips) AS trips,
                     sum(median_mph * trips) / sum(trips) AS mph
              FROM zone_monthly WHERE year(month) IN ({base_year}, {cmp_year})
                AND month(month) BETWEEN {m_from} AND {m_to} GROUP BY ALL""")
    zb = z.filter(pl.col("yr") == base_year).select("LocationID", pl.col("trips").alias("t0"), pl.col("mph").alias("s0"))
    zc = z.filter(pl.col("yr") == cmp_year).select("LocationID", pl.col("trips").alias("t1"), pl.col("mph").alias("s1"))
    zz = (zb.join(zc, on="LocationID").join(q("SELECT * FROM zones"), on="LocationID")
          .filter(pl.col("t0") >= min_trips)
          .with_columns(((pl.col("t1") / pl.col("t0") - 1) * 100).alias("Pickups % change"),
                        ((pl.col("s1") / pl.col("s0") - 1) * 100).alias("Median speed % change")))
    if area == "Manhattan":
        zz = zz.filter(pl.col("Borough") == "Manhattan")
    lim = 40 if metric.startswith("Pickups") else 10
    fig = px.choropleth(zz.to_pandas(), geojson=geojson(), locations="LocationID", color=metric,
                        color_continuous_scale="RdBu_r", range_color=(-lim, lim), hover_name="Zone",
                        hover_data={"Borough": True, "in_cbd": True, "t0": ":,", "t1": ":,", "LocationID": False})
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    fig.update_layout(height=700, margin=dict(l=0, r=0, t=10, b=0))
    c2.plotly_chart(fig, width="stretch")
    c1.caption(f"{cmp_year} vs {base_year}, {MONTHS[m_from - 1]}–{MONTHS[m_to - 1]}. Colour clipped at ±{lim}%. "
               "Zones are by pickup location; `in_cbd` marks toll-zone zones.")

# ---------------- Fares & fees
with tabs[3]:
    f = q("""SELECT month, segment, avg_total, cbd_fees, fee_share FROM monthly ORDER BY month""")
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.line(f.to_pandas(), x="month", y="avg_total", color="segment", color_discrete_map=SEG_COLORS,
                            labels={"avg_total": "Average total paid per trip (USD)", "month": "", "segment": ""},
                            title="Average rider total per trip"), width="stretch")
    ff = f.group_by("month").agg(pl.col("cbd_fees").sum()).filter(pl.col("cbd_fees") > 0).sort("month")
    c2.plotly_chart(px.bar(ff.to_pandas(), x="month", y="cbd_fees", color_discrete_sequence=["#d62728"],
                           labels={"cbd_fees": "CBD fees (USD)", "month": ""},
                           title="Congestion fees charged on yellow taxi trips"), width="stretch")
    st.caption("Taxi riders pay $0.75 per trip that starts, ends or passes through the zone; private cars pay a "
               "daily toll that is not in this dataset.")

# ---------------- Data & method
with tabs[4]:
    st.markdown("""
**Source:** [NYC Taxi & Limousine Commission – TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
(yellow taxi Parquet files + taxi zone lookup/shapefile).

**Pipeline:** `src/download.py` → `src/prepare.py` (DuckDB streams ~120M rows, cleans, aggregates to small Parquet)
→ `src/geo.py` (zone GeoJSON) → `src/analyze.py` (Polars + Plotly, `findings.json`) → this app.

**Toll zone in taxi-zone terms:** a zone counts as inside if more than half of its *same-zone* trips since
5 Jan 2025 paid the CBD fee (38 Manhattan zones). Zones straddling 60th St are classified as outside.

**Cleaning:** 1–180 min, 0.1–60 mi, 1–70 mph, non-negative fare, known zones, pickup in the file's month.
""")
    zt = q("SELECT LocationID, Borough, Zone, in_cbd, round(fee_share, 3) AS fee_share, intra_zone_trips_2025_plus FROM zones WHERE Borough = 'Manhattan' ORDER BY in_cbd DESC, Zone")
    st.dataframe(zt, hide_index=True, width="stretch")
    st.download_button("Download monthly table (CSV)", q("SELECT * FROM monthly").write_csv(), "monthly.csv", "text/csv")
