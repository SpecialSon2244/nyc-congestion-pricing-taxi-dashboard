-- Data-driven definition of the Congestion Relief Zone (Manhattan below 60th St) in taxi-zone terms.
-- A taxi trip that starts AND ends in the same zone pays the $0.75 CBD fee only if that zone is inside
-- the charging area, so the share of fee-paying intra-zone trips since 2025-01-05 classifies each zone.
SELECT
    l.LocationID,
    l.Borough,
    l.Zone,
    coalesce(s.intra_trips, 0)            AS intra_zone_trips_2025_plus,
    s.fee_share,
    coalesce(s.fee_share > 0.5 AND l.Borough = 'Manhattan', false) AS in_cbd
FROM read_csv('data/raw/taxi_zone_lookup.csv') l
LEFT JOIN (
    SELECT PULocationID AS LocationID,
           count(*) AS intra_trips,
           avg((cbd_congestion_fee > 0)::INT) AS fee_share
    FROM raw
    WHERE PULocationID = DOLocationID
      AND tpep_pickup_datetime >= TIMESTAMP '2025-01-05'
    GROUP BY 1
) s USING (LocationID)
ORDER BY l.LocationID;
