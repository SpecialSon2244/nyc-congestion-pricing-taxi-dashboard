Did New York's congestion toll actually make Manhattan traffic faster? I checked 110 million yellow-taxi trips.

NYC started charging to drive into Manhattan below 60th St on 5 January 2025. Taxi records log distance and meter time, so every trip doubles as a speed sensor. I compared the same months (Jan–Aug) in 2024, 2025 and 2026.

What I found:
→ Taxi demand went up, not down: trips rose 12% in 2025, and 10% inside the toll zone.
→ Weekday taxi speeds inside the zone barely moved: 7.91 mph in 2024, 7.98 mph in 2025 (+0.9%), versus 0.0% outside the zone.
→ 2026 is slower everywhere: 7.47 mph inside the zone (−5.6% vs 2024).
→ The surprise: taxi pickups in Brooklyn and the Bronx roughly tripled in 2025, so "outside the zone" is not a clean comparison group.

Stack: DuckDB streaming ~120M Parquet rows in about a minute, Polars, Plotly, and a Streamlit dashboard where you can pick years, months and zones.

Biggest lesson: check your control group before you trust a before/after story.

Code and dashboard: https://github.com/SpecialSon2244/nyc-congestion-pricing-taxi-dashboard

What other data would you use to measure the toll's effect?

#DataAnalytics #DuckDB #Streamlit #NYC #OpenData
