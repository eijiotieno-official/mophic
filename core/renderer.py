# renderer.py
#
# Copyright 2026 Eiji Otieno
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""CPU rendering of compositions with Cairo.

``CairoRenderer.render_frame(composition, time_seconds)`` draws one frame at
the composition's own resolution and returns a ``RenderedFrame``. It uses
Cairo for drawing, Pango for text and GdkPixbuf for decoding images. It
never imports GTK, GDK or libadwaita, so it runs in a plain ``python3``
process.

Rendering follows the conventions in ``core.layers``: the background is
painted first, then ``layers[0]`` (bottom) through ``layers[-1]`` (top).
Invisible layers, layers with zero opacity and layers with a zero scale
component draw nothing. Animated values come only from
``AnimatableProperty.value_at``.

Each layer draws in its own Cairo state with this transform, which maps a
local point ``p`` to composition pixels as
``position + rotate(scale * (p - anchor_point))``. Rotation is clockwise on
screen because Cairo's y axis points down. Strokes are drawn in local
coordinates, so scaling a layer also scales its stroke width.

Text: the first line's baseline sits at local y = 0. Horizontally, the
text's logical extents start at local x = 0 for ``left`` alignment, are
centered on 0 for ``center`` and end at 0 for ``right``. Hinting is
disabled and antialiasing is grayscale so text renders the same at any
position or scale.

Pixel format: frames are ``cairo.FORMAT_ARGB32`` image surfaces. Each
pixel is one 32-bit integer in the machine's native byte order, with alpha
in the top 8 bits followed by red, green and blue, and the color channels
are premultiplied by alpha. Rows are ``stride`` bytes apart, which may be
more than ``width * 4``.
"""

import io
import math
import os
import sys
from dataclasses import dataclass
from typing import NamedTuple, Protocol

import cairo
import gi

gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')

from gi.repository import GdkPixbuf, GLib, Pango, PangoCairo

from .layers import ImageLayer, Layer, ShapeLayer, SolidLayer, TextLayer
from .project import Composition
from .properties import Color, check_number

_PANGO_ALIGNMENTS = {
    'left': Pango.Alignment.LEFT,
    'center': Pango.Alignment.CENTER,
    'right': Pango.Alignment.RIGHT,
}


class RenderError(Exception):
    """Rendering failed, for example because an image could not be loaded."""


class Pixel(NamedTuple):
    """One pixel's 8-bit channels, premultiplied by alpha."""

    r: int
    g: int
    b: int
    a: int


