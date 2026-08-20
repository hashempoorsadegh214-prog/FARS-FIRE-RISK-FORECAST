import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw


# ============================================================
# تنظیمات
# ============================================================

FARS_FILE = "fars.geojson"
OUTPUT_DIR = "data/fwi"

WMS_URL = "https://maps.effis.emergency.copernicus.eu/gwis"
LAYER = "ecmwf.fwi"

# کادر پوشاننده استان فارس
WEST = 50.0
SOUTH = 27.0
EAST = 54.5
NORTH = 31.5

WIDTH = 1000
HEIGHT = 700

MAX_RETRIES = 5


# ============================================================
# خواندن Boundary فارس
# ============================================================

def load_fars_boundary():
    if not os.path.exists(FARS_FILE):
        raise FileNotFoundError(
            f"Boundary file not found: {FARS_FILE}"
        )

    with open(FARS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            "fars.geojson must be a GeoJSON FeatureCollection."
        )

    features = data.get("features", [])

    if not features:
        raise ValueError(
            "fars.geojson contains no features."
        )

    print(f"Fars boundary loaded: {len(features)} feature(s)")

    return data


# ============================================================
# استخراج Polygon / MultiPolygon
# ============================================================

def get_polygons(geojson_data):

    polygons = []

    for feature in geojson_data["features"]:

        geometry = feature.get("geometry")

        if not geometry:
            continue

        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")

        if geometry_type == "Polygon":
            polygons.append(coordinates)

        elif geometry_type == "MultiPolygon":
            for polygon in coordinates:
                polygons.append(polygon)

    if not polygons:
        raise ValueError(
            "No Polygon or MultiPolygon geometry found."
        )

    print(f"Polygon parts found: {len(polygons)}")

    return polygons


# ============================================================
# تبدیل طول و عرض جغرافیایی به پیکسل
# ============================================================

def geo_to_pixel(lon, lat):

    x = (
        (lon - WEST)
        / (EAST - WEST)
        * (WIDTH - 1)
    )

    y = (
        (NORTH - lat)
        / (NORTH - SOUTH)
        * (HEIGHT - 1)
    )

    return (
        int(round(x)),
        int(round(y))
    )


# ============================================================
# ساخت ماسک دقیق فارس
# ============================================================

def create_fars_mask(polygons):

    mask = Image.new(
        "L",
        (WIDTH, HEIGHT),
        0
    )

    draw = ImageDraw.Draw(mask)

    for polygon in polygons:

        if not polygon:
            continue

        # مرز خارجی
        outer_ring = polygon[0]

        outer_pixels = [
            geo_to_pixel(
                point[0],
                point[1]
            )
            for point in outer_ring
        ]

        if len(outer_pixels) >= 3:
            draw.polygon(
                outer_pixels,
                fill=255
            )

        # حفره‌های داخلی
        for hole in polygon[1:]:

            hole_pixels = [
                geo_to_pixel(
                    point[0],
                    point[1]
                )
                for point in hole
            ]

            if len(hole_pixels) >= 3:
                draw.polygon(
                    hole_pixels,
                    fill=0
                )

    return mask


# ============================================================
# ساخت URL سرویس FWI
# ============================================================

def build_wms_url(date_str):

    bbox = (
        f"{WEST},{SOUTH},{EAST},{NORTH}"
    )

    return (
        f"{WMS_URL}"
        f"?LAYERS={LAYER}"
        f"&FORMAT=image/png"
        f"&TRANSPARENT=true"
        f"&SINGLETILE=false"
        f"&SERVICE=wms"
        f"&VERSION=1.1.1"
        f"&REQUEST=GetMap"
        f"&STYLES="
        f"&SRS=EPSG:4326"
        f"&BBOX={bbox}"
        f"&WIDTH={WIDTH}"
        f"&HEIGHT={HEIGHT}"
        f"&TIME={date_str}"
    )


# ============================================================
# دانلود نقشه FWI
# ============================================================

