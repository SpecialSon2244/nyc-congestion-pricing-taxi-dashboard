"""Convert the TLC taxi-zone shapefile (NY State Plane, feet) to a light WGS84 GeoJSON for maps."""
from pathlib import Path
import json
import zipfile

import shapefile  # pyshp
from pyproj import Transformer
import numpy as np
import shapely
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"


def main() -> None:
    zip_path = RAW / "taxi_zones.zip"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(RAW / "taxi_zones_shp")
    shp = next((RAW / "taxi_zones_shp").rglob("*.shp"))
    to_wgs84 = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True).transform
    features = []
    for rec in shapefile.Reader(str(shp)).shapeRecords():
        attrs = rec.record.as_dict()
        geom = shape(rec.shape.__geo_interface__).simplify(60, preserve_topology=True)  # 60 ft
        geom = shapely.transform(geom, lambda c: np.round(np.column_stack(to_wgs84(c[:, 0], c[:, 1])), 5))
        features.append({
            "type": "Feature",
            "id": int(attrs["LocationID"]),
            "properties": {"LocationID": int(attrs["LocationID"]), "zone": attrs["zone"], "borough": attrs["borough"]},
            "geometry": json.loads(json.dumps(mapping(geom), default=list)),
        })
    out = PROC / "taxi_zones.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print("wrote", out, f"{out.stat().st_size / 1e6:.2f} MB,", len(features), "zones")


if __name__ == "__main__":
    main()
