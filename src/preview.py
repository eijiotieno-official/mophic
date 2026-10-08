# preview.py
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

"""The composition preview: a Gtk.DrawingArea showing a rendered frame.

The frame is scaled to fit the widget, keeping its aspect ratio, and
centered; the rest of the widget is filled with a neutral dark color.
"""

from dataclasses import dataclass

import cairo
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from core.renderer import RenderedFrame

LETTERBOX_COLOR = (0.12, 0.12, 0.13)
"""RGB fill for the parts of the preview not covered by the frame."""


@dataclass(frozen=True)
class Fit:
    """Where a frame is drawn inside the preview, in widget coordinates."""

    x: float
    y: float
    width: float
    height: float
    scale: float


def fit_rect(content_width: float, content_height: float,
             area_width: float, area_height: float) -> Fit:
    """Fit content into an area, preserving aspect ratio and centering it.

    Returns a zero-sized fit if either size is empty.
    """
    if min(content_width, content_height, area_width, area_height) <= 0:
        return Fit(0.0, 0.0, 0.0, 0.0, 0.0)
    scale = min(area_width / content_width, area_height / content_height)
    width = content_width * scale
    height = content_height * scale
    return Fit((area_width - width) / 2, (area_height - height) / 2, width, height, scale)


def paint(ctx: cairo.Context, width: int, height: int, frame: RenderedFrame | None) -> None:
    """Draw ``frame`` fitted into a ``width`` x ``height`` area.

    Only draws on ``ctx``; it never modifies the frame.
    """
    ctx.save()
    ctx.set_source_rgb(*LETTERBOX_COLOR)
    ctx.paint()
    if frame is not None:
        fit = fit_rect(frame.width, frame.height, width, height)
        if fit.scale > 0:
            ctx.translate(fit.x, fit.y)
            ctx.scale(fit.scale, fit.scale)
            ctx.set_source_surface(frame.surface, 0, 0)
            pattern = ctx.get_source()
            pattern.set_filter(cairo.FILTER_BILINEAR)
            pattern.set_extend(cairo.EXTEND_PAD)
            ctx.rectangle(0, 0, frame.width, frame.height)
            ctx.fill()
    ctx.restore()


class FramePreview:
    """Shows the latest ``RenderedFrame`` in a ``Gtk.DrawingArea``."""

    def __init__(self, drawing_area: Gtk.DrawingArea) -> None:
        self._area = drawing_area
        self._frame: RenderedFrame | None = None
        drawing_area.set_draw_func(self._draw)

    @property
    def drawing_area(self) -> Gtk.DrawingArea:
        """The wrapped drawing area."""
        return self._area

    @property
    def frame(self) -> RenderedFrame | None:
        """The frame currently shown."""
        return self._frame

    def set_frame(self, frame: RenderedFrame | None) -> None:
        """Show ``frame`` and schedule a redraw. The frame must not be modified afterwards."""
        self._frame = frame
        self._area.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, ctx: cairo.Context, width: int, height: int) -> None:
        paint(ctx, width, height, self._frame)
