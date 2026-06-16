"""
QR Code Calibration Grid Generator

Generates QR code grids for robotic arm calibration using standard OpenCV
(no contrib module required). Follows the same patterns as apriltag_generator.py.

Dependencies:
- qrcode[pil]: QR code generation
- svgwrite: SVG output
"""

import json
import base64
from pathlib import Path
from io import BytesIO

import qrcode
import svgwrite


# ===============================
# Configuration
# ===============================

# QR Code Parameters
QR_VERSION = 1                              # 21x21 modules (smallest)
QR_ERROR_CORRECTION = qrcode.constants.ERROR_CORRECT_L  # 7% recovery
QR_BOX_SIZE = 10                            # Pixels per module for raster
QR_BORDER = 4                               # Quiet zone in modules (ISO minimum)

# Physical Dimensions (millimeters)
QR_SIZE_MM = 8.0                            # Total QR code size including quiet zone
GRID_PITCH_MM = 2.0                         # Gap between codes

# Derived values
QR_TOTAL_MODULES = 21 + (2 * QR_BORDER)     # 29 modules with quiet zone
QR_PIXELS = QR_TOTAL_MODULES * QR_BOX_SIZE  # 290 pixels

# Page Configuration (matching existing apriltag generator)
MARGIN_MM = 12.7  # 0.5 inch

PAGE_SIZES_MM = {
    "letter": (279.4, 215.9),
    "tabloid": (431.8, 279.4),
}

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ===============================
# QR Code Generation
# ===============================

def generate_qr_png(qr_id: int) -> bytes:
    """
    Generate a QR code image for the given ID.

    Args:
        qr_id: Numeric identifier to encode

    Returns:
        PNG image bytes
    """
    qr = qrcode.QRCode(
        version=QR_VERSION,
        error_correction=QR_ERROR_CORRECTION,
        box_size=QR_BOX_SIZE,
        border=QR_BORDER,
    )
    qr.add_data(str(qr_id))
    qr.make(fit=False)  # Don't auto-fit; use specified version

    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to bytes
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def draw_qr_svg(dwg, parent, x: float, y: float, size_mm: float, qr_id: int):
    """
    Embed a QR code as base64 PNG in the SVG.

    Args:
        dwg: SVG drawing object
        parent: Parent SVG group
        x, y: Position in mm (bottom-left corner of QR code)
        size_mm: Size in mm
        qr_id: QR code identifier
    """
    png_bytes = generate_qr_png(qr_id)
    b64 = base64.b64encode(png_bytes).decode("ascii")

    parent.add(
        dwg.image(
            href=f"data:image/png;base64,{b64}",
            insert=(x, y),
            size=(size_mm, size_mm),
        )
    )


# ===============================
# Grid Generation Helper
# ===============================

def generate_grid(dwg, parent, width: float, height: float):
    """Generate reference grid lines."""
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


# ===============================
# Coordinate Calculation Helpers
# ===============================

def calculate_qr_corners(x: float, y: float, size: float) -> list:
    """
    Calculate the 4 corners of a QR code.

    Returns corners in order: bottom-left, bottom-right, top-right, top-left
    (counter-clockwise from bottom-left, matching coordinate system convention)
    """
    return [
        [x, y],                    # Bottom-left
        [x + size, y],             # Bottom-right
        [x + size, y + size],      # Top-right
        [x, y + size],             # Top-left
    ]


def calculate_finder_centers(x: float, y: float, size: float) -> dict:
    """
    Calculate the centers of the three finder patterns.

    QR codes have finder patterns (the big corner squares) at:
    - Top-left
    - Top-right
    - Bottom-left

    Each finder pattern is 7x7 modules. For Version 1 (21x21 inner modules),
    with 4-module quiet zone, the finder centers are calculated from the
    outer edge of the printed QR code.

    Returns dict with 'top_left', 'top_right', 'bottom_left' centers in mm.
    """
    module_size = size / QR_TOTAL_MODULES

    # Finder pattern center offset from QR outer edge
    # Quiet zone (4 modules) + half of finder (3.5 modules) = 7.5 modules
    finder_offset = (QR_BORDER + 3.5) * module_size

    return {
        "top_left": [x + finder_offset, y + size - finder_offset],
        "top_right": [x + size - finder_offset, y + size - finder_offset],
        "bottom_left": [x + finder_offset, y + finder_offset],
    }


# ===============================
# Main Generator
# ===============================

def generate(page_name: str):
    """
    Generate QR code calibration grid for specified page size.

    Args:
        page_name: 'letter' or 'tabloid'
    """
    page_w, page_h = PAGE_SIZES_MM[page_name]

    usable_w = page_w - 2 * MARGIN_MM
    usable_h = page_h - 2 * MARGIN_MM

    # Create SVG
    dwg = svgwrite.Drawing(
        filename=str(OUTPUT_DIR / f"calibration_qr_{page_name}.svg"),
        size=(f"{page_w}mm", f"{page_h}mm"),
        viewBox=f"0 0 {page_w} {page_h}",
    )

    # Bottom-left origin (Y-up coordinate system)
    root = dwg.add(
        dwg.g(transform=f"translate(0,{page_h}) scale(1,-1)")
    )

    # Field with margin offset
    field = root.add(
        dwg.g(
            id="field",
            transform=f"translate({MARGIN_MM},{MARGIN_MM})"
        )
    )

    # Generate reference grid
    generate_grid(dwg, field, usable_w, usable_h)

    # Place QR codes
    markers_metadata = []
    qr_id = 0

    y = 0.0
    while y + QR_SIZE_MM <= usable_h:
        x = 0.0
        while x + QR_SIZE_MM <= usable_w:
            # Draw QR code
            draw_qr_svg(dwg, field, x, y, QR_SIZE_MM, qr_id)

            # Calculate metadata
            cx = x + QR_SIZE_MM / 2
            cy = y + QR_SIZE_MM / 2
            corners = calculate_qr_corners(x, y, QR_SIZE_MM)
            finder_centers = calculate_finder_centers(x, y, QR_SIZE_MM)

            markers_metadata.append({
                "id": qr_id,
                "content": str(qr_id),
                "center_mm": [cx, cy],
                "corners_mm": corners,
                "finder_centers_mm": finder_centers,
                "rotation_deg": 0.0,
            })

            qr_id += 1
            x += QR_SIZE_MM + GRID_PITCH_MM

        y += QR_SIZE_MM + GRID_PITCH_MM

    # Build metadata
    metadata = {
        "page": page_name,
        "page_size_mm": [page_w, page_h],
        "margin_mm": MARGIN_MM,
        "usable_area_mm": [usable_w, usable_h],
        "marker_type": "qrcode",
        "qr_version": QR_VERSION,
        "qr_error_correction": "L",
        "qr_size_mm": QR_SIZE_MM,
        "grid_pitch_mm": GRID_PITCH_MM,
        "origin": "bottom-left",
        "coordinate_system": "Y-up",
        "total_markers": len(markers_metadata),
        "markers": markers_metadata,
    }

    # Save outputs
    json_path = OUTPUT_DIR / f"calibration_qr_{page_name}.json"
    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2)

    dwg.save()

    print(f"Generated {page_name}:")
    print(f"  - {len(markers_metadata)} QR codes")
    print(f"  - SVG: {OUTPUT_DIR / f'calibration_qr_{page_name}.svg'}")
    print(f"  - JSON: {json_path}")


if __name__ == "__main__":
    generate("letter")
    generate("tabloid")
