"""OpenCV preprocessing for scanned pages: grayscale, denoise, deskew, binarize."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreprocessResult:
    image: np.ndarray
    scale: float
    deskew_angle: float


def _deskew_angle(binary: np.ndarray) -> float:
    try:
        coords = np.column_stack(np.where(binary < 128))
        if coords.shape[0] < 200:
            return 0.0
        if coords.shape[0] > 120_000:
            step = max(1, coords.shape[0] // 120_000)
            coords = coords[::step]
        angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.25 or abs(angle) > 15:
            return 0.0
        return float(angle)
    except Exception:  # pragma: no cover - defensive
        return 0.0


def preprocess_image(image_bgr: np.ndarray, *, min_width: int = 1800) -> PreprocessResult:
    if image_bgr is None or image_bgr.size == 0:
        raise ValueError("empty image")
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    scale = 1.0
    if width < min_width:
        scale = min_width / max(1, width)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=15,
    )
    angle = _deskew_angle(binary)
    if angle:
        h, w = binary.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        binary = cv2.warpAffine(
            binary,
            matrix,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )
    # Remove scanner borders/shadows at the page edge.
    border = 3
    binary[:border, :] = 255
    binary[-border:, :] = 255
    binary[:, :border] = 255
    binary[:, -border:] = 255
    logger.debug("preprocess scale=%.2f deskew=%.2f", scale, angle)
    return PreprocessResult(image=binary, scale=scale, deskew_angle=angle)
