import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests


# ============================================================
# تنظیمات اصلی
# ============================================================

FARS_FILE = "fars.geojson"
OUTPUT_DIR = "data/fwi"

WMS_URL = "https://maps.effis.emergency.copernicus.eu/effis"
LAYER = "ecmwf007.fwi"

# محدوده پوشاننده استان فارس
BBOX = "50.0,27.0,54.5,31.5"

# اندازه خروجی رستر
WIDTH = 800
HEIGHT = 600

# تعداد روزهای پیش‌بینی
FORECAST_DAYS = 9

# تعداد تلاش مجدد
MAX_RETRIES = 5

# فاصله بین تلاش‌ها
RETRY_DELAY = 10


# ============================================================
# بررسی Boundary فارس
# ============================================================

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

    features = data.get("features", [])

    if not features:
        raise ValueError(
            "fars.geojson does not contain any features."
        )

    print("Fars boundary loaded successfully.")
    print(f"Features: {len(features)}")


# ============================================================
# ساخت آدرس WMS
# ============================================================

def build_wms_params(date_str):

    return {
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
        "SINGLETILE": "false",
        "TIME": date_str,
    }


# ============================================================
# دریافت پایدار فایل
# ============================================================

def download_fwi(date_str, output_file):

    print("")
    print("=" * 70)
    print(f"Downloading FWI for: {date_str}")
    print("=" * 70)

    headers = {
        "User-Agent": "FARS-FIRE-RISK-FORECAST/1.0",
        "Accept": "image/tiff,*/*",
        "Accept-Encoding": "identity",
        "Connection": "close",
    }

    params = build_wms_params(date_str)

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"Attempt {attempt}/{MAX_RETRIES}"
        )

        try:

            with requests.get(
                WMS_URL,
                params=params,
                headers=headers,
                stream=True,
                timeout=(30, 180),
            ) as response:

                print(
                    f"HTTP status: {response.status_code}"
                )

                print(
                    "Content-Type:",
                    response.headers.get(
                        "Content-Type",
                        ""
                    )
                )

                response.raise_for_status()

                temp_file = output_file + ".part"

                total_bytes = 0

                with open(
                    temp_file,
                    "wb"
                ) as f:

                    for chunk in response.iter_content(
                        chunk_size=64 * 1024
                    ):

                        if not chunk:
                            continue

                        f.write(chunk)
                        total_bytes += len(chunk)

                print(
                    f"Downloaded bytes: {total_bytes}"
                )

                # پاسخ خیلی کوچک احتمالاً خطای سرویس است
                if total_bytes < 1000:

                    with open(
                        temp_file,
                        "rb"
                    ) as f:
                        sample = f.read(3000)

                    try:
                        sample_text = sample.decode(
                            "utf-8",
                            errors="ignore"
                        )
                    except Exception:
                        sample_text = ""

                    print(
                        "Server response preview:"
                    )
                    print(sample_text)

                    raise RuntimeError(
                        "Server returned an unexpectedly "
                        "small response."
                    )

                # بررسی ابتدایی TIFF
                with open(
                    temp_file,
                    "rb"
                ) as f:

                    header = f.read(4)

                valid_tiff = (
                    header.startswith(b"II*\x00")
                    or header.startswith(b"MM\x00*")
                )

                if not valid_tiff:

                    print(
                        "WARNING: Response does not "
                        "look like a TIFF file."
                    )

                    with open(
                        temp_file,
                        "rb"
                    ) as f:
                        sample = f.read(3000)

                    print(
                        sample.decode(
                            "utf-8",
                            errors="ignore"
                        )
                    )

                    raise RuntimeError(
                        "EFFIS response is not a valid TIFF."
                    )

                # انتقال فایل موقت به فایل نهایی
                os.replace(
                    temp_file,
                    output_file
                )

                print(
                    f"Saved successfully: {output_file}"
                )

                return

        except Exception as e:

            last_error = e

            print(
                f"Attempt {attempt} failed:"
            )
            print(str(e))

            temp_file = output_file + ".part"

            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

            if attempt < MAX_RETRIES:

                print(
                    f"Waiting {RETRY_DELAY} seconds "
                    "before retry..."
                )

                time.sleep(
                    RETRY_DELAY
                )

    raise RuntimeError(
        f"FWI download failed after "
        f"{MAX_RETRIES} attempts for "
        f"{date_str}: {last_error}"
    )


# ============================================================
# ساخت Metadata
# ============================================================

def create_metadata(files):

    return {
        "source": "Copernicus EFFIS",
        "service": WMS,
        "layer": LAYER,
        "model": "ECMWF",
        "spatial_resolution": "approximately 8 km",
        "forecast_days": FORECAST_DAYS,
        "boundary": FARS_FILE,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "files": files,
    }


# ============================================================
# اجرای اصلی
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("FARS FIRE RISK - FWI ENGINE")
    print("=" * 70)

    # --------------------------------------------------------
    # بررسی Boundary
    # --------------------------------------------------------

    check_fars_boundary()

    # --------------------------------------------------------
    # ساخت پوشه خروجی
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # تاریخ امروز
    # --------------------------------------------------------

    today = datetime.now(
        timezone.utc
    ).date()

    downloaded_files = []

    # --------------------------------------------------------
    # دریافت پیش‌بینی 9 روزه
    # --------------------------------------------------------

    for day_ahead in range(
        FORECAST_DAYS
    ):

        forecast_date = (
            today
            + timedelta(
                days=day_ahead
            )
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

            downloaded_files.append(
                {
                    "date": date_str,
                    "day_ahead": day_ahead,
                    "file": f"fwi_{date_str}.tif",
                }
            )

        except Exception as e:

            print("")
            print(
                "=" * 70
            )
            print(
                "ERROR: FWI DOWNLOAD FAILED"
            )
            print(
                f"Date: {date_str}"
            )
            print(
                str(e)
            )
            print(
                "=" * 70
            )

            # Workflow باید قرمز شود
            raise

    # --------------------------------------------------------
    # ساخت Metadata
    # --------------------------------------------------------

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
    print("=" * 70)
    print("FWI UPDATE COMPLETED SUCCESSFULLY")
    print("=" * 70)

    print(
        f"Downloaded files: "
        f"{len(downloaded_files)}"
    )

    print(
        f"Output directory: "
        f"{OUTPUT_DIR}"
    )

    print(
        f"Metadata file: "
        f"{metadata_file}"
    )


# ============================================================
# اجرای برنامه
# ============================================================

if __name__ == "__main__":
    main()
