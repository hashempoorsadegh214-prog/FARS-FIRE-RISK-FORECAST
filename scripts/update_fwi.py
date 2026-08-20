import json
import os
from datetime import datetime, timedelta, timezone

import requests


# -----------------------------
# تنظیمات
# -----------------------------

FARS_FILE = "fars.geojson"
OUTPUT_DIR = "data/fwi"

WMS_URL = "https://maps.effis.emergency.copernicus.eu/effis"
LAYER = "ecmwf007.fwi"

# محدوده تقریبی استان فارس
BBOX = "50.0,27.0,54.5,31.5"

WIDTH = 1200
HEIGHT = 900

FORECAST_DAYS = 9


# -----------------------------
# بررسی فایل مرز فارس
# -----------------------------

def check_fars_boundary():
    if not os.path.exists(FARS_FILE):
        raise FileNotFoundError(
            f"Boundary file not found: {FARS_FILE}"
        )

    with open(FARS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            "fars.geojson is not a valid GeoJSON FeatureCollection."
        )

    if "features" not in data or len(data["features"]) == 0:
        raise ValueError(
            "fars.geojson does not contain any features."
        )

    print("Fars boundary loaded successfully.")
    print(f"Features: {len(data['features'])}")


# -----------------------------
# دریافت FWI
# -----------------------------

def download_fwi(date_str, output_file):
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": LAYER,
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": BBOX,
        "WIDTH": WIDTH,
        "HEIGHT": HEIGHT,
        "FORMAT": "image/tiff",
        "TRANSPARENT": "true",
        "TIME": date_str,
    }

    print("")
    print("=" * 60)
    print(f"Downloading FWI for: {date_str}")
    print("=" * 60)

    response = requests.get(
        WMS_URL,
        params=params,
        timeout=180,
    )

    print(f"HTTP status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', '')}")
    print(f"File size: {len(response.content)} bytes")

    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type",
        ""
    ).lower()

    # اگر سرور XML یا متن خطا برگرداند
    first_bytes = response.content[:100].lower()

    if (
        "xml" in content_type
        or first_bytes.startswith(b"<?xml")
        or b"serviceexception" in first_bytes
    ):
        print("")
        print("Server response:")
        print(response.text[:3000])

        raise RuntimeError(
            f"EFFIS returned an XML/service error for {date_str}."
        )

    # فایل غیرعادی کوچک
    if len(response.content) < 1000:
        raise RuntimeError(
            f"Downloaded response is too small for {date_str}."
        )

    os.makedirs(
        os.path.dirname(output_file),
        exist_ok=True
    )

    with open(output_file, "wb") as f:
        f.write(response.content)

    print(f"Saved successfully: {output_file}")


# -----------------------------
# ساخت metadata
# -----------------------------

def create_metadata(files):
    return {
        "source": "Copernicus EFFIS / GWIS",
        "model": "ECMWF",
        "layer": LAYER,
        "forecast_days": FORECAST_DAYS,
        "boundary": FARS_FILE,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "files": files,
    }


# -----------------------------
# main
# -----------------------------

def main():

    print("")
    print("=" * 60)
    print("FWI ENGINE STARTED")
    print("=" * 60)

    # بررسی Boundary
    check_fars_boundary()

    # ساخت پوشه خروجی
    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    today = datetime.now(
        timezone.utc
    ).date()

    downloaded_files = []

    # دریافت 9 روز
    for day_ahead in range(FORECAST_DAYS):

        forecast_date = (
            today + timedelta(days=day_ahead)
        )

        date_str = forecast_date.isoformat()

        output_file = os.path.join(
            OUTPUT_DIR,
            f"fwi_{date_str}.tif"
        )

        try:

            download_fwi(
                date_str,
                output_file
            )

            downloaded_files.append({
                "date": date_str,
                "day_ahead": day_ahead,
                "file": f"fwi_{date_str}.tif",
            })

        except Exception as e:

            print("")
            print(
                f"ERROR: Failed to download FWI for {date_str}"
            )
            print(str(e))

            # بسیار مهم:
            # Workflow باید در صورت شکست قرمز شود.
            raise

    # metadata
    metadata = create_metadata(
        downloaded_files
    )

    metadata_file = os.path.join(
        OUTPUT_DIR,
        "metadata.json"
    )

    with open(
        metadata_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            metadata,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("")
    print("=" * 60)
    print("FWI UPDATE COMPLETED")
    print("=" * 60)
    print(
        f"Downloaded files: {len(downloaded_files)}"
    )
    print(
        f"Output directory: {OUTPUT_DIR}"
    )
    print(
        f"Metadata: {metadata_file}"
    )


if __name__ == "__main__":
    main()
