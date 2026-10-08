import math
import os
import subprocess
import sys
import textwrap

import cairo
import gi
import pytest

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

from core import (EASE_IN_OUT, EASE_OUT, Color, Composition, ImageLayer, Layer, Point, Scale,
                  ShapeLayer, SolidLayer, TextLayer, project_to_dict, Project)
from core.renderer import CairoRenderer, Pixel, RenderedFrame, RenderError, Renderer

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BLACK = Color(0.0, 0.0, 0.0, 1.0)
WHITE = Color(1.0, 1.0, 1.0, 1.0)
RED = Color(1.0, 0.0, 0.0, 1.0)
GREEN = Color(0.0, 1.0, 0.0, 1.0)
BLUE = Color(0.0, 0.0, 1.0, 1.0)

BLACK_PX = Pixel(0, 0, 0, 255)
WHITE_PX = Pixel(255, 255, 255, 255)
RED_PX = Pixel(255, 0, 0, 255)
GREEN_PX = Pixel(0, 255, 0, 255)
BLUE_PX = Pixel(0, 0, 255, 255)


def make_comp(width=100, height=100, background=BLACK):
    return Composition(width=width, height=height, fps=30.0, duration=5.0,
                       background_color=background)


def render(comp, time=0.0):
    return CairoRenderer().render_frame(comp, time)


def rect(width=20, height=10, color=RED, **kwargs):
    return ShapeLayer(shape_type='rectangle', width=width, height=height, fill_color=color,
                      stroke_color=None, **kwargs)


def bbox(frame, background=BLACK_PX):
    """Bounding box (x0, y0, x1, y1), inclusive, of pixels differing from ``background``."""
    xs, ys = [], []
    for y in range(frame.height):
        for x in range(frame.width):
            if frame.pixel(x, y) != background:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def assert_bbox_near(actual, expected, tolerance=1):
    assert actual is not None
    for got, want in zip(actual, expected):
        assert abs(got - want) <= tolerance, (actual, expected)


def assert_pixel_near(pixel, expected, tolerance=2):
    for got, want in zip(pixel, expected):
        assert abs(got - want) <= tolerance, (pixel, expected)


def frame_bytes(frame):
    frame.surface.flush()
    return bytes(frame.surface.get_data())


def write_png(path, width, height, paint):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    paint(cairo.Context(surface))
    surface.write_to_png(str(path))


def red_blue_png(path):
    """A 10x6 image: left half red, right half blue."""
    def paint(ctx):
        ctx.set_source_rgb(1, 0, 0)
        ctx.rectangle(0, 0, 5, 6)
        ctx.fill()
        ctx.set_source_rgb(0, 0, 1)
        ctx.rectangle(5, 0, 5, 6)
        ctx.fill()
    write_png(path, 10, 6, paint)
    return str(path)


# --- Frames, surfaces and the renderer interface ---------------------------------------------

def test_cairo_renderer_satisfies_renderer_protocol():
    renderer: Renderer = CairoRenderer()
    assert isinstance(renderer.render_frame(make_comp(), 0.0), RenderedFrame)


def test_frame_has_composition_resolution_and_argb32_format():
    frame = render(make_comp(width=64, height=48))
    assert (frame.width, frame.height) == (64, 48)
    assert frame.surface.get_format() == cairo.FORMAT_ARGB32
    assert frame.stride >= 64 * 4


def test_empty_composition_is_background_everywhere():
    frame = render(make_comp(width=20, height=10, background=Color(0.2, 0.4, 0.6, 1.0)))
    expected = Pixel(51, 102, 153, 255)
    assert all(frame.pixel(x, y) == expected for y in range(10) for x in range(20))


def test_transparent_background_stays_transparent():
    frame = render(make_comp(width=8, height=8, background=Color(1.0, 0.0, 0.0, 0.0)))
    assert frame.pixel(4, 4) == Pixel(0, 0, 0, 0)


def test_translucent_background_keeps_its_alpha():
    frame = render(make_comp(width=8, height=8, background=Color(1.0, 1.0, 1.0, 0.5)))
    assert_pixel_near(frame.pixel(0, 0), (128, 128, 128, 128), tolerance=1)


