import json
import os
import requests
import xml.etree.ElementTree as ET


WMS_URL = "https://maps.effis.emergency.copernicus.eu/effis"

OUTPUT_DIR = "data/fwi"

CAPABILITIES_FILE = os.path.join(
    OUTPUT_DIR,
    "wms_capabilities.xml"
)

LAYERS_FILE = os.path.join(
    OUTPUT_DIR,
    "wms_layers.json"
)


def download_capabilities():
    print("=" * 70)
    print("Getting EFFIS WMS capabilities")
    print("=" * 70)

    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetCapabilities",
        "VERSION": "1.1.1",
    }

    response = requests.get(
        WMS_URL,
        params=params,
        timeout=120,
        headers={
            "User-Agent": "FARS-FIRE-RISK-FORECAST/1.0",
            "Accept": "text/xml,application/xml,*/*",
        },
    )

    print("HTTP status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("Downloaded bytes:", len(response.content))

    response.raise_for_status()

    if len(response.content) < 1000:
        raise RuntimeError(
            "GetCapabilities response is unexpectedly small."
        )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    with open(
        CAPABILITIES_FILE,
        "wb"
    ) as f:
        f.write(response.content)

    print(
        f"Saved capabilities to: {CAPABILITIES_FILE}"
    )


def extract_layers():
    print("")
    print("=" * 70)
    print("Reading available WMS layers")
    print("=" * 70)

    with open(
        CAPABILITIES_FILE,
        "rb"
    ) as f:
        xml_data = f.read()

    root = ET.fromstring(xml_data)

    layers = []

    for layer in root.iter():
        tag = layer.tag.lower()

        if tag.endswith("layer"):

            name = None
            title = None

            for child in layer:
                child_tag = child.tag.lower()

                if child_tag.endswith("name"):
                    name = (
                        child.text.strip()
                        if child.text
                        else None
                    )

                elif child_tag.endswith("title"):
                    title = (
                        child.text.strip()
                        if child.text
                        else None
                    )

            if name:
                layers.append(
                    {
                        "name": name,
                        "title": title or "",
                    }
                )

    with open(
        LAYERS_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            layers,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Total layers found: {len(layers)}"
    )

    print("")
    print("Layers related to FWI / fire danger:")

    matches = []

    for item in layers:

        text = (
            item["name"]
            + " "
            + item["title"]
        ).lower()

        if any(
            keyword in text
            for keyword in [
                "fwi",
                "fire",
                "danger",
                "ecmwf",
                "forecast",
            ]
        ):
            matches.append(item)

            print(
                f"- {item['name']} | "
                f"{item['title']}"
            )

    if not matches:
        print(
            "No FWI/fire-danger related layer was found."
        )

    return layers


def main():

    print("")
    print("=" * 70)
    print("FARS FIRE RISK - EFFIS LAYER DISCOVERY")
    print("=" * 70)

    download_capabilities()

    extract_layers()

    print("")
    print("=" * 70)
    print("LAYER DISCOVERY COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()
