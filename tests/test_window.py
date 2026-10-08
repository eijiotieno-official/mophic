"""GTK-level window tests. Skip when there is no display or glib-compile-resources."""

import pytest

from mophic.preview import fit_rect
from conftest import make_window, requires_display, small_comp


@requires_display
def test_frame_zero_at_startup(window_class, app):
    win = make_window(window_class, app)
    try:
        assert win.playback.current_time == 0.0
        assert win.playback.is_playing is False
        assert win.preview.frame is not None
        assert win.preview.frame.width == 64
        assert win.preview.frame.height == 36
        assert win.time_label.get_label().startswith('0:00.00')
        assert win.play_button.get_icon_name() == 'media-playback-start-symbolic'
    finally:
        win.destroy()


@requires_display
def test_demo_startup_selects_title_and_shows_panels(window_class, app):
    from examples.demo_project import build_demo_composition

    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        assert win.selected_layer() is not None
        assert win.selected_layer().name == 'Title'
        assert win.layer_list.get_parent() is not None
        assert win.properties.get_parent() is not None
        assert win.properties._stack.get_visible_child_name() == 'editor'  # noqa: SLF001
    finally:
        win.destroy()


@requires_display
def test_play_pause_stop_actions(window_class, app):
    win = make_window(window_class, app)
    try:
        win.activate_action('win.play-pause', None)
        assert win.playback.is_playing is True
        assert win.play_button.get_icon_name() == 'media-playback-pause-symbolic'

        assert win.playback.advance(1_000_000) is True
        assert win.playback.advance(1_500_000) is True
        assert win.playback.current_time == pytest.approx(0.5)
        assert win.time_label.get_label().startswith('0:00.50')

        win.activate_action('win.play-pause', None)
        assert win.playback.is_playing is False
        paused = win.playback.current_time

        win.activate_action('win.play-pause', None)
        assert win.playback.is_playing is True
        win.playback.advance(2_000_000)
        win.playback.advance(2_200_000)
        assert win.playback.current_time == pytest.approx(paused + 0.2)

        win.activate_action('win.stop', None)
        assert win.playback.is_playing is False
        assert win.playback.current_time == 0.0
        assert win.time_label.get_label().startswith('0:00.00')
        assert win.play_button.get_icon_name() == 'media-playback-start-symbolic'
    finally:
        win.destroy()


@requires_display
def test_loop_action(window_class, app):
    from gi.repository import GLib

    win = make_window(window_class, app)
    try:
        assert win.playback.loop is False
        win.change_action_state('loop', GLib.Variant.new_boolean(True))
        assert win.playback.loop is True
        win.change_action_state('loop', GLib.Variant.new_boolean(False))
        assert win.playback.loop is False
    finally:
        win.destroy()


@requires_display
def test_scale_seek_updates_preview(window_class, app):
    from gi.repository import Gtk

    win = make_window(window_class, app)
    try:
        first = win.preview.frame
        win.time_scale.emit('change-value', Gtk.ScrollType.JUMP, 1.0)
        assert win.playback.current_time == pytest.approx(1.0)
        assert win.preview.frame is not None
        assert win.preview.frame is not first
        assert '0:01.00' in win.time_label.get_label()
        assert win.time_adjustment.get_value() == pytest.approx(1.0)
    finally:
        win.destroy()


@requires_display
def test_seek_while_playing_continues(window_class, app):
    from gi.repository import Gtk

    win = make_window(window_class, app)
    try:
        win.activate_action('win.play-pause', None)
        win.playback.advance(1_000_000)
        win.playback.advance(1_200_000)
        win.time_scale.emit('change-value', Gtk.ScrollType.JUMP, 0.8)
        assert win.playback.is_playing is True
        assert win.playback.current_time == pytest.approx(0.8)
        win.playback.advance(5_000_000)
        win.playback.advance(5_300_000)
        assert win.playback.current_time == pytest.approx(1.1)
    finally:
        win.destroy()


@requires_display
def test_end_without_loop_stops_via_advance(window_class, app):
    win = make_window(window_class, app, composition=small_comp(duration=1.0, fps=10.0))
    try:
        win.activate_action('win.play-pause', None)
        win.playback.advance(0)
        keep = win.playback.advance(1_000_000)
        assert keep is False
        assert win.playback.is_playing is False
        assert win.playback.current_time == pytest.approx(win.playback.end_time)
        assert win.play_button.get_icon_name() == 'media-playback-start-symbolic'
    finally:
        win.destroy()


@requires_display
def test_preview_fit_from_allocation(window_class, app):
    from gi.repository import GLib

    win = make_window(window_class, app)
    try:
        win.present()
        got_size = False
        for _ in range(200):
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            width = win.preview_area.get_width()
            height = win.preview_area.get_height()
            if width > 1 and height > 1:
                got_size = True
                break
        if not got_size:
            pytest.skip('preview area never received an allocation')

        fit = fit_rect(win.composition.width, win.composition.height, width, height)
        assert fit.scale > 0
        assert abs(fit.width / fit.height - win.composition.width / win.composition.height) < 1e-6
        assert abs(fit.x - (width - fit.width) / 2) < 1e-6
        assert abs(fit.y - (height - fit.height) / 2) < 1e-6

        win.set_default_size(900, 700)
        resized = False
        for _ in range(200):
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            new_w = win.preview_area.get_width()
            new_h = win.preview_area.get_height()
            if (new_w, new_h) != (width, height) and new_w > 1 and new_h > 1:
                resized = True
                fit2 = fit_rect(win.composition.width, win.composition.height, new_w, new_h)
                assert fit2.scale > 0
                assert abs(fit2.width / fit2.height
                           - win.composition.width / win.composition.height) < 1e-6
                break
        if not resized:
            pytest.skip('compositor did not apply a window resize; fit checked on initial allocation only')
    finally:
        win.playback.pause()
        win.destroy()


@requires_display
def test_close_request_pauses_playback(window_class, app):
    win = make_window(window_class, app)
    try:
        win.activate_action('win.play-pause', None)
        assert win.playback.is_playing is True
        win.emit('close-request')
        assert win.playback.is_playing is False
    finally:
        win.destroy()