@pytest.mark.parametrize('color, expected', [(RED, RED_PX), (GREEN, GREEN_PX), (BLUE, BLUE_PX)])
def test_primary_background_colors_have_correct_channels(color, expected):
    assert render(make_comp(width=4, height=4, background=color)).pixel(1, 1) == expected


def test_pixel_outside_frame_raises():
    frame = render(make_comp(width=4, height=4))
    for x, y in [(-1, 0), (0, -1), (4, 0), (0, 4)]:
        with pytest.raises(IndexError):
            frame.pixel(x, y)


def test_oversized_composition_raises_render_error():
    comp = make_comp(width=100_000, height=100_000)
    with pytest.raises(RenderError, match='surface'):
        render(comp)


def test_render_frame_validates_arguments():
    renderer = CairoRenderer()
    with pytest.raises(TypeError):
        renderer.render_frame(object(), 0.0)
    with pytest.raises(TypeError):
        renderer.render_frame(make_comp(), '1')
    with pytest.raises(ValueError):
        renderer.render_frame(make_comp(), -0.5)
    with pytest.raises(ValueError):
        renderer.render_frame(make_comp(), math.nan)


def test_write_png_round_trips(tmp_path):
    comp = make_comp(width=30, height=20)
    comp.add_layer(rect(position=Point(15, 10)))
    path = tmp_path / 'frame.png'
    render(comp).write_png(path)
    loaded = cairo.ImageSurface.create_from_png(str(path))
    assert (loaded.get_width(), loaded.get_height()) == (30, 20)
    assert RenderedFrame(loaded).pixel(15, 10) == RED_PX


def test_unsupported_layer_type_raises_render_error():
    class VideoLayer(Layer):
        layer_type = 'video'

    comp = make_comp()
    comp.add_layer(VideoLayer(name='Video'))
    with pytest.raises(RenderError, match='VideoLayer'):
        render(comp)


# --- Solid and shape layers ------------------------------------------------------------------

def test_solid_layer_covers_composition():
    comp = make_comp(width=20, height=10)
    comp.add_layer(SolidLayer(color=GREEN))
    frame = render(comp)
    assert all(frame.pixel(x, y) == GREEN_PX for y in range(10) for x in range(20))


def test_solid_layer_moves_with_position():
    comp = make_comp(width=20, height=10)
    comp.add_layer(SolidLayer(color=GREEN, position=Point(5, 0)))
    frame = render(comp)
    assert frame.pixel(4, 5) == BLACK_PX
    assert frame.pixel(5, 5) == GREEN_PX


def test_rectangle_fill_is_centered_on_position():
    comp = make_comp()
    comp.add_layer(rect(width=40, height=20, position=Point(50, 50)))
    frame = render(comp)
    assert bbox(frame) == (30, 40, 69, 59)
    assert frame.pixel(50, 50) == RED_PX
    assert frame.pixel(30, 40) == RED_PX
    assert frame.pixel(69, 59) == RED_PX


def test_rectangle_fill_then_stroke():
    comp = make_comp()
    comp.add_layer(ShapeLayer(shape_type='rectangle', width=40, height=20, fill_color=BLUE,
                              stroke_color=WHITE, stroke_width=4, position=Point(50, 50)))
    frame = render(comp)
    # The 4 px stroke is centered on the edge x = 30, covering x 28..31.
    assert bbox(frame) == (28, 38, 71, 61)
    assert frame.pixel(29, 50) == WHITE_PX
    assert frame.pixel(31, 50) == WHITE_PX
    assert frame.pixel(32, 50) == BLUE_PX
    assert frame.pixel(50, 50) == BLUE_PX


def test_rectangle_stroke_without_fill():
    comp = make_comp()
    comp.add_layer(ShapeLayer(shape_type='rectangle', width=40, height=20, fill_color=None,
                              stroke_color=WHITE, stroke_width=2, position=Point(50, 50)))
    frame = render(comp)
    assert frame.pixel(30, 50) == WHITE_PX
    assert frame.pixel(50, 50) == BLACK_PX


def test_zero_stroke_width_draws_no_stroke():
    comp = make_comp()
    comp.add_layer(ShapeLayer(shape_type='rectangle', width=40, height=20, fill_color=BLUE,
                              stroke_color=WHITE, stroke_width=0, position=Point(50, 50)))
    assert bbox(render(comp)) == (30, 40, 69, 59)


