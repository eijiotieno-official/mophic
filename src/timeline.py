# timeline.py
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

"""Timeline widget: ruler, tracks, playhead, and keyframe diamonds."""

from __future__ import annotations

from collections.abc import Callable
from gettext import gettext as _

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')

from gi.repository import Gdk, Gtk

from core.layers import Layer
from core.properties import AnimatableProperty, TIME_EPSILON

from .timeline_geometry import (
    DEFAULT_PX_PER_SECOND,
    LABEL_WIDTH,
    RULER_HEIGHT,
    TRACK_HEIGHT,
    TRACK_LABELS,
    TRACK_NAMES,
    TimelineView,
    clamp_zoom,
    hit_test_keyframe,
    ruler_ticks,
    snap_time,
    time_to_x,
    timeline_height,
    track_y,
    x_to_time,
)


def _prop_for_track(layer: Layer, track: str) -> AnimatableProperty:
    return getattr(layer, track)


class TimelineWidget(Gtk.Box):
    """Keyframe timeline for the selected layer's transform properties."""

    def __init__(self, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, **kwargs)
        self.set_size_request(-1, 180)
        self.add_css_class('background')

        self._layer: Layer | None = None
        self._duration = 5.0
        self._fps = 30.0
        self._time = 0.0
        self._px_per_second = DEFAULT_PX_PER_SECOND
        self._scroll_x = 0.0
        self._selected: tuple[str, float] | None = None
        self._drag_mode: str | None = None  # 'playhead' | 'keyframe'
        self._drag_track: str | None = None
        self._drag_old_time: float | None = None
        self._drag_current_time: float | None = None

        self._on_seek: Callable[[float], None] | None = None
        self._on_move_keyframe: Callable[[str, float, float], None] | None = None
        self._on_remove_keyframe: Callable[[str, float], None] | None = None
        self._on_select_keyframe: Callable[[str | None, float | None], None] | None = None

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)
        toolbar.set_margin_top(4)
        zoom_label = Gtk.Label(label=_('Zoom'))
        zoom_label.add_css_class('dim-label')
        toolbar.append(zoom_label)
        self._zoom_adj = Gtk.Adjustment(
            value=DEFAULT_PX_PER_SECOND,
            lower=20.0,
            upper=400.0,
            step_increment=10.0,
            page_increment=40.0,
        )
        self._zoom = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                               adjustment=self._zoom_adj, hexpand=True)
        self._zoom.set_draw_value(False)
        self._zoom.set_tooltip_text(_('Pixels per second'))
        self._zoom.connect('value-changed', self._on_zoom_changed)
        toolbar.append(self._zoom)
        self.append(toolbar)

        self._empty = Gtk.Label(
            label=_('Select a layer to edit keyframes.'),
            wrap=True,
            justify=Gtk.Justification.CENTER,
            vexpand=True,
        )
        self._empty.add_css_class('dim-label')

        self._scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self._scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self._scrolled.set_min_content_height(int(timeline_height()))
        self._drawing = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self._drawing.set_content_height(int(timeline_height()))
        self._drawing.set_draw_func(self._draw)
        self._scrolled.set_child(self._drawing)
        hadj = self._scrolled.get_hadjustment()
        hadj.connect('value-changed', self._on_scroll_changed)

        self._stack = Gtk.Stack(vexpand=True, hexpand=True)
        self._stack.add_named(self._empty, 'empty')
        self._stack.add_named(self._scrolled, 'timeline')
        self._stack.set_visible_child_name('empty')
        self.append(self._stack)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect('pressed', self._on_pressed)
        click.connect('released', self._on_released)
        self._drawing.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect('drag-update', self._on_drag_update)
        drag.connect('drag-end', self._on_drag_end)
        self._drawing.add_controller(drag)

        key = Gtk.EventControllerKey()
        key.connect('key-pressed', self._on_key_pressed)
        self._drawing.add_controller(key)
        self._drawing.set_focusable(True)

    def connect_handlers(
        self,
        *,
        on_seek: Callable[[float], None],
        on_move_keyframe: Callable[[str, float, float], None],
        on_remove_keyframe: Callable[[str, float], None],
        on_select_keyframe: Callable[[str | None, float | None], None],
    ) -> None:
        self._on_seek = on_seek
        self._on_move_keyframe = on_move_keyframe
        self._on_remove_keyframe = on_remove_keyframe
        self._on_select_keyframe = on_select_keyframe

    def set_composition(self, duration: float, fps: float) -> None:
        self._duration = max(0.0, float(duration))
        self._fps = max(1.0, float(fps))
        self._queue_redraw()

    def set_layer(self, layer: Layer | None) -> None:
        self._layer = layer
        if layer is None:
            self._selected = None
            self._stack.set_visible_child_name('empty')
            if self._on_select_keyframe:
                self._on_select_keyframe(None, None)
        else:
            self._stack.set_visible_child_name('timeline')
        self._queue_redraw()

    def set_time(self, time_seconds: float) -> None:
        self._time = max(0.0, float(time_seconds))
        self._queue_redraw()

    @property
    def selected_keyframe(self) -> tuple[str, float] | None:
        return self._selected

    def clear_selection(self) -> None:
        self._selected = None
        if self._on_select_keyframe:
            self._on_select_keyframe(None, None)
        self._queue_redraw()

    def _view(self) -> TimelineView:
        width = max(self._drawing.get_width(), 1)
        return TimelineView(
            duration=self._duration,
            fps=self._fps,
            px_per_second=self._px_per_second,
            scroll_x=self._scroll_x,
            width=float(width),
        )

    def _track_times(self) -> dict[str, list[float]]:
        layer = self._layer
        if layer is None:
            return {name: [] for name in TRACK_NAMES}
        return {
            name: [kf.time for kf in _prop_for_track(layer, name).keyframes]
            for name in TRACK_NAMES
        }

    def _queue_redraw(self) -> None:
        view = self._view()
        self._drawing.set_content_width(int(view.content_width))
        self._drawing.queue_draw()

    def _on_zoom_changed(self, scale: Gtk.Scale) -> None:
        self._px_per_second = clamp_zoom(scale.get_value())
        self._queue_redraw()

    def _on_scroll_changed(self, adj: Gtk.Adjustment) -> None:
        self._scroll_x = adj.get_value()
        self._drawing.queue_draw()

    def _content_x(self, widget_x: float) -> float:
        return widget_x  # DrawingArea content coords already include scroll via content width

    def _on_pressed(self, _gesture, _n_press, x, y) -> None:
        self._drawing.grab_focus()
        view = self._view()
        cx = self._content_x(x)
        tracks = self._track_times()
        hit = hit_test_keyframe(cx, y, tracks, view)
        if hit is not None:
            self._selected = (hit.track, hit.time)
            self._drag_mode = 'keyframe'
            self._drag_track = hit.track
            self._drag_old_time = hit.time
            self._drag_current_time = hit.time
            if self._on_select_keyframe:
                self._on_select_keyframe(hit.track, hit.time)
            self._queue_redraw()
            return

        if y >= 0 and cx >= LABEL_WIDTH:
            time = snap_time(x_to_time(cx, view), self._fps, self._duration)
            self._drag_mode = 'playhead'
            self._selected = None
            if self._on_select_keyframe:
                self._on_select_keyframe(None, None)
            if self._on_seek:
                self._on_seek(time)
            self._queue_redraw()

    def _on_drag_update(self, gesture, offset_x, _offset_y) -> None:
        ok, start_x, _start_y = gesture.get_start_point()
        if not ok:
            return
        view = self._view()
        cx = self._content_x(start_x + offset_x)
        time = snap_time(x_to_time(cx, view), self._fps, self._duration)
        if self._drag_mode == 'playhead':
            if self._on_seek:
                self._on_seek(time)
        elif self._drag_mode == 'keyframe' and self._drag_track is not None:
            self._drag_current_time = time
            self._queue_redraw()

    def _on_drag_end(self, _gesture, _offset_x, _offset_y) -> None:
        if (self._drag_mode == 'keyframe'
                and self._drag_track is not None
                and self._drag_old_time is not None
                and self._drag_current_time is not None):
            old = self._drag_old_time
            new = self._drag_current_time
            track = self._drag_track
            if abs(new - old) > TIME_EPSILON and self._on_move_keyframe:
                try:
                    self._on_move_keyframe(track, old, new)
                    self._selected = (track, new)
                    if self._on_select_keyframe:
                        self._on_select_keyframe(track, new)
                except (ValueError, KeyError, TypeError):
                    self._selected = (track, old)
            else:
                self._selected = (track, old)
        self._drag_mode = None
        self._drag_track = None
        self._drag_old_time = None
        self._drag_current_time = None
        self._queue_redraw()

    def _on_released(self, *_args) -> None:
        pass

    def _on_key_pressed(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete, Gdk.KEY_BackSpace):
            if self._selected is not None and self._on_remove_keyframe:
                track, time = self._selected
                self._on_remove_keyframe(track, time)
                self._selected = None
                if self._on_select_keyframe:
                    self._on_select_keyframe(None, None)
                return True
        return False

    def _draw(self, _area, cr, width, height) -> None:
        view = TimelineView(
            duration=self._duration,
            fps=self._fps,
            px_per_second=self._px_per_second,
            scroll_x=self._scroll_x,
            width=float(width),
        )

        # Background
        cr.set_source_rgb(0.18, 0.18, 0.20)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Label gutter
        cr.set_source_rgb(0.14, 0.14, 0.16)
        cr.rectangle(0, 0, LABEL_WIDTH, height)
        cr.fill()

        # Ruler
        cr.set_source_rgb(0.22, 0.22, 0.24)
        cr.rectangle(0, 0, width, RULER_HEIGHT)
        cr.fill()
        cr.set_source_rgb(0.75, 0.75, 0.78)
        cr.select_font_face('Sans')
        cr.set_font_size(11)
        for t, label in ruler_ticks(view):
            x = time_to_x(t, view)
            cr.move_to(x, RULER_HEIGHT)
            cr.line_to(x, RULER_HEIGHT - 6)
            cr.stroke()
            cr.move_to(x + 3, 14)
            cr.show_text(label)

        # Track rows + labels
        for index, name in enumerate(TRACK_NAMES):
            y = track_y(index)
            if index % 2 == 0:
                cr.set_source_rgb(0.16, 0.16, 0.18)
            else:
                cr.set_source_rgb(0.15, 0.15, 0.17)
            cr.rectangle(LABEL_WIDTH, y, width - LABEL_WIDTH, TRACK_HEIGHT)
            cr.fill()
            cr.set_source_rgb(0.85, 0.85, 0.88)
            cr.move_to(8, y + TRACK_HEIGHT / 2 + 4)
            cr.show_text(TRACK_LABELS[name])

        # Duration end line
        end_x = time_to_x(self._duration, view)
        cr.set_source_rgba(1, 1, 1, 0.2)
        cr.move_to(end_x, RULER_HEIGHT)
        cr.line_to(end_x, height)
        cr.stroke()

        # Keyframes
        if self._layer is not None:
            for index, name in enumerate(TRACK_NAMES):
                prop = _prop_for_track(self._layer, name)
                cy = track_y(index) + TRACK_HEIGHT / 2.0
                for kf in prop.keyframes:
                    draw_time = kf.time
                    if (self._drag_mode == 'keyframe'
                            and self._drag_track == name
                            and self._drag_old_time is not None
                            and abs(kf.time - self._drag_old_time) <= TIME_EPSILON
                            and self._drag_current_time is not None):
                        draw_time = self._drag_current_time
                    kx = time_to_x(draw_time, view)
                    selected = (self._selected is not None
                                and self._selected[0] == name
                                and abs(self._selected[1] - kf.time) <= TIME_EPSILON)
                    self._draw_diamond(cr, kx, cy, selected=selected)

        # Playhead
        px = time_to_x(self._time, view)
        cr.set_source_rgb(0.95, 0.35, 0.25)
        cr.set_line_width(1.5)
        cr.move_to(px, 0)
        cr.line_to(px, height)
        cr.stroke()
        cr.move_to(px - 5, 0)
        cr.line_to(px + 5, 0)
        cr.line_to(px, 8)
        cr.close_path()
        cr.fill()

    @staticmethod
    def _draw_diamond(cr, x: float, y: float, *, selected: bool) -> None:
        size = 6.0
        if selected:
            cr.set_source_rgb(1.0, 0.85, 0.2)
        else:
            cr.set_source_rgb(0.55, 0.75, 1.0)
        cr.move_to(x, y - size)
        cr.line_to(x + size, y)
        cr.line_to(x, y + size)
        cr.line_to(x - size, y)
        cr.close_path()
        cr.fill()
        cr.set_source_rgb(0.1, 0.1, 0.12)
        cr.set_line_width(1.0)
        cr.move_to(x, y - size)
        cr.line_to(x + size, y)
        cr.line_to(x, y + size)
        cr.line_to(x - size, y)
        cr.close_path()
        cr.stroke()
