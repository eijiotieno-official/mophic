# window.py
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

import logging
from gettext import gettext as _

from gi.repository import Adw
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from core import Composition
from core.renderer import CairoRenderer, RenderError
from examples.demo_project import build_demo_composition

from .playback import FrameCache, PlaybackController, format_time
from .preview import FramePreview

logger = logging.getLogger(__name__)


@Gtk.Template(resource_path='/io/github/eijiotieno/Mophic/window.ui')
class MophicWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'MophicWindow'

    toast_overlay = Gtk.Template.Child()
    preview_area = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    time_scale = Gtk.Template.Child()
    time_adjustment = Gtk.Template.Child()
    time_label = Gtk.Template.Child()

    def __init__(self, composition: Composition | None = None, **kwargs):
        super().__init__(**kwargs)
        if composition is None:
            composition = build_demo_composition()
        self.composition = composition
        self.preview = FramePreview(self.preview_area)
        self.frames = FrameCache(CairoRenderer(), composition)
        self.playback = PlaybackController(composition, self.preview_area, self._refresh)
        self._failed_time: float | None = None

        self._add_actions()
        self.time_adjustment.configure(0.0, 0.0, composition.duration,
                                       1.0 / composition.fps, 1.0, 0.0)
        self.time_scale.set_sensitive(self.playback.can_play)
        self.time_scale.connect('change-value', self._on_time_scale_change_value)
        self.connect('close-request', self._on_close_request)
        self._refresh()

    def _add_actions(self):
        play_pause = Gio.SimpleAction.new('play-pause', None)
        play_pause.connect('activate', lambda *_: self.playback.toggle_play())
        play_pause.set_enabled(self.playback.can_play)
        self.add_action(play_pause)

        stop = Gio.SimpleAction.new('stop', None)
        stop.connect('activate', lambda *_: self.playback.stop())
        self.add_action(stop)

        loop = Gio.SimpleAction.new_stateful('loop', None, GLib.Variant.new_boolean(False))
        loop.connect('change-state', self._on_loop_change_state)
        self.add_action(loop)

    def _on_loop_change_state(self, action, value):
        action.set_state(value)
        self.playback.set_loop(value.get_boolean())

    def _on_time_scale_change_value(self, _scale, _scroll_type, value):
        self.playback.set_time(value)
        return True

    def _on_close_request(self, _window):
        self.playback.pause()
        return False

    def _refresh(self):
        """Show the frame and controls for the playback controller's current state."""
        playback = self.playback
        frame_time = playback.frame_time
        try:
            frame = self.frames.frame_at(frame_time)
        except RenderError as error:
            self._report_render_error(frame_time, error)
            playback.pause()
        else:
            self._failed_time = None
            if frame is not self.preview.frame:
                self.preview.set_frame(frame)

        time = playback.current_time
        self.time_adjustment.set_value(time)
        self.time_label.set_label(
            f'{format_time(time)} / {format_time(self.composition.duration)}')
        if playback.is_playing:
            self.play_button.set_icon_name('media-playback-pause-symbolic')
            self.play_button.set_tooltip_text(_('Pause'))
        else:
            self.play_button.set_icon_name('media-playback-start-symbolic')
            self.play_button.set_tooltip_text(_('Play'))

    def _report_render_error(self, frame_time, error):
        if self._failed_time == frame_time:
            return
        self._failed_time = frame_time
        logger.error('Could not render the frame at %.3f s: %s', frame_time, error)
        self.toast_overlay.add_toast(Adw.Toast.new(_('Could not render the preview: {}').format(error)))