def test_ellipse_bounds_and_corners():
    comp = make_comp()
    comp.add_layer(ShapeLayer(shape_type='ellipse', width=60, height=30, fill_color=RED,
                              stroke_color=None, position=Point(50, 50)))
    frame = render(comp)
    assert_bbox_near(bbox(frame), (20, 35, 79, 64))
    assert frame.pixel(50, 50) == RED_PX
    assert frame.pixel(22, 50) == RED_PX
    # The bounding-box corners lie outside the ellipse.
    assert frame.pixel(21, 36) == BLACK_PX
    assert frame.pixel(78, 63) == BLACK_PX


def test_line_is_stroked_between_start_and_end():
    comp = make_comp()
    comp.add_layer(ShapeLayer(shape_type='line', start=Point(-30, 0), end=Point(30, 0),
                              fill_color=RED, stroke_color=WHITE, stroke_width=4,
                              position=Point(50, 50)))
    frame = render(comp)
    assert bbox(frame) == (20, 48, 79, 51)
    assert frame.pixel(50, 48) == WHITE_PX
    assert frame.pixel(50, 51) == WHITE_PX
    assert frame.pixel(50, 47) == BLACK_PX
    assert frame.pixel(19, 50) == BLACK_PX
    assert frame.pixel(80, 50) == BLACK_PX


def test_line_without_stroke_draws_nothing():
    comp = make_comp()
    comp.add_layer(ShapeLayer(shape_type='line', fill_color=RED, stroke_color=None,
                              position=Point(10, 50)))
    assert bbox(render(comp)) is None


def test_stroke_width_scales_with_layer():
    comp = make_comp()
    comp.add_layer(ShapeLayer(shape_type='line', start=Point(-20, 0), end=Point(20, 0),
                              stroke_color=WHITE, stroke_width=2, position=Point(50, 50),
                              scale=Scale(100, 300)))
    assert bbox(render(comp)) == (30, 47, 69, 52)


# --- Text layers ------------------------------------------------------------------------------

def text_comp(**kwargs):
    comp = make_comp(width=200, height=100)
    options = dict(text='Hi', font_family='Sans', font_size=40, color=WHITE,
                   position=Point(20, 60))
    options.update(kwargs)
    comp.add_layer(TextLayer(**options))
    return comp


def test_text_appears_in_text_color_near_baseline():
    frame = render(text_comp())
    box = bbox(frame)
    assert box is not None
    x0, y0, x1, y1 = box
    # Left aligned from x = 20; glyphs sit on the baseline at y = 60.
    assert 18 <= x0 <= 26
    assert x1 > x0 + 10
    assert y0 < 60 - 15
    assert 57 <= y1 <= 61
    assert any(frame.pixel(x, y) == WHITE_PX
               for y in range(y0, y1 + 1) for x in range(x0, x1 + 1))


def test_text_moves_with_position():
    box = bbox(render(text_comp()))
    moved = bbox(render(text_comp(position=Point(50, 70))))
    assert moved == (box[0] + 30, box[1] + 10, box[2] + 30, box[3] + 10)


def test_text_changes_with_content():
    short = render(text_comp(text='Hi'))
    long = render(text_comp(text='Hi there'))
    assert frame_bytes(short) != frame_bytes(long)
    assert bbox(long)[2] > bbox(short)[2] + 20


def test_text_changes_with_font_size():
    small = bbox(render(text_comp(font_size=20)))
    large = bbox(render(text_comp(font_size=40)))
    assert (large[3] - large[1]) > (small[3] - small[1]) * 1.5


def test_text_alignment_anchors_logical_extents():
    left = bbox(render(text_comp(alignment='left', position=Point(100, 60))))
    center = bbox(render(text_comp(alignment='center', position=Point(100, 60))))
    right = bbox(render(text_comp(alignment='right', position=Point(100, 60))))
    assert left[0] >= 98
    assert right[2] <= 102
    assert center[0] < 100 < center[2]
    assert abs((center[0] + center[2]) / 2 - 100) <= 3


def test_empty_text_draws_nothing():
    assert bbox(render(text_comp(text=''))) is None


