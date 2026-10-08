"""Playback controller tests. No GTK; fake tick widget and fixed timestamps."""

import pytest

from core import Color, Composition
from core.renderer import CairoRenderer, RenderError
from mophic.playback import (
    FrameCache,
    PlaybackController,
    format_time,
    last_frame_time,
    time_for_elapsed,
)


class FakeClock:
    def __init__(self, frame_time_us: int) -> None:
        self._frame_time_us = frame_time_us

    def get_frame_time(self) -> int:
        return self._frame_time_us


class FakeTickWidget:
    def __init__(self) -> None:
        self.callbacks: dict[int, object] = {}
        self._next_id = 1

    def add_tick_callback(self, callback):
        tick_id = self._next_id
        self._next_id += 1
        self.callbacks[tick_id] = callback
        return tick_id

    def remove_tick_callback(self, tick_id: int) -> None:
        del self.callbacks[tick_id]

    @property
    def active_count(self) -> int:
        return len(self.callbacks)

    def fire(self, frame_time_us: int) -> bool:
        assert self.active_count == 1
        tick_id, callback = next(iter(self.callbacks.items()))
        keep = callback(self, FakeClock(frame_time_us))
        # GTK removes the callback itself when it returns False.
        if not keep:
            self.callbacks.pop(tick_id, None)
        return keep


def make_comp(duration=5.0, fps=30.0, width=40, height=20):
    return Composition(width=width, height=height, fps=fps, duration=duration,
                       background_color=Color(0, 0, 0, 1))


def make_controller(comp=None, on_changed=None):
    widget = FakeTickWidget()
    controller = PlaybackController(comp or make_comp(), widget, on_changed)
    return controller, widget


# --- format_time / time_for_elapsed ----------------------------------------------------------

@pytest.mark.parametrize('seconds, expected', [
    (0.0, '0:00.00'),
    (0.019, '0:00.01'),
    (0.02, '0:00.02'),
    (1.0, '0:01.00'),
    (2.5, '0:02.50'),
    (59.999, '0:59.99'),
    (60.0, '1:00.00'),
    (125.67, '2:05.67'),
])
def test_format_time(seconds, expected):
    assert format_time(seconds) == expected


def test_time_for_elapsed_no_loop_reaches_end():
    assert time_for_elapsed(0.0, 4.9, 5.0, 4.0 + 29 / 30, False) == (
        pytest.approx(4.9), False)
    end = last_frame_time(make_comp(duration=5.0, fps=30.0))
    time, reached = time_for_elapsed(0.0, 5.0, 5.0, end, False)
    assert reached is True
    assert time == end


def test_time_for_elapsed_loop_wraps():
    time, reached = time_for_elapsed(0.0, 5.5, 5.0, 4.9666, True)
    assert reached is False
    assert time == pytest.approx(0.5)


def test_time_for_elapsed_zero_duration():
    assert time_for_elapsed(0.0, 1.0, 0.0, 0.0, False) == (0.0, True)
    assert time_for_elapsed(0.0, 1.0, 0.0, 0.0, True) == (0.0, True)


# --- initial state ---------------------------------------------------------------------------

def test_initial_state():
    controller, widget = make_controller()
    assert controller.current_time == 0.0
    assert controller.is_playing is False
    assert controller.loop is False
    assert controller.can_play is True
    assert controller.frame_time == 0.0
    assert widget.active_count == 0


def test_zero_duration_cannot_play():
    controller, widget = make_controller(make_comp(duration=0.0))
    assert controller.can_play is False
    controller.play()
    assert controller.is_playing is False
    assert widget.active_count == 0


# --- play / pause / resume / stop ------------------------------------------------------------

def test_play_pause_resume_preserves_time():
    controller, widget = make_controller()
    changes = []
    controller._on_changed = lambda: changes.append(
        (controller.current_time, controller.is_playing))

    controller.play()
    assert controller.is_playing is True
    assert widget.active_count == 1
    assert widget.fire(1_000_000) is True  # origin tick
    assert widget.fire(1_500_000) is True  # +0.5 s
    assert controller.current_time == pytest.approx(0.5)

    controller.pause()
    assert controller.is_playing is False
    assert widget.active_count == 0
    paused_at = controller.current_time

    controller.play()
    assert controller.is_playing is True
    assert widget.active_count == 1
    assert widget.fire(10_000_000) is True
    assert widget.fire(10_250_000) is True
    assert controller.current_time == pytest.approx(paused_at + 0.25)


def test_stop_resets_to_zero():
    controller, widget = make_controller()
    controller.play()
    widget.fire(1_000_000)
    widget.fire(2_000_000)
    assert controller.current_time == pytest.approx(1.0)
    controller.stop()
    assert controller.current_time == 0.0
    assert controller.is_playing is False
    assert widget.active_count == 0


def test_toggle_play():
    controller, widget = make_controller()
    controller.toggle_play()
    assert controller.is_playing is True
    controller.toggle_play()
    assert controller.is_playing is False
    assert widget.active_count == 0


# --- seeking ---------------------------------------------------------------------------------

