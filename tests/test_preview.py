"""Preview fit and paint tests. DrawingArea smoke test needs a display."""

import cairo
import pytest

from core.renderer import RenderedFrame
from mophic.preview import LETTERBOX_COLOR, FramePreview, fit_rect, paint


def solid_frame(width, height, color=(1.0, 0.0, 0.0, 1.0)):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgba(*color)
    ctx.paint()
    surface.flush()
    return RenderedFrame(surface)


def paint_to_surface(width, height, frame):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    paint(cairo.Context(surface), width, height, frame)
    surface.flush()
    return RenderedFrame(surface)


def read_pixel(frame, x, y):
    return frame.pixel(x, y)


# --- fit_rect --------------------------------------------------------------------------------

def test_fit_rect_letterboxes_wide_area():
    fit = fit_rect(1920, 1080, 800, 500)
    assert fit.scale == pytest.approx(800 / 1920)
    assert fit.width == pytest.approx(800)
    assert fit.height == pytest.approx(1080 * 800 / 1920)
    assert fit.x == pytest.approx(0)
    assert fit.y == pytest.approx((500 - fit.height) / 2)


def test_fit_rect_pillarboxes_tall_area():
    fit = fit_rect(1920, 1080, 500, 800)
    assert fit.scale == pytest.approx(500 / 1920)
    assert fit.width == pytest.approx(500)
    assert fit.x == pytest.approx(0)
    assert fit.y == pytest.approx((800 - fit.height) / 2)


def test_fit_rect_exact_match():
    fit = fit_rect(100, 50, 200, 100)
    assert fit.scale == pytest.approx(2.0)
    assert (fit.x, fit.y, fit.width, fit.height) == (0.0, 0.0, 200.0, 100.0)


def test_fit_rect_zero_sizes():
    assert fit_rect(100, 50, 0, 100).scale == 0
    assert fit_rect(0, 50, 100, 100).scale == 0
    assert fit_rect(100, 50, 100, 0).scale == 0


# --- paint -----------------------------------------------------------------------------------

def letterbox_rgb():
    return tuple(round(c * 255) for c in LETTERBOX_COLOR)


def assert_near(pixel, expected, tolerance=2):
    for got, want in zip(pixel, expected):
        assert abs(got - want) <= tolerance, (pixel, expected)


def test_paint_letterboxes_wide_widget():
    frame = solid_frame(1920, 1080, (1, 0, 0, 1))
    painted = paint_to_surface(800, 500, frame)
    fit = fit_rect(1920, 1080, 800, 500)
    top = max(0, int(fit.y) - 1)
    assert_near(read_pixel(painted, 400, top), (*letterbox_rgb(), 255))
    # Centre of the fitted frame is red.
    cy = int(fit.y + fit.height / 2)
    cx = int(fit.x + fit.width / 2)
    assert_near(read_pixel(painted, cx, cy), (255, 0, 0, 255))


def test_paint_pillarboxes_tall_widget():
    frame = solid_frame(1920, 1080, (0, 1, 0, 1))
    painted = paint_to_surface(500, 800, frame)
    fit = fit_rect(1920, 1080, 500, 800)
    # Side letterbox if any; with 16:9 into 500x800, width fills and y is padded.
    assert fit.x == pytest.approx(0)
    above = max(0, int(fit.y) - 1)
    assert_near(read_pixel(painted, 250, above), (*letterbox_rgb(), 255))
    cy = int(fit.y + fit.height / 2)
    assert_near(read_pixel(painted, 250, cy), (0, 255, 0, 255))


def test_paint_near_exact_aspect():
    frame = solid_frame(1920, 1080, (0, 0, 1, 1))
    painted = paint_to_surface(1000, 563, frame)
    fit = fit_rect(1920, 1080, 1000, 563)
    assert abs(fit.x) < 1 or abs(fit.y) < 1
    cx = int(fit.x + fit.width / 2)
    cy = int(fit.y + fit.height / 2)
    assert_near(read_pixel(painted, cx, cy), (0, 0, 255, 255))


def test_paint_none_frame_is_letterbox_only():
    painted = paint_to_surface(40, 30, None)
    assert_near(read_pixel(painted, 20, 15), (*letterbox_rgb(), 255))


def test_paint_does_not_mutate_source():
    frame = solid_frame(20, 10)
    before = bytes(frame.surface.get_data())
    paint_to_surface(80, 50, frame)
    frame.surface.flush()
    assert bytes(frame.surface.get_data()) == before


# --- GTK smoke -------------------------------------------------------------------------------

def test_frame_preview_set_frame_smoke():
    gi = pytest.importorskip('gi')
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk

    if not Gtk.init_check():
        pytest.skip('no display')

    area = Gtk.DrawingArea()
    preview = FramePreview(area)
    assert preview.frame is None
    frame = solid_frame(16, 9)
    preview.set_frame(frame)
    assert preview.frame is frame
    preview.set_frame(None)
    assert preview.frame is None
