import json
import base64
from pathlib import Path
from io import BytesIO

import cv2
import numpy as np
import svgwrite


# ===============================
# Configuration
# ===============================

APRILTAG_DICT = cv2.aruco.DICT_APRILTAG_36h11
TAG_SIZE_MM = 12.0
TAG_PIXELS = 200      # raster resolution per tag
GRID_PITCH_MM = 2.0

MARGIN_MM = 12.7  # 0.5 inch

PAGE_SIZES_MM = {
    "letter": (279.4, 215.9),
    "tabloid": (431.8, 279.4),
}

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

dictionary = cv2.aruco.getPredefinedDictionary(APRILTAG_DICT)
MAX_TAG_ID = dictionary.bytesList.shape[0]

# ===============================
# Helpers
# ===============================

def generate_grid(dwg, parent, width, height):
    grid = parent.add(
        dwg.g(
            id="grid",
            stroke="#cccccc",
            stroke_width=0.1,
        )
    )

    x = 0.0
    while x <= width:
        grid.add(dwg.line(start=(x, 0), end=(x, height)))
        x += GRID_PITCH_MM

    y = 0.0
    while y <= height:
        grid.add(dwg.line(start=(0, y), end=(width, y)))
        y += GRID_PITCH_MM


def generate_apriltag_png(tag_id):
    """
    Generate a real tag36h11 image using OpenCV (version-robust).
    Returns PNG bytes.
    """
    dictionary = cv2.aruco.getPredefinedDictionary(APRILTAG_DICT)

    img = dictionary.generateImageMarker(tag_id, TAG_PIXELS)

    _, png = cv2.imencode(".png", img)
    return png.tobytes()

def draw_apriltag_svg(dwg, parent, x, y, size_mm, tag_id):
    png_bytes = generate_apriltag_png(tag_id)
    b64 = base64.b64encode(png_bytes).decode("ascii")

    parent.add(
        dwg.image(
            href=f"data:image/png;base64,{b64}",
            insert=(x, y),
            size=(size_mm, size_mm),
        )
    )


# ===============================
# Main Generator
# ===============================

def generate(page_name):
    page_w, page_h = PAGE_SIZES_MM[page_name]

    usable_w = page_w - 2 * MARGIN_MM
    usable_h = page_h - 2 * MARGIN_MM

    dwg = svgwrite.Drawing(
        filename=OUTPUT_DIR / f"calibration_{page_name}.svg",
        size=(f"{page_w}mm", f"{page_h}mm"),
        viewBox=f"0 0 {page_w} {page_h}",
    )

    # Bottom-left origin
    root = dwg.add(
        dwg.g(transform=f"translate(0,{page_h}) scale(1,-1)")
    )

    field = root.add(
        dwg.g(
            id="field",
            transform=f"translate({MARGIN_MM},{MARGIN_MM})"
        )
    )

    generate_grid(dwg, field, usable_w, usable_h)

    tags_metadata = []

    tag_id = 0
    y = 0.0
    while y + TAG_SIZE_MM <= usable_h and tag_id < MAX_TAG_ID:
        x = 0.0
        while x + TAG_SIZE_MM <= usable_w and tag_id < MAX_TAG_ID:
            draw_apriltag_svg(
                dwg,
                field,
                x,
                y,
                TAG_SIZE_MM,
                tag_id,
            )

            cx = x + TAG_SIZE_MM / 2
            cy = y + TAG_SIZE_MM / 2

            corners = [
                [x, y],
                [x + TAG_SIZE_MM, y],
                [x + TAG_SIZE_MM, y + TAG_SIZE_MM],
                [x, y + TAG_SIZE_MM],
            ]

            tags_metadata.append(
                {
                    "id": tag_id,
                    "center_mm": [cx, cy],
                    "corners_mm": corners,
                    "rotation_deg": 0.0,
                }
            )

            tag_id += 1
            x += TAG_SIZE_MM + GRID_PITCH_MM

        y += TAG_SIZE_MM + GRID_PITCH_MM

    metadata = {
        "page": page_name,
        "page_size_mm": [page_w, page_h],
        "margin_mm": MARGIN_MM,
        "usable_area_mm": [usable_w, usable_h],
        "apriltag_family": "tag36h11",
        "tag_size_mm": TAG_SIZE_MM,
        "grid_pitch_mm": GRID_PITCH_MM,
        "origin": "bottom-left",
        "tags": tags_metadata,
    }

    with open(OUTPUT_DIR / f"calibration_{page_name}.json", "w") as f:
        json.dump(metadata, f, indent=2)

    dwg.save()


if __name__ == "__main__":
    generate("letter")
    generate("tabloid")
