import json
import os
import subprocess
from datetime import datetime, timedelta, timezone


# ============================================================
# تنظیمات
# ============================================================

FARS_FILE = "fars.geojson"
OUTPUT_DIR = "data/fwi"

WMS_URL = "https://maps.effis.emergency.copernicus.eu/effis"
LAYER = "ecmwf007.fwi"

BBOX = "50.0,27.0,54.5,31.5"

WIDTH = 800
HEIGHT = 600

FORECAST_DAYS = 9

MAX_RETRIES = 5


# ============================================================
# بررسی Boundary
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
            "fars.geojson is not a valid FeatureCollection."
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
# ساخت URL
# ============================================================

def build_url(date_str):

    params = [
        ("LAYERS", LAYER),
        ("FORMAT", "image/tiff"),
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

    return (
        f"{WMS_URL}?{query}"
    )


# ============================================================
# دانلود با curl
# ============================================================

def download_fwi(date_str, output_file):

    url = build_url(date_str)

    print("")
    print("=" * 70)
    print(
        f"Downloading FWI for {date_str}"
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
            os.remove(temp_file)

        command = [
            "curl",
            "--fail",
            "--location",
            "--silent",
            "--show-error",

            # تلاش مجدد در خطای شبکه
            "--retry",
            "3",

            "--retry-delay",
            "5",

            "--retry-all-errors",

            # زمان اتصال
            "--connect-timeout",
            "30",

            # زمان کل
            "--max-time",
            "300",

            # جلوگیری از فشرده‌سازی
            "--header",
            "Accept-Encoding: identity",

            # User-Agent
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

                print(
                    "curl error:"
                )

                print(
                    result.stderr
                )

                if attempt < MAX_RETRIES:
                    continue

                raise RuntimeError(
                    "curl could not download "
                    f"FWI for {date_str}"
                )

            if not os.path.exists(
                temp_file
            ):
                raise RuntimeError(
                    "Output file was not created."
                )

            file_size = os.path.getsize(
                temp_file
            )

            print(
                f"Downloaded bytes: {file_size}"
            )

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
                    "EFFIS returned an "
                    "unexpectedly small file."
                )

            # بررسی TIFF
            with open(
                temp_file,
                "rb"
            ) as f:

                header = f.read(4)

            if not (
                header.startswith(
                    b"II*\x00"
                )
                or header.startswith(
                    b"MM\x00*"
                )
            ):

                with open(
                    temp_file,
                    "rb"
                ) as f:
                    preview = f.read(3000)

                print(
                    "Response is not TIFF:"
                )

                print(
                    preview.decode(
                        "utf-8",
                        errors="ignore"
                    )
                )

                raise RuntimeError(
                    "EFFIS response is "
                    "not a valid TIFF."
                )

            os.replace(
                temp_file,
                output_file
            )

            print(
                f"Saved successfully: "
                f"{output_file}"
            )

            return

        except Exception as e:

            print(
                f"Attempt {attempt} failed:"
            )

            print(
                str(e)
            )

            if attempt < MAX_RETRIES:
                continue

            raise


# ============================================================
# اجرای اصلی
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("FARS FIRE RISK - FWI ENGINE")
    print("=" * 70)

    check_fars_boundary()

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    today = datetime.now(
        timezone.utc
    ).date()

    files = []

    for day_ahead in range(
        FORECAST_DAYS
    ):

        date = (
            today
            + timedelta(
                days=day_ahead
            )
        )

        date_str = date.isoformat()

        output_file = os.path.join(
            OUTPUT_DIR,
            f"fwi_{date_str}.tif"
        )

        download_fwi(
            date_str,
            output_file
        )

        files.append(
            {
                "date": date_str,
                "day_ahead": day_ahead,
                "file": (
                    f"fwi_{date_str}.tif"
                ),
            }
        )

    metadata = {
        "source": (
            "Copernicus EFFIS"
        ),
        "layer": LAYER,
        "model": "ECMWF",
        "forecast_days": FORECAST_DAYS,
        "resolution": (
            "approximately 8 km"
        ),
        "boundary": FARS_FILE,
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "files": files,
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
    print(
        "FWI UPDATE COMPLETED"
    )
    print("=" * 70)

    print(
        f"Total files: {len(files)}"
    )


if __name__ == "__main__":
    main()