# --- Image layers -----------------------------------------------------------------------------

def test_png_image_draws_at_natural_size(tmp_path):
    comp = make_comp()
    comp.add_layer(ImageLayer(path=red_blue_png(tmp_path / 'img.png'), position=Point(20, 30)))
    frame = render(comp)
    assert bbox(frame) == (20, 30, 29, 35)
    assert frame.pixel(20, 30) == RED_PX
    assert frame.pixel(24, 35) == RED_PX
    assert frame.pixel(25, 30) == BLUE_PX
    assert frame.pixel(29, 35) == BLUE_PX


def test_png_image_with_alpha_composites_over_background(tmp_path):
    def paint(ctx):
        ctx.set_source_rgba(1, 1, 1, 0.5)
        ctx.paint()
    path = tmp_path / 'half.png'
    write_png(path, 4, 4, paint)
    comp = make_comp(background=BLUE)
    comp.add_layer(ImageLayer(path=str(path), position=Point(10, 10)))
    assert_pixel_near(render(comp).pixel(11, 11), (128, 128, 255, 255), tolerance=1)


def test_jpeg_image_draws(tmp_path):
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 16, 16)
    pixbuf.fill(0x00FF00FF)
    path = tmp_path / 'img.jpg'
    pixbuf.savev(str(path), 'jpeg', ['quality'], ['100'])
    comp = make_comp()
    comp.add_layer(ImageLayer(path=str(path), position=Point(40, 40)))
    frame = render(comp)
    assert_bbox_near(bbox(frame), (40, 40, 55, 55), tolerance=0)
    assert_pixel_near(frame.pixel(47, 47), GREEN_PX, tolerance=8)


def test_image_scales_with_bilinear_filtering(tmp_path):
    comp = make_comp()
    comp.add_layer(ImageLayer(path=red_blue_png(tmp_path / 'img.png'), position=Point(20, 30),
                              scale=Scale(400, 400)))
    frame = render(comp)
    assert_bbox_near(bbox(frame), (20, 30, 59, 53))
    assert frame.pixel(25, 40) == RED_PX
    assert frame.pixel(55, 40) == BLUE_PX
    # Bilinear filtering blends across the red/blue boundary at x = 40.
    boundary = frame.pixel(40, 40)
    assert 0 < boundary.r < 255 and 0 < boundary.b < 255


def test_missing_image_raises_render_error_with_path(tmp_path):
    missing = str(tmp_path / 'nope.png')
    comp = make_comp()
    comp.add_layer(ImageLayer(path=missing))
    with pytest.raises(RenderError, match='nope.png'):
        render(comp)


def test_invalid_image_raises_render_error(tmp_path):
    path = tmp_path / 'bad.png'
    path.write_bytes(b'not an image')
    comp = make_comp()
    comp.add_layer(ImageLayer(path=str(path)))
    with pytest.raises(RenderError, match='bad.png'):
        render(comp)


def test_images_are_cached_per_renderer_by_resolved_path(tmp_path):
    path = tmp_path / 'img.png'
    red_blue_png(path)
    os.symlink(path, tmp_path / 'link.png')
    comp = make_comp()
    comp.add_layer(ImageLayer(path=str(path), position=Point(0, 0)))
    comp.add_layer(ImageLayer(path=str(tmp_path / 'link.png'), position=Point(50, 50)))
    renderer = CairoRenderer()
    first = renderer.render_frame(comp, 0.0)

    path.unlink()
    second = renderer.render_frame(comp, 0.0)
    assert frame_bytes(first) == frame_bytes(second)

    renderer.clear_image_cache()
    with pytest.raises(RenderError):
        renderer.render_frame(comp, 0.0)


# --- Transforms and opacity -------------------------------------------------------------------

def test_full_opacity_is_opaque():
    comp = make_comp()
    comp.add_layer(rect(color=WHITE, position=Point(50, 50), opacity=1.0))
    assert render(comp).pixel(50, 50) == WHITE_PX


def test_half_opacity_blends_with_background():
    comp = make_comp()
    comp.add_layer(rect(color=WHITE, position=Point(50, 50), opacity=0.5))
    assert_pixel_near(render(comp).pixel(50, 50), (128, 128, 128, 255), tolerance=1)


