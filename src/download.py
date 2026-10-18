"""Download NYC TLC yellow-taxi trip records (Parquet, 2024 onward) plus the taxi zone lookup and shapefile."""
from pathlib import Path
import time
import urllib.error
import urllib.request

BASE = "https://d37ci6vzurychx.cloudfront.net"
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
MONTHS = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13)]


def fetch(url: str, dest: Path, retries: int = 4) -> bool:
    """Return False only when the file is not published (HTTP 403/404)."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(dest)
            print("downloaded", dest.name)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                print("not published yet:", dest.name)
                return False
            print("retry", attempt, dest.name, exc)
        except Exception as exc:
            print("retry", attempt, dest.name, exc)
        tmp.unlink(missing_ok=True)
        time.sleep(3 * attempt)
    raise RuntimeError(f"failed to download {url}")


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    fetch(f"{BASE}/misc/taxi_zone_lookup.csv", RAW / "taxi_zone_lookup.csv")
    fetch(f"{BASE}/misc/taxi_zones.zip", RAW / "taxi_zones.zip")
    for m in MONTHS:
        if not fetch(f"{BASE}/trip-data/yellow_tripdata_{m}.parquet", RAW / f"yellow_tripdata_{m}.parquet"):
            break