def test_seek_while_paused():
    controller, _widget = make_controller()
    controller.set_time(2.5)
    assert controller.current_time == pytest.approx(2.5)
    assert controller.frame_time == pytest.approx(2.5)
    controller.set_time(-1.0)
    assert controller.current_time == 0.0
    controller.set_time(100.0)
    assert controller.current_time == pytest.approx(controller.end_time)


def test_seek_while_playing_rebases():
    controller, widget = make_controller()
    controller.play()
    widget.fire(1_000_000)
    widget.fire(2_000_000)
    assert controller.current_time == pytest.approx(1.0)

    controller.set_time(3.0)
    assert controller.current_time == pytest.approx(3.0)
    assert controller.is_playing is True
    # Next tick after seek only records the new origin.
    assert widget.fire(5_000_000) is True
    assert controller.current_time == pytest.approx(3.0)
    assert widget.fire(5_500_000) is True
    assert controller.current_time == pytest.approx(3.5)


# --- loop and end ----------------------------------------------------------------------------

def test_end_without_loop_stops():
    controller, widget = make_controller(make_comp(duration=2.0, fps=10.0))
    controller.play()
    widget.fire(0)
    keep = widget.fire(2_000_000)  # exactly duration
    assert keep is False
    assert controller.is_playing is False
    assert controller.current_time == pytest.approx(controller.end_time)
    assert widget.active_count == 0


def test_loop_wraps_and_continues():
    controller, widget = make_controller(make_comp(duration=2.0, fps=10.0))
    controller.set_loop(True)
    controller.play()
    widget.fire(0)
    assert widget.fire(2_500_000) is True
    assert controller.is_playing is True
    assert controller.current_time == pytest.approx(0.5)


def test_play_from_end_without_loop_restarts():
    controller, widget = make_controller(make_comp(duration=2.0, fps=10.0))
    controller.set_time(controller.end_time)
    controller.play()
    assert controller.current_time == 0.0
    assert controller.is_playing is True
    widget.fire(0)
    widget.fire(500_000)
    assert controller.current_time == pytest.approx(0.5)


def test_play_from_end_with_loop_continues():
    controller, widget = make_controller(make_comp(duration=2.0, fps=10.0))
    controller.set_loop(True)
    controller.set_time(controller.end_time)
    controller.play()
    # With loop, parked at end does not force restart to 0.
    assert controller.current_time == pytest.approx(controller.end_time)
    widget.fire(0)
    widget.fire(200_000)
    assert controller.current_time == pytest.approx(
        (controller.end_time + 0.2) % 2.0)


# --- duration boundary / frame_time ----------------------------------------------------------

def test_frame_time_snaps_to_frame_start():
    controller, _widget = make_controller(make_comp(duration=5.0, fps=30.0))
    controller.set_time(1.0 / 30 + 0.01)
    assert controller.frame_time == pytest.approx(1.0 / 30)
    controller.set_time(controller.end_time)
    assert controller.frame_time == pytest.approx(controller.end_time)


def test_last_frame_time():
    comp = make_comp(duration=5.0, fps=30.0)
    assert last_frame_time(comp) == pytest.approx((comp.frame_count - 1) / 30.0)
    assert last_frame_time(make_comp(duration=0.0)) == 0.0


# --- tick invariant --------------------------------------------------------------------------

def test_tick_invariant_across_transitions():
    controller, widget = make_controller()
    for action in (
        controller.play,
        controller.play,
        controller.pause,
        controller.pause,
        controller.play,
        controller.stop,
        controller.play,
    ):
        action()
        if controller.is_playing:
            assert widget.active_count == 1
        else:
            assert widget.active_count == 0


def test_on_changed_notified():
    notifications = []
    controller, widget = make_controller(on_changed=lambda: notifications.append(True))
    controller.play()
    widget.fire(1_000_000)
    widget.fire(1_100_000)
    controller.pause()
    controller.set_time(1.0)
    controller.set_loop(True)
    controller.stop()
    assert len(notifications) >= 6


# --- FrameCache ------------------------------------------------------------------------------

class CountingRenderer:
    def __init__(self) -> None:
        self.calls = []
        self._inner = CairoRenderer()

    def render_frame(self, composition, time_seconds):
        self.calls.append(time_seconds)
        return self._inner.render_frame(composition, time_seconds)


def test_frame_cache_reuses_same_time():
    comp = make_comp()
    renderer = CountingRenderer()
    cache = FrameCache(renderer, comp)
    first = cache.frame_at(0.0)
    second = cache.frame_at(0.0)
    assert first is second
    assert renderer.calls == [0.0]
    third = cache.frame_at(1.0 / 30)
    assert third is not first
    assert renderer.calls == [0.0, 1.0 / 30]


def test_frame_cache_keeps_previous_on_error():
    class FailingRenderer:
        def __init__(self) -> None:
            self.n = 0
            self._inner = CairoRenderer()

        def render_frame(self, composition, time_seconds):
            self.n += 1
            if self.n == 2:
                raise RenderError('boom')
            return self._inner.render_frame(composition, time_seconds)

    comp = make_comp()
    renderer = FailingRenderer()
    cache = FrameCache(renderer, comp)
    good = cache.frame_at(0.0)
    with pytest.raises(RenderError):
        cache.frame_at(1.0)
    assert cache.frame is good