def test_zero_opacity_draws_nothing():
    comp = make_comp()
    comp.add_layer(rect(color=WHITE, position=Point(50, 50), opacity=0.0))
    assert bbox(render(comp)) is None


def test_opacity_applies_to_layer_as_a_whole():
    comp = make_comp()
    comp.add_layer(ShapeLayer(shape_type='rectangle', width=40, height=20, fill_color=BLUE,
                              stroke_color=RED, stroke_width=4, position=Point(50, 50),
                              opacity=0.5))
    # Where the stroke overlaps the fill, only the stroke shows, at half strength.
    assert_pixel_near(render(comp).pixel(31, 50), (128, 0, 0, 255), tolerance=1)


def test_opacity_on_transparent_background():
    comp = make_comp(background=Color(0.0, 0.0, 0.0, 0.0))
    comp.add_layer(rect(color=RED, position=Point(50, 50), opacity=0.5))
    assert_pixel_near(render(comp).pixel(50, 50), (128, 0, 0, 128), tolerance=1)


def test_translation_moves_shape():
    comp = make_comp()
    layer = rect(width=20, height=10, position=Point(30, 30))
    comp.add_layer(layer)
    assert bbox(render(comp)) == (20, 25, 39, 34)
    layer.position.base_value = Point(60, 70)
    assert bbox(render(comp)) == (50, 65, 69, 74)


def test_anchor_point_is_placed_at_position():
    comp = make_comp()
    comp.add_layer(rect(width=20, height=10, anchor_point=Point(-10, -5), position=Point(30, 30)))
    assert bbox(render(comp)) == (30, 30, 49, 39)


def test_scale_is_percent_around_anchor():
    comp = make_comp()
    comp.add_layer(rect(width=20, height=10, anchor_point=Point(-10, -5), position=Point(30, 30),
                        scale=Scale(200, 50)))
    assert bbox(render(comp)) == (30, 30, 69, 34)


def test_negative_scale_mirrors_around_anchor():
    comp = make_comp()
    comp.add_layer(rect(width=20, height=10, anchor_point=Point(-10, -5), position=Point(50, 50),
                        scale=Scale(-100, 100)))
    assert bbox(render(comp)) == (30, 50, 49, 59)


def test_zero_scale_draws_nothing():
    comp = make_comp()
    comp.add_layer(rect(position=Point(50, 50), scale=Scale(0, 100)))
    assert bbox(render(comp)) is None


@pytest.mark.parametrize('rotation, expected', [
    (0, (30, 30, 49, 39)),
    (90, (20, 30, 29, 49)),    # clockwise: +x maps to +y (down), +y maps to -x (left)
    (180, (10, 20, 29, 29)),
    (-90, (30, 10, 39, 29)),
    (270, (30, 10, 39, 29)),
])
def test_rotation_is_clockwise_degrees_around_anchor(rotation, expected):
    comp = make_comp()
    comp.add_layer(rect(width=20, height=10, anchor_point=Point(-10, -5), position=Point(30, 30),
                        rotation=rotation))
    assert_bbox_near(bbox(render(comp)), expected, tolerance=0)


def test_rotation_45_degrees():
    comp = make_comp()
    comp.add_layer(rect(width=20, height=20, position=Point(50, 50), rotation=45))
    frame = render(comp)
    half_diagonal = 10 * math.sqrt(2)
    assert_bbox_near(bbox(frame), (50 - half_diagonal, 50 - half_diagonal,
                                   50 + half_diagonal - 1, 50 + half_diagonal - 1))
    assert frame.pixel(50, 38) == RED_PX
    assert frame.pixel(39, 39) == BLACK_PX


def test_transform_applies_scale_before_rotation():
    comp = make_comp()
    comp.add_layer(rect(width=20, height=10, anchor_point=Point(-10, -5), position=Point(50, 50),
                        scale=Scale(200, 100), rotation=90))
    # Scaled to 40x10, then rotated: 10 wide, 40 tall, to the left of the anchor.
    assert bbox(render(comp)) == (40, 50, 49, 89)


# --- Animation ------------------------------------------------------------------------------