def download_fwi(date_str, output_file):

    url = build_wms_url(date_str)
    temp_file = output_file + ".part"

    print("")
    print("=" * 70)
    print(f"Downloading FWI forecast: {date_str}")
    print("=" * 70)

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"Attempt {attempt}/{MAX_RETRIES}"
        )

        if os.path.exists(temp_file):
            os.remove(temp_file)

        command = [
            "curl",
            "--fail",
            "--location",
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

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=360
        )

        if result.returncode != 0:

            print("curl error:")
            print(result.stderr)

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"FWI download failed for {date_str}"
                )

            continue

        if not os.path.exists(temp_file):
            raise RuntimeError(
                "Downloaded file was not created."
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
                response_preview = f.read(3000)

            print(
                response_preview.decode(
                    "utf-8",
                    errors="ignore"
                )
            )

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "EFFIS returned an invalid response."
                )

            continue

        # بررسی هدر PNG
        with open(
            temp_file,
            "rb"
        ) as f:
            header = f.read(8)

        if header != b"\x89PNG\r\n\x1a\n":

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "Downloaded file is not a valid PNG."
                )

            continue

        os.replace(
            temp_file,
            output_file
        )

        print(
            f"Downloaded successfully: {output_file}"
        )

        return


# ============================================================
# اعمال مرز واقعی فارس روی تصویر
# ============================================================

def clip_to_fars(
    input_file,
    output_file,
    polygons
):

    print("")
    print("=" * 70)
    print("Applying exact Fars boundary")
    print("=" * 70)

    image = Image.open(
        input_file
    ).convert("RGBA")

    # ماسک دقیق فارس
    mask = create_fars_mask(
        polygons
    )

    # آلفای فعلی تصویر
    original_alpha = image.getchannel("A")

    # آلفای نهایی:
    # داخل فارس = تصویر
    # خارج فارس = کاملاً شفاف
    final_alpha = Image.composite(
        original_alpha,
        Image.new(
            "L",
            image.size,
            0
        ),
        mask
    )

    image.putalpha(
        final_alpha
    )

    image.save(
        output_file,
        format="PNG",
        optimize=True
    )

    print(
        f"Final Fars map created: {output_file}"
    )


# ============================================================
# اجرای اصلی
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("FARS FIRE RISK - FWI ENGINE")
    print("=" * 70)

    # --------------------------------------------------------
    # Boundary
    # --------------------------------------------------------

    boundary = load_fars_boundary()

    polygons = get_polygons(
        boundary
    )

    # --------------------------------------------------------
    # پوشه خروجی
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # تاریخ فردا
    # --------------------------------------------------------

    today = datetime.now(
        timezone.utc
    ).date()

    forecast_date = (
        today + timedelta(days=1)
    )

    date_str = (
        forecast_date.isoformat()
    )

    # --------------------------------------------------------
    # فایل موقت و فایل نهایی
    # --------------------------------------------------------

    raw_file = os.path.join(
        OUTPUT_DIR,
        f"raw_{date_str}.png"
    )

    final_file = os.path.join(
        OUTPUT_DIR,
        f"fwi_{date_str}.png"
    )

    # --------------------------------------------------------
    # دانلود
    # --------------------------------------------------------

    download_fwi(
        date_str,
        raw_file
    )

    # --------------------------------------------------------
    # برش دقیق فارس
    # --------------------------------------------------------

    clip_to_fars(
        raw_file,
        final_file,
        polygons
    )

    # --------------------------------------------------------
    # حذف فایل خام
    # --------------------------------------------------------

    if os.path.exists(raw_file):
        os.remove(raw_file)

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = {
        "source": "Copernicus EFFIS / GWIS",
        "layer": LAYER,
        "model": "ECMWF",
        "forecast_type": "1 day forecast",
        "forecast_date": date_str,
        "boundary": FARS_FILE,
        "bbox": (
            f"{WEST},{SOUTH},{EAST},{NORTH}"
        ),
        "output": (
            f"fwi_{date_str}.png"
        ),
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        )
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
    print("FWI PROCESS COMPLETED")
    print("=" * 70)
    print(
        f"Forecast date: {date_str}"
    )
    print(
        f"Final output: {final_file}"
    )


if __name__ == "__main__":
    main()
