import io
import json
import os
from datetime import datetime, timedelta, timezone

import requests

FARS_FILE = "fars.geojson"
OUTPUT_DIR = "data/fwi"

WMS_URL = "https://maps.effis.emergency.copernicus.eu/effis"

LAYER = "ecmwf007.fwi"

# محدوده تقریبی استان فارس
BBOX = "50.0,27.0,54.5,31.5"

# اندازه تصویر خروجی
WIDTH = 1200
HEIGHT = 900

# تعداد روزهای پیش بینی
FORECAST_DAYS = 9


def load_fars_boundary():
    with open(FARS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def download_fwi(date_str, output_file):
    params = {
        "LAYERS": LAYER,
        "FORMAT": "image/tiff",
        "TRANSPARENT": "true",
        "SINGLETILE": "false",
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": BBOX,
        "WIDTH": WIDTH,
        "HEIGHT": HEIGHT,
        "TIME": date_str,
    }

    print(f"Downloading FWI for {date_str}")

    response = requests.get(
        WMS_URL,
        params=params,
        timeout=120,
    )

    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")

    if len(response.content) < 1000:
        raise RuntimeError(
            f"Downloaded file is unexpectedly small for {date_str}"
        )

    if "xml" in content_type.lower() or response.content[:50].startswith(b"<?xml"):
        raise RuntimeError(
            f"Server returned XML instead of GeoTIFF for {date_str}."
        )

    with open(output_file, "wb") as f:
        f.write(response.content)

    print(f"Saved: {output_file}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # بررسی وجود Boundary
    if not os.path.exists(FARS_FILE):
        raise FileNotFoundError(
            f"Boundary file not found: {FARS_FILE}"
        )

    # فقط برای اطمینان از سالم بودن GeoJSON
    fars = load_fars_boundary()

    if "features" not in fars:
        raise ValueError("fars.geojson is not a valid FeatureCollection.")

    today = datetime.now(timezone.utc).date()

    metadata = {
        "source": "Copernicus EFFIS / GWIS",
        "layer": LAYER,
        "model": "ECMWF",
        "forecast_days": FORECAST_DAYS,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "boundary": "fars.geojson",
        "files": [],
    }

    for i in range(FORECAST_DAYS):
        forecast_date = today + timedelta(days=i)
        date_str = forecast_date.isoformat()

        output_file = os.path.join(
            OUTPUT_DIR,
            f"fwi_{date_str}.tif",
        )

        try:
            download_fwi(date_str, output_file)

            metadata["files"].append(
                {
                    "date": date_str,
                    "file": f"fwi_{date_str}.tif",
                    "day_ahead": i,
                }
            )

        except Exception as e:
            print(f"WARNING: failed for {date_str}: {e}")

    metadata_file = os.path.join(
        OUTPUT_DIR,
        "metadata.json",
    )

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(
            metadata,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("")
    print("FWI update completed.")
    print(f"Files created: {len(metadata['files'])}")


if __name__ == "__main__":
    main()