def animated_layer():
    layer = rect(width=20, height=10, anchor_point=Point(-10, -5))
    layer.position.set_keyframe(0.0, Point(20, 40), EASE_IN_OUT)
    layer.position.set_keyframe(2.0, Point(60, 40))
    layer.scale.set_keyframe(0.0, Scale(100, 100), EASE_OUT)
    layer.scale.set_keyframe(2.0, Scale(200, 150))
    layer.rotation.set_keyframe(0.0, 0.0)
    layer.rotation.set_keyframe(2.0, 90.0)
    layer.opacity.set_keyframe(0.0, 1.0)
    layer.opacity.set_keyframe(2.0, 0.5)
    return layer


def static_copy(layer, time):
    return rect(width=layer.width, height=layer.height, anchor_point=layer.anchor_point,
                position=layer.position.value_at(time), scale=layer.scale.value_at(time),
                rotation=layer.rotation.value_at(time), opacity=layer.opacity.value_at(time))


@pytest.mark.parametrize('time', [0.0, 0.5, 1.0, 1.5, 2.0, 3.0])
def test_animated_layer_matches_property_values(time):
    animated = make_comp()
    layer = animated_layer()
    animated.add_layer(layer)
    expected = make_comp()
    expected.add_layer(static_copy(layer, time))
    assert frame_bytes(render(animated, time)) == frame_bytes(render(expected, time))


def test_animated_rectangle_start_middle_end():
    comp = make_comp()
    layer = animated_layer()
    comp.add_layer(layer)

    assert bbox(render(comp, 0.0)) == (20, 40, 39, 49)

    middle = render(comp, 1.0)
    position = layer.position.value_at(1.0)
    assert position == Point(40, 40)
    opacity = layer.opacity.value_at(1.0)
    expected_red = round(255 * opacity)
    # Just right of and below the anchor lies inside the rotated rectangle.
    assert abs(middle.pixel(39, 42).r - expected_red) <= 1

    end = render(comp, 2.0)
    # 40x15 after scaling, rotated 90 degrees clockwise around the anchor (60, 40).
    assert_bbox_near(bbox(end), (45, 40, 59, 79), tolerance=0)
    assert_pixel_near(end.pixel(52, 60), (128, 0, 0, 255), tolerance=1)


# --- Layer order, visibility, determinism and purity -----------------------------------------

def test_layers_draw_bottom_to_top():
    comp = make_comp()
    comp.add_layer(rect(width=40, height=40, color=RED, position=Point(40, 50)))
    comp.add_layer(rect(width=40, height=40, color=BLUE, position=Point(60, 50)))
    frame = render(comp)
    assert frame.pixel(30, 50) == RED_PX
    assert frame.pixel(50, 50) == BLUE_PX
    assert frame.pixel(70, 50) == BLUE_PX

    comp.move_layer(comp.layers[1].id, 0)
    assert render(comp).pixel(50, 50) == RED_PX


def test_invisible_layers_are_skipped():
    comp = make_comp()
    bottom = rect(width=40, height=40, color=RED, position=Point(50, 50))
    top = rect(width=40, height=40, color=BLUE, position=Point(50, 50))
    comp.add_layer(bottom)
    comp.add_layer(top)
    top.visible = False
    assert render(comp).pixel(50, 50) == RED_PX
    bottom.visible = False
    assert bbox(render(comp)) is None


def test_invisible_missing_image_is_not_loaded(tmp_path):
    comp = make_comp()
    comp.add_layer(ImageLayer(path=str(tmp_path / 'missing.png'), visible=False))
    assert bbox(render(comp)) is None


def test_layer_state_does_not_leak_between_layers():
    comp = make_comp()
    comp.add_layer(rect(position=Point(50, 50), rotation=33, scale=Scale(300, 50), opacity=0.3))
    comp.add_layer(rect(width=10, height=10, color=GREEN, anchor_point=Point(-5, -5)))
    frame = render(comp)
    assert frame.pixel(0, 0) == GREEN_PX
    assert frame.pixel(9, 9) == GREEN_PX
    assert frame.pixel(10, 10) == BLACK_PX


