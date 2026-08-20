import json
import os
import subprocess
from datetime import datetime, timedelta, timezone


# ============================================================
# تنظیمات
# ============================================================

FARS_FILE = "fars.geojson"
OUTPUT_DIR = "data/fwi"

WMS_URL = "https://maps.effis.emergency.copernicus.eu/gwis"
LAYER = "ecmwf.fwi"

# محدوده تقریبی استان فارس
BBOX = "50.0,27.0,54.5,31.5"

# اندازه نقشه
WIDTH = 1000
HEIGHT = 700

# فقط پیش بینی یک روز آینده
FORECAST_DAYS = 1

MAX_RETRIES = 5


# ============================================================
# بررسی Boundary فارس
# ============================================================

def check_fars_boundary():

    print("=" * 70)
    print("Checking Fars boundary")
    print("=" * 70)

    if not os.path.exists(FARS_FILE):
        raise FileNotFoundError(
            f"Boundary file not found: {FARS_FILE}"
        )

    with open(
        FARS_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            "fars.geojson is not a valid GeoJSON FeatureCollection."
        )

    features = data.get("features", [])

    if not features:
        raise ValueError(
            "fars.geojson contains no features."
        )

    print(
        f"Fars boundary loaded successfully. "
        f"Features: {len(features)}"
    )


# ============================================================
# پاک کردن خروجی های قبلی
# ============================================================

def clean_old_fwi_files():

    print("")
    print("=" * 70)
    print("Cleaning old FWI files")
    print("=" * 70)

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(
            OUTPUT_DIR,
            exist_ok=True
        )
        return

    for filename in os.listdir(OUTPUT_DIR):

        if filename.startswith("fwi_") and filename.endswith(".png"):

            file_path = os.path.join(
                OUTPUT_DIR,
                filename
            )

            try:
                os.remove(file_path)

                print(
                    f"Removed old file: {filename}"
                )

            except Exception as e:

                print(
                    f"Could not remove {filename}: {e}"
                )


# ============================================================
# ساخت URL WMS
# ============================================================

def build_url(date_str):

    params = [
        ("LAYERS", LAYER),
        ("FORMAT", "image/png"),
        ("TRANSPARENT", "true"),
        ("SINGLETILE", "false"),
        ("SERVICE", "wms"),
        ("VERSION", "1.1.1"),
        ("REQUEST", "GetMap"),
        ("STYLES", ""),
        ("SRS", "EPSG:4326"),
        ("BBOX", BBOX),
        ("WIDTH", str(WIDTH)),
        ("HEIGHT", str(HEIGHT)),
        ("TIME", date_str),
    ]

    query = "&".join(
        f"{key}={value}"
        for key, value in params
    )

    return f"{WMS_URL}?{query}"


# ============================================================
# دانلود FWI فردا
# ============================================================

def download_fwi(date_str, output_file):

    url = build_url(date_str)

    print("")
    print("=" * 70)
    print(
        f"Downloading FWI forecast for: {date_str}"
    )
    print("=" * 70)

    temp_file = output_file + ".part"

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"Attempt {attempt}/{MAX_RETRIES}"
        )

        if os.path.exists(temp_file):

            try:
                os.remove(temp_file)
            except Exception:
                pass

        command = [
            "curl",

            "--fail",
            "--location",

            # جلوگیری از مشکلات HTTP/2
            "--http1.1",

            "--silent",
            "--show-error",

            "--retry",
            "3",

            "--retry-delay",
            "5",

            "--retry-all-errors",

            "--connect-timeout",
            "30",

            "--max-time",
            "300",

            "--header",
            "Accept: image/png",

            "--header",
            "Accept-Encoding: identity",

            "--user-agent",
            "FARS-FIRE-RISK-FORECAST/1.0",

            "--output",
            temp_file,

            url,
        ]

        try:

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=360
            )

            if result.returncode != 0:

                print("")
                print("curl error:")
                print(result.stderr)

                if attempt < MAX_RETRIES:
                    continue

                raise RuntimeError(
                    f"Unable to download FWI forecast for {date_str}"
                )

            if not os.path.exists(temp_file):

                raise RuntimeError(
                    "Output file was not created."
                )

            file_size = os.path.getsize(
                temp_file
            )

            print(
                f"Downloaded bytes: {file_size}"
            )

            # بررسی اندازه فایل
            if file_size < 1000:

                with open(
                    temp_file,
                    "rb"
                ) as f:

                    preview = f.read(3000)

                print(
                    "Server response:"
                )

                print(
                    preview.decode(
                        "utf-8",
                        errors="ignore"
                    )
                )

                raise RuntimeError(
                    "EFFIS returned an unexpectedly "
                    "small response."
                )

            # بررسی PNG
            with open(
                temp_file,
                "rb"
            ) as f:

                header = f.read(8)

            png_signature = (
                b"\x89PNG\r\n\x1a\n"
            )

            if header != png_signature:

                with open(
                    temp_file,
                    "rb"
                ) as f:

                    preview = f.read(3000)

                print(
                    "Response is not PNG:"
                )

                print(
                    preview.decode(
                        "utf-8",
                        errors="ignore"
                    )
                )

                raise RuntimeError(
                    "EFFIS response is not a valid PNG."
                )

            os.replace(
                temp_file,
                output_file
            )

            print("")
            print(
                f"Saved successfully: {output_file}"
            )

            return

        except Exception as e:

            print("")
            print(
                f"Attempt {attempt} failed:"
            )

            print(
                str(e)
            )

            if os.path.exists(temp_file):

                try:
                    os.remove(temp_file)
                except Exception:
                    pass

            if attempt < MAX_RETRIES:

                print(
                    "Retrying..."
                )


# ============================================================
# اجرای اصلی
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("FARS FIRE RISK - ONE DAY FWI FORECAST")
    print("=" * 70)

    # بررسی مرز
    check_fars_boundary()

    # ساخت پوشه
    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # حذف خروجی های قدیمی
    clean_old_fwi_files()

    # تاریخ امروز UTC
    today = datetime.now(
        timezone.utc
    ).date()

    # --------------------------------------------------------
    # مهم:
    # پیش بینی یک روز آینده = فردا
    # --------------------------------------------------------

    forecast_date = (
        today + timedelta(days=1)
    )

    date_str = (
        forecast_date.isoformat()
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        f"fwi_{date_str}.png"
    )

    # دریافت FWI فردا
    download_fwi(
        date_str,
        output_file
    )

    # --------------------------------------------------------
    # metadata
    # --------------------------------------------------------

    metadata = {

        "source":
            "Copernicus EFFIS / GWIS",

        "service":
            WMS_URL,

        "layer":
            LAYER,

        "model":
            "ECMWF",

        "forecast_type":
            "1 day forecast",

        "forecast_date":
            date_str,

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "boundary":
            FARS_FILE,

        "bbox":
            BBOX,

        "output":
            f"fwi_{date_str}.png"
    }

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
    print("FWI ONE-DAY FORECAST COMPLETED")
    print("=" * 70)

    print(
        f"Forecast date: {date_str}"
    )

    print(
        f"Output: {output_file}"
    )


# ============================================================
# شروع
# ============================================================

if __name__ == "__main__":
    main()
