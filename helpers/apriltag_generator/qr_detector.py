"""
QR Code Detection Module

Uses standard OpenCV QRCodeDetector (no contrib required) for calibration.
Loads ground truth from generated JSON metadata and computes homography
between camera pixel coordinates and world coordinates (mm).

Dependencies:
- opencv-python: QR detection and homography
- numpy: Array operations
"""

import json
import cv2
import numpy as np


class QRCalibrationDetector:
    """Detect QR codes and compute camera-to-world transformations."""

    def __init__(self, metadata_path: str):
        """
        Initialize detector with ground truth metadata.

        Args:
            metadata_path: Path to calibration JSON file
        """
        with open(metadata_path) as f:
            self.metadata = json.load(f)

        # Build lookup table: content string -> marker data
        self.marker_lookup = {
            m["content"]: m for m in self.metadata["markers"]
        }

        # Initialize OpenCV detector
        self.detector = cv2.QRCodeDetector()

    def detect(self, image: np.ndarray) -> list:
        """
        Detect a single QR code in image.

        Args:
            image: Input image (BGR or grayscale)

        Returns:
            List with single detection dict, or empty list if none found.
            Each detection contains:
                - id: Marker ID
                - content: Decoded string
                - corners_px: 4 corners in pixel coordinates
                - corners_mm: 4 corners in world coordinates (from metadata)
                - center_mm: Center in world coordinates
        """
        # Detect and decode
        data, points, _ = self.detector.detectAndDecode(image)

        if points is None or not data:
            return []

        # Convert points shape from [1, 4, 2] to [4, 2]
        corners_px = points[0].astype(np.float32)

        # Look up ground truth
        if data not in self.marker_lookup:
            return []  # Unknown marker

        marker = self.marker_lookup[data]

        return [{
            "id": marker["id"],
            "content": data,
            "corners_px": corners_px.tolist(),
            "corners_mm": marker["corners_mm"],
            "center_mm": marker["center_mm"],
            "finder_centers_mm": marker.get("finder_centers_mm"),
        }]

    def detect_multi(self, image: np.ndarray) -> list:
        """
        Detect multiple QR codes in image.

        Args:
            image: Input image (BGR or grayscale)

        Returns:
            List of detection dicts (same format as detect())
        """
        # Use detectAndDecodeMulti for multiple codes
        retval, decoded_info, points, _ = self.detector.detectAndDecodeMulti(image)

        if not retval or points is None:
            return []

        results = []
        for i, data in enumerate(decoded_info):
            if not data or data not in self.marker_lookup:
                continue

            marker = self.marker_lookup[data]
            corners_px = points[i].astype(np.float32)

            results.append({
                "id": marker["id"],
                "content": data,
                "corners_px": corners_px.tolist(),
                "corners_mm": marker["corners_mm"],
                "center_mm": marker["center_mm"],
                "finder_centers_mm": marker.get("finder_centers_mm"),
            })

        return results

    def refine_corners(self, image: np.ndarray, corners: np.ndarray) -> np.ndarray:
        """
        Refine QR code corner positions to sub-pixel accuracy.

        Args:
            image: Grayscale input image
            corners: Detected corners [4, 2] or [N, 2]

        Returns:
            Refined corners with same shape
        """
        gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Refinement criteria
        criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,    # Max iterations
            0.001  # Epsilon
        )

        # Corner refinement window size (in pixels)
        win_size = (5, 5)
        zero_zone = (-1, -1)

        # Ensure corners are in correct shape for cornerSubPix
        corners_input = corners.reshape(-1, 1, 2).astype(np.float32)

        # Refine corners
        refined = cv2.cornerSubPix(
            gray,
            corners_input,
            win_size,
            zero_zone,
            criteria
        )

        return refined.reshape(-1, 2)

    def compute_homography(self, detections: list) -> tuple:
        """
        Compute homography from detected markers.

        Uses all corner correspondences from detected QR codes to compute
        a homography matrix that transforms pixel coordinates to world
        coordinates (mm).

        Args:
            detections: List from detect() or detect_multi()

        Returns:
            (homography_matrix, reprojection_error) or (None, None) if
            insufficient points (need at least 4 correspondences)
        """
        if not detections:
            return None, None

        # Collect all corner correspondences
        src_points = []  # Pixel coordinates
        dst_points = []  # World coordinates (mm)

        for det in detections:
            for px, mm in zip(det["corners_px"], det["corners_mm"]):
                src_points.append(px)
                dst_points.append(mm)

        if len(src_points) < 4:
            return None, None

        src = np.array(src_points, dtype=np.float32)
        dst = np.array(dst_points, dtype=np.float32)

        # Compute homography with RANSAC
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)

        if H is None:
            return None, None

        # Calculate reprojection error
        src_h = np.hstack([src, np.ones((len(src), 1))])
        projected = (H @ src_h.T).T
        projected = projected[:, :2] / projected[:, 2:3]
        error = np.sqrt(np.mean(np.sum((projected - dst) ** 2, axis=1)))

        return H, error


def pixel_to_world(H: np.ndarray, pixel_point: tuple) -> tuple:
    """
    Convert pixel coordinate to world coordinate using homography.

    Args:
        H: 3x3 homography matrix
        pixel_point: (x, y) in pixels

    Returns:
        (x, y) in mm
    """
    p = np.array([pixel_point[0], pixel_point[1], 1.0])
    w = H @ p
    return (w[0] / w[2], w[1] / w[2])


def world_to_pixel(H: np.ndarray, world_point: tuple) -> tuple:
    """
    Convert world coordinate to pixel coordinate using homography.

    Args:
        H: 3x3 homography matrix (pixel -> world)
        world_point: (x, y) in mm

    Returns:
        (x, y) in pixels
    """
    H_inv = np.linalg.inv(H)
    p = np.array([world_point[0], world_point[1], 1.0])
    w = H_inv @ p
    return (w[0] / w[2], w[1] / w[2])


# ===============================
# Example Usage
# ===============================

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Example: detect QR codes in an image
    if len(sys.argv) < 3:
        print("Usage: python qr_detector.py <metadata.json> <image>")
        print("Example: python qr_detector.py output/calibration_qr_letter.json photo.png")
        sys.exit(1)

    metadata_path = sys.argv[1]
    image_path = sys.argv[2]

    # Load detector
    detector = QRCalibrationDetector(metadata_path)

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Could not load image '{image_path}'")
        sys.exit(1)

    # Detect QR codes
    detections = detector.detect_multi(image)

    if not detections:
        print("No QR codes detected")
        sys.exit(0)

    print(f"Detected {len(detections)} QR code(s):")
    for det in detections:
        print(f"  ID {det['id']}: center at {det['center_mm']} mm")

    # Compute homography
    H, error = detector.compute_homography(detections)

    if H is not None:
        print(f"\nHomography computed successfully")
        print(f"Reprojection error: {error:.4f} mm")
        print(f"\nHomography matrix:")
        print(H)
    else:
        print("\nCould not compute homography (need more detections)")