def build_mixed_comp(tmp_path):
    comp = make_comp(width=160, height=120, background=Color(0.1, 0.2, 0.3, 1.0))
    comp.add_layer(SolidLayer(color=Color(0.0, 0.0, 0.0, 0.5), position=Point(80, 0)))
    layer = animated_layer()
    comp.add_layer(layer)
    comp.add_layer(ShapeLayer(shape_type='ellipse', width=50, height=30, fill_color=GREEN,
                              stroke_color=WHITE, stroke_width=3, position=Point(110, 80),
                              rotation=20))
    comp.add_layer(ShapeLayer(shape_type='line', start=Point(0, 0), end=Point(100, 30),
                              stroke_color=RED, stroke_width=2, position=Point(10, 10)))
    title = TextLayer(text='Mophic', font_size=24, alignment='center', position=Point(80, 110))
    title.opacity.set_keyframe(0.0, 0.0)
    title.opacity.set_keyframe(2.0, 1.0)
    comp.add_layer(title)
    comp.add_layer(ImageLayer(path=red_blue_png(tmp_path / 'img.png'), position=Point(140, 10),
                              rotation=15))
    return comp


def test_rendering_is_deterministic(tmp_path):
    comp = build_mixed_comp(tmp_path)
    renderer = CairoRenderer()
    first = frame_bytes(renderer.render_frame(comp, 1.25))
    assert frame_bytes(renderer.render_frame(comp, 1.25)) == first
    assert frame_bytes(CairoRenderer().render_frame(comp, 1.25)) == first
    assert frame_bytes(renderer.render_frame(comp, 0.25)) != first


def test_rendering_does_not_mutate_composition(tmp_path):
    comp = build_mixed_comp(tmp_path)
    project = Project(name='Render')
    project.add_composition(comp)
    before = project_to_dict(project)
    renderer = CairoRenderer()
    for time in (0.0, 1.0, 2.5, 10.0):
        renderer.render_frame(comp, time)
    assert project_to_dict(project) == before


def test_renderer_runs_without_gtk(tmp_path):
    script = textwrap.dedent(f'''
        import sys
        from core import Composition, ImageLayer, Point, ShapeLayer, TextLayer
        from core.renderer import CairoRenderer
        sys.path.insert(0, {os.path.join(PROJECT_ROOT, 'tests')!r})
        from test_renderer import red_blue_png
        comp = Composition(width=64, height=64)
        comp.add_layer(ShapeLayer(position=Point(32, 32)))
        comp.add_layer(TextLayer(text='Hi', font_size=20, position=Point(4, 40)))
        comp.add_layer(ImageLayer(path=red_blue_png({str(tmp_path / 'img.png')!r})))
        CairoRenderer().render_frame(comp, 0.0)
        loaded = sorted(name for name in sys.modules
                        if name.split('.')[-1] in {{'Gtk', 'Gdk', 'Adw', 'numpy', 'PIL'}})
        print(','.join(loaded))
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=PROJECT_ROOT,
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == ''


# --- Demonstration composition --------------------------------------------------------------

def test_demo_composition_renders(tmp_path):
    from examples import phase3_demo

    logo = tmp_path / 'logo.png'
    phase3_demo.write_logo(logo)
    comp = phase3_demo.build_demo_composition(str(logo))
    assert (comp.width, comp.height, comp.fps, comp.duration) == (1920, 1080, 30.0, 5.0)
    names = [layer.name for layer in comp.layers]
    assert names[0] == 'Background'
    assert {'Title', 'Rectangle', 'Ellipse', 'Line', 'Highlight', 'Logo'} <= set(names)
    title = comp.layers[names.index('Title')]
    assert title.position.is_animated and title.opacity.is_animated
    assert comp.layers[names.index('Line')].scale.is_animated
    assert comp.layers[names.index('Highlight')].opacity.is_animated

    renderer = CairoRenderer()
    start = renderer.render_frame(comp, 0.0)
    frame = renderer.render_frame(comp, phase3_demo.RENDER_TIME)
    assert (frame.width, frame.height) == (1920, 1080)
    assert frame_bytes(frame) != frame_bytes(start)

    path = tmp_path / 'phase3-render.png'
    frame.write_png(path)
    loaded = cairo.ImageSurface.create_from_png(str(path))
    assert (loaded.get_width(), loaded.get_height()) == (1920, 1080)
