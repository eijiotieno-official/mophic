# playback.py
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

"""Playback state for the preview: current time, play/pause, loop.

Nothing here imports GTK. The controller is driven by a widget's frame
clock through a duck-typed ``tick_widget`` (anything with
``add_tick_callback`` and ``remove_tick_callback``), so tests can drive it
with fake timestamps.

Times are in seconds. Valid composition time is ``0 <= t < duration``;
playback never goes past the start of the last frame unless it loops.
"""

import math
from collections.abc import Callable
from typing import Protocol

from core import Composition
from core.properties import check_number
from core.renderer import RenderedFrame, Renderer

MICROSECONDS = 1_000_000


class FrameClock(Protocol):
    """The part of ``Gdk.FrameClock`` the controller uses."""

    def get_frame_time(self) -> int:
        """Monotonic time of the current frame, in microseconds."""


class TickWidget(Protocol):
    """The part of ``Gtk.Widget`` the controller uses."""

    def add_tick_callback(self, callback: Callable[[object, FrameClock], bool]) -> int:
        """Register ``callback`` to run once per frame; return its ID."""

    def remove_tick_callback(self, tick_id: int) -> None:
        """Unregister a tick callback."""


def format_time(seconds: float) -> str:
    """Format seconds as ``M:SS.ss``, rounding down to whole hundredths."""
    centiseconds = max(0, math.floor(seconds * 100 + 1e-6))
    minutes, centiseconds = divmod(centiseconds, 6000)
    return f'{minutes}:{centiseconds // 100:02d}.{centiseconds % 100:02d}'


def last_frame_time(composition: Composition) -> float:
    """Start time of the composition's last frame, or 0 if it has none."""
    return composition.time_at_frame(max(composition.frame_count - 1, 0))


def time_for_elapsed(start_time: float, elapsed: float, duration: float,
                     end_time: float, loop: bool) -> tuple[float, bool]:
    """Return ``(time, reached_end)`` after playing ``elapsed`` seconds from ``start_time``.

    With ``loop`` the time wraps modulo ``duration``. Without it, reaching
    ``duration`` clamps to ``end_time`` (the last frame's start) and reports
    the end. A zero duration is always at its end.
    """
    if duration <= 0.0:
        return 0.0, True
    time = start_time + max(elapsed, 0.0)
    if loop:
        return time % duration, False
    if time >= duration:
        return end_time, True
    return min(time, end_time), False


class PlaybackController:
    """Current time and play/pause/loop state for one composition.

    ``is_playing`` is true exactly while one tick callback is registered on
    ``tick_widget``. ``on_changed`` is called after every change to the time
    or state.
    """

    def __init__(self, composition: Composition, tick_widget: TickWidget,
                 on_changed: Callable[[], None] | None = None) -> None:
        self._composition = composition
        self._tick_widget = tick_widget
        self._on_changed = on_changed
        self._current_time = 0.0
        self._loop = False
        self._tick_id: int | None = None
        self._origin_time = 0.0
        self._origin_frame_time: int | None = None
        self._last_frame_time: int | None = None

    @property
    def composition(self) -> Composition:
        """The composition being played. It is never modified."""
        return self._composition

    @property
    def current_time(self) -> float:
        """Current time in seconds."""
        return self._current_time

    @property
    def is_playing(self) -> bool:
        """Whether playback is running."""
        return self._tick_id is not None

    @property
    def loop(self) -> bool:
        """Whether playback wraps to the start at the end."""
        return self._loop

    @property
    def can_play(self) -> bool:
        """Whether the composition has any duration to play."""
        return self._composition.duration > 0.0

    @property
    def end_time(self) -> float:
        """The latest time playback or seeking can reach."""
        return last_frame_time(self._composition)

    @property
    def frame_time(self) -> float:
        """Start time of the frame containing ``current_time``; what gets rendered."""
        comp = self._composition
        index = min(comp.frame_at_time(self._current_time), max(comp.frame_count - 1, 0))
        return comp.time_at_frame(index)

    def play(self) -> None:
        """Start playing from the current time; from 0 if parked at the end without loop."""
        if self.is_playing or not self.can_play:
            return
        if not self._loop and self._current_time >= self.end_time:
            self._current_time = 0.0
        self._last_frame_time = None
        self._rebase()
        self._tick_id = self._tick_widget.add_tick_callback(self._on_tick)
        self._notify()

    def pause(self) -> None:
        """Stop playing and keep the current time."""
        if not self.is_playing:
            return
        self._remove_tick()
        self._notify()

    def toggle_play(self) -> None:
        """Pause if playing, otherwise play."""
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        """Stop playing and return to time 0."""
        if self.is_playing:
            self._remove_tick()
        self._current_time = 0.0
        self._notify()

    def set_time(self, time_seconds: float) -> None:
        """Seek to ``time_seconds``, clamped to ``[0, end_time]``.

        While playing, playback continues from the new time. The next tick
        records a fresh frame-clock origin so elapsed time restarts at zero.
        """
        time_seconds = check_number('time_seconds', time_seconds)
        self._current_time = min(max(time_seconds, 0.0), self.end_time)
        self._origin_time = self._current_time
        self._origin_frame_time = None
        self._notify()

    def set_loop(self, enabled: bool) -> None:
        """Turn looping on or off."""
        if not isinstance(enabled, bool):
            raise TypeError(f'enabled must be a bool, got {type(enabled).__name__}')
        if enabled == self._loop:
            return
        self._loop = enabled
        self._notify()

    def advance(self, frame_time_us: int) -> bool:
        """Update the time for a frame-clock timestamp in microseconds.

        Returns ``True`` to keep receiving ticks, ``False`` when playback has
        ended (the tick widget then drops the callback itself).
        """
        tick_id = self._tick_id
        if tick_id is None:
            return False
        self._last_frame_time = frame_time_us
        if self._origin_frame_time is None:
            self._origin_frame_time = frame_time_us
            return True
        elapsed = (frame_time_us - self._origin_frame_time) / MICROSECONDS
        self._current_time, reached_end = time_for_elapsed(
            self._origin_time, elapsed, self._composition.duration, self.end_time, self._loop)
        if reached_end:
            self._tick_id = None
        self._notify()
        # on_changed may have paused playback, which already removed this callback.
        return self._tick_id == tick_id

    def _on_tick(self, _widget: object, frame_clock: FrameClock) -> bool:
        return self.advance(frame_clock.get_frame_time())

    def _rebase(self) -> None:
        self._origin_time = self._current_time
        self._origin_frame_time = self._last_frame_time

    def _remove_tick(self) -> None:
        tick_id, self._tick_id = self._tick_id, None
        self._tick_widget.remove_tick_callback(tick_id)

    def _notify(self) -> None:
        if self._on_changed is not None:
            self._on_changed()


class FrameCache:
    """Renders frames, re-rendering only when the requested time changes."""

    def __init__(self, renderer: Renderer, composition: Composition) -> None:
        self._renderer = renderer
        self._composition = composition
        self._time: float | None = None
        self._frame: RenderedFrame | None = None

    @property
    def frame(self) -> RenderedFrame | None:
        """The most recently rendered frame."""
        return self._frame

    def invalidate(self) -> None:
        """Forget the cached frame so the next ``frame_at`` re-renders."""
        self._time = None
        self._frame = None

    def frame_at(self, time_seconds: float) -> RenderedFrame:
        """Return the frame at ``time_seconds``.

        Raises whatever the renderer raises; the previous frame is kept.
        """
        if self._frame is None or self._time != time_seconds:
            self._frame = self._renderer.render_frame(self._composition, time_seconds)
            self._time = time_seconds
        return self._frame