@dataclass(frozen=True)
class RenderedFrame:
    """A rendered frame backed by a Cairo ``FORMAT_ARGB32`` image surface.

    See the module docstring for the memory layout of ``surface``.
    """

    surface: cairo.ImageSurface

    @property
    def width(self) -> int:
        """Width in pixels."""
        return self.surface.get_width()

    @property
    def height(self) -> int:
        """Height in pixels."""
        return self.surface.get_height()

    @property
    def stride(self) -> int:
        """Bytes between the starts of consecutive rows."""
        return self.surface.get_stride()

    def pixel(self, x: int, y: int) -> Pixel:
        """Return the pixel at column ``x``, row ``y``.

        Decodes the native-endian ARGB32 word, so the channel order is the
        same on every machine. The color channels stay premultiplied by
        alpha; for opaque pixels they equal the straight color.
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f'pixel ({x}, {y}) is outside {self.width}x{self.height}')
        self.surface.flush()
        offset = y * self.stride + x * 4
        word = int.from_bytes(self.surface.get_data()[offset:offset + 4], sys.byteorder)
        return Pixel((word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF, (word >> 24) & 0xFF)

    def write_png(self, path: str | os.PathLike[str]) -> None:
        """Write the frame to a PNG file."""
        self.surface.write_to_png(os.fspath(path))


class Renderer(Protocol):
    """Anything that can turn a composition at a time into a frame."""

    def render_frame(self, composition: Composition, time_seconds: float) -> RenderedFrame:
        """Render ``composition`` at ``time_seconds``."""


class CairoRenderer:
    """Renders compositions on the CPU with Cairo.

    Decoded images are cached by resolved path for the renderer's lifetime;
    call ``clear_image_cache()`` after an image file changes on disk.

    Relative ImageLayer paths are resolved against ``base_directory`` when set
    (typically the project file's parent). Missing or unreadable images draw a
    soft ``Missing`` placeholder instead of raising ``RenderError``.
    """

    def __init__(self, *, base_directory: str | os.PathLike[str] | None = None) -> None:
        self._images: dict[str, cairo.ImageSurface] = {}
        self._base_directory = os.fspath(base_directory) if base_directory else None
        self._font_options = cairo.FontOptions()
        self._font_options.set_antialias(cairo.ANTIALIAS_GRAY)
        self._font_options.set_hint_style(cairo.HINT_STYLE_NONE)
        self._font_options.set_hint_metrics(cairo.HINT_METRICS_OFF)

    @property
    def base_directory(self) -> str | None:
        """Directory used to resolve relative image paths."""
        return self._base_directory

    def set_base_directory(self, directory: str | os.PathLike[str] | None) -> None:
        """Set the project directory for relative image paths and clear the cache."""
        self._base_directory = os.fspath(directory) if directory else None
        self.clear_image_cache()

    def render_frame(self, composition: Composition, time_seconds: float) -> RenderedFrame:
        """Render ``composition`` at ``time_seconds`` (>= 0) into a new frame.

        The composition is only read, never modified.
        """
        if not isinstance(composition, Composition):
            raise TypeError(f'expected a Composition, got {type(composition).__name__}')
        time_seconds = check_number('time_seconds', time_seconds)
        if time_seconds < 0.0:
            raise ValueError(f'time_seconds must be >= 0, got {time_seconds!r}')

        surface = _create_surface(composition.width, composition.height)
        ctx = cairo.Context(surface)
        _paint_background(ctx, composition.background_color)
        for layer in composition.layers:
            if layer.visible:
                self._render_layer(ctx, layer, composition, time_seconds)
        surface.flush()
        return RenderedFrame(surface)

    def clear_image_cache(self) -> None:
        """Forget all decoded images."""
        self._images.clear()

    def _render_layer(self, ctx: cairo.Context, layer: Layer,
                      composition: Composition, time_seconds: float) -> None:
        if not isinstance(layer, (SolidLayer, ShapeLayer, TextLayer, ImageLayer)):
            raise RenderError(f'unsupported layer type {type(layer).__name__}')
        opacity = layer.opacity.value_at(time_seconds)
        if opacity <= 0.0:
            return
        image = self._load_image(layer.path) if isinstance(layer, ImageLayer) else None

        ctx.save()
        if _apply_transform(ctx, layer, time_seconds):
            if opacity < 1.0:
                ctx.push_group()
            self._draw_content(ctx, layer, composition, image)
            if opacity < 1.0:
                ctx.pop_group_to_source()
                ctx.paint_with_alpha(opacity)
        ctx.restore()

    def _draw_content(self, ctx: cairo.Context, layer: Layer, composition: Composition,
                      image: cairo.ImageSurface | None) -> None:
        if isinstance(layer, SolidLayer):
            _draw_solid(ctx, layer, composition)
        elif isinstance(layer, ShapeLayer):
            _draw_shape(ctx, layer)
        elif isinstance(layer, TextLayer):
            self._draw_text(ctx, layer)
        elif isinstance(layer, ImageLayer):
            _draw_image(ctx, image)

    def _draw_text(self, ctx: cairo.Context, layer: TextLayer) -> None:
        layout = PangoCairo.create_layout(ctx)
        PangoCairo.context_set_font_options(layout.get_context(), self._font_options)
        layout.context_changed()

        font = Pango.FontDescription()
        font.set_family(layer.font_family)
        font.set_absolute_size(layer.font_size * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_alignment(_PANGO_ALIGNMENTS[layer.alignment])
        layout.set_text(layer.text, -1)

        _ink, logical = layout.get_extents()
        left = logical.x / Pango.SCALE
        width = logical.width / Pango.SCALE
        if layer.alignment == 'left':
            x = -left
        elif layer.alignment == 'center':
            x = -(left + width / 2.0)
        else:
            x = -(left + width)
        baseline = layout.get_baseline() / Pango.SCALE

        _set_color(ctx, layer.color)
        ctx.move_to(x, -baseline)
        PangoCairo.show_layout(ctx, layout)

    def _resolve_image_path(self, path: str) -> str:
        if os.path.isabs(path) or self._base_directory is None:
            return path
        return os.path.normpath(os.path.join(self._base_directory, path))

    def _load_image(self, path: str) -> cairo.ImageSurface:
        resolved = self._resolve_image_path(path)
        try:
            key = os.path.realpath(resolved)
        except OSError:
            key = resolved
        image = self._images.get(key)
        if image is None:
            try:
                image = _decode_image(path, key)
            except RenderError:
                image = _missing_image_placeholder()
            self._images[key] = image
        return image


def _create_surface(width: int, height: int) -> cairo.ImageSurface:
    try:
        return cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    except cairo.Error as error:
        raise RenderError(f'could not create a {width}x{height} image surface: {error}') from error


def _set_color(ctx: cairo.Context, color: Color) -> None:
    ctx.set_source_rgba(color.r, color.g, color.b, color.a)


def _paint_background(ctx: cairo.Context, color: Color) -> None:
    ctx.save()
    ctx.set_operator(cairo.OPERATOR_SOURCE)
    _set_color(ctx, color)
    ctx.paint()
    ctx.restore()


def _apply_transform(ctx: cairo.Context, layer: Layer, time_seconds: float) -> bool:
    """Set up the layer transform. Returns ``False`` if the layer has zero scale.

    Each Cairo call below transforms user space, so the calls apply to a
    point in reverse order: subtract the anchor, scale, rotate, then move to
    the position.
    """
    position = layer.position.value_at(time_seconds)
    scale = layer.scale.value_at(time_seconds)
    rotation = layer.rotation.value_at(time_seconds)
    scale_x, scale_y = scale.x / 100.0, scale.y / 100.0
    if scale_x == 0.0 or scale_y == 0.0:
        return False

    anchor = layer.anchor_point
    ctx.translate(position.x, position.y)
    ctx.rotate(math.radians(rotation))
    ctx.scale(scale_x, scale_y)
    ctx.translate(-anchor.x, -anchor.y)
    return True


def _draw_solid(ctx: cairo.Context, layer: SolidLayer, composition: Composition) -> None:
    ctx.rectangle(0.0, 0.0, composition.width, composition.height)
    _set_color(ctx, layer.color)
    ctx.fill()


def _draw_shape(ctx: cairo.Context, layer: ShapeLayer) -> None:
    if layer.shape_type == 'line':
        ctx.move_to(layer.start.x, layer.start.y)
        ctx.line_to(layer.end.x, layer.end.y)
    elif layer.shape_type == 'rectangle':
        ctx.rectangle(-layer.width / 2.0, -layer.height / 2.0, layer.width, layer.height)
    else:
        ctx.save()
        ctx.scale(layer.width / 2.0, layer.height / 2.0)
        ctx.new_sub_path()
        ctx.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
        ctx.close_path()
        ctx.restore()

    if layer.fill_color is not None and layer.shape_type != 'line':
        _set_color(ctx, layer.fill_color)
        ctx.fill_preserve()
    if layer.stroke_color is not None and layer.stroke_width > 0.0:
        _set_color(ctx, layer.stroke_color)
        ctx.set_line_width(layer.stroke_width)
        ctx.stroke_preserve()
    ctx.new_path()


def _draw_image(ctx: cairo.Context, image: cairo.ImageSurface) -> None:
    ctx.set_source_surface(image, 0.0, 0.0)
    ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
    ctx.rectangle(0.0, 0.0, image.get_width(), image.get_height())
    ctx.fill()


_MISSING_PLACEHOLDER_SIZE = 200


def _missing_image_placeholder() -> cairo.ImageSurface:
    """A visible stand-in when an image file is missing or unreadable."""
    size = _MISSING_PLACEHOLDER_SIZE
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0.55, 0.15, 0.35)
    ctx.paint()
    ctx.set_source_rgb(0.95, 0.85, 0.90)
    ctx.set_line_width(4.0)
    ctx.rectangle(8, 8, size - 16, size - 16)
    ctx.stroke()
    ctx.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(28)
    text = 'Missing'
    extents = ctx.text_extents(text)
    ctx.move_to((size - extents.width) / 2 - extents.x_bearing,
                (size - extents.height) / 2 - extents.y_bearing)
    ctx.show_text(text)
    surface.flush()
    return surface


def _decode_image(path: str, resolved_path: str) -> cairo.ImageSurface:
    """Decode an image file with GdkPixbuf into a Cairo image surface.

    The pixbuf is re-encoded as an uncompressed PNG in memory and read back
    with Cairo, which converts it to premultiplied ARGB32 without a
    per-pixel Python loop.
    """
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(resolved_path)
        pixbuf = pixbuf.apply_embedded_orientation() or pixbuf
        _ok, png = pixbuf.save_to_bufferv('png', ['compression'], ['0'])
    except GLib.Error as error:
        raise RenderError(f'could not load image {path!r}: {error.message}') from error
    try:
        return cairo.ImageSurface.create_from_png(io.BytesIO(png))
    except cairo.Error as error:
        raise RenderError(f'could not convert image {path!r}: {error}') from error
