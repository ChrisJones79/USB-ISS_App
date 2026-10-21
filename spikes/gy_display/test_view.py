"""Offline checks that the heatmap draws all 32x24 cells in the GY manual's order. No hardware.

Run: .venv/bin/python -m pytest spikes/gy_display -q
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gyframe import COLS, PIXELS, ROWS, Frame  # noqa: E402
from view import CELL, Heatmap  # noqa: E402


@pytest.fixture(scope="module")
def heat():
    app = QApplication.instance() or QApplication([])
    h = Heatmap()
    yield h
    del app


def render(heat, pixels):
    heat.show_frame(Frame(tuple(pixels), 25.0, 0.0))
    return heat.grab().toImage()


def cell(img, x, y):
    """Colour at the centre of on-screen cell (x, y), x from the left."""
    return img.pixelColor(x * CELL + CELL // 2, y * CELL + CELL // 2).name()


def test_widget_is_32_by_24_cells(heat):
    img = render(heat, [0.0] * PIXELS)
    assert (img.width(), img.height()) == (COLS * CELL, ROWS * CELL)


def test_every_stream_pixel_lands_in_its_own_cell(heat):
    # A unique value per pixel: every one of the 768 cells must show a distinct colour,
    # and pixel i must sit at row i // 32, with manual column i % 32 + 1 drawn from the right.
    img = render(heat, [float(i) for i in range(PIXELS)])
    seen = {}
    for i in range(PIXELS):
        row, col = divmod(i, COLS)
        seen[(COLS - 1 - col, row)] = cell(img, COLS - 1 - col, row)
    assert len(seen) == PIXELS
    # monotonic ramp: pixel 0 is the coldest (top right), pixel 767 the hottest (bottom left)
    assert cell(img, COLS - 1, 0) == "#000000"
    assert cell(img, 0, ROWS - 1) == "#ffffff"


@pytest.mark.parametrize("i, x, y", [(0, 31, 0), (31, 0, 0), (736, 31, 23), (767, 0, 23)])
def test_corners(heat, i, x, y):
    px = [20.0] * PIXELS
    px[i] = 30.0
    img = render(heat, px)
    hot = [(cx, cy) for cy in range(ROWS) for cx in range(COLS) if cell(img, cx, cy) == "#ffffff"]
    assert hot == [(x, y)]
