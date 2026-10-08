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

from core import Color, Composition, Point, Scale
from core.commands import (AddLayerCommand, MoveLayerCommand, RemoveLayerCommand,
                           SetAttributeCommand, SetPropertyValueCommand, UndoStack)
from core.layers import ShapeLayer, SolidLayer, TextLayer
from core.renderer import CairoRenderer, RenderError
from examples.demo_project import build_demo_composition

from .layer_factory import FACTORIES
from .layer_list import LayerListPanel
from .playback import FrameCache, PlaybackController, format_time
from .preview import FramePreview
from .properties_panel import PropertiesPanel

logger = logging.getLogger(__name__)


@Gtk.Template(resource_path='/io/github/eijiotieno/Mophic/window.ui')
class MophicWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'MophicWindow'

    toast_overlay = Gtk.Template.Child()
    layers_host = Gtk.Template.Child()
    properties_host = Gtk.Template.Child()
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
        self.undo_stack = UndoStack()
        self._selected_id: str | None = None
        self._failed_time: float | None = None

        self.preview = FramePreview(self.preview_area)
        self.frames = FrameCache(CairoRenderer(), composition)
        self.playback = PlaybackController(composition, self.preview_area, self._refresh)

        self.layer_list = LayerListPanel(hexpand=True, vexpand=True)
        self.properties = PropertiesPanel(hexpand=True, vexpand=True)
        self.layers_host.append(self.layer_list)
        self.properties_host.append(self.properties)

        self.layer_list.connect_handlers(
            on_select=self._on_select_layer,
            on_visibility=self._on_visibility,
            on_add=self.add_layer_kind,
            on_delete=self.delete_selected,
            on_duplicate=self.duplicate_selected,
            on_move=self.move_selected,
            on_rename=self.rename_selected,
        )
        self.properties.connect_handlers(on_edit=self._on_property_edit)

        self._add_actions()
        self.time_adjustment.configure(0.0, 0.0, composition.duration,
                                       1.0 / composition.fps, 1.0, 0.0)
        self.time_scale.set_sensitive(self.playback.can_play)
        self.time_scale.connect('change-value', self._on_time_scale_change_value)
        self.connect('close-request', self._on_close_request)

        self._selected_id = self._initial_selection_id()
        self.layer_list.resync(composition, self._selected_id)
        self._bind_properties()
        self._refresh()

    def _initial_selection_id(self) -> str | None:
        for layer in self.composition.layers:
            if layer.name == 'Title':
                return layer.id
        if self.composition.layers:
            return self.composition.layers[-1].id
        return None

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

        add_layer = Gio.SimpleAction.new('add-layer', GLib.VariantType.new('s'))
        add_layer.connect('activate', self._on_add_layer_action)
        self.add_action(add_layer)

    def _on_add_layer_action(self, _action, parameter):
        if parameter is not None:
            self.add_layer_kind(parameter.get_string())

    def _on_loop_change_state(self, action, value):
        action.set_state(value)
        self.playback.set_loop(value.get_boolean())

    def _on_time_scale_change_value(self, _scale, _scroll_type, value):
        self.playback.set_time(value)
        return True

    def _on_close_request(self, _window):
        self.playback.pause()
        return False

    def selected_layer(self):
        if self._selected_id is None or not self.composition.has_layer(self._selected_id):
            return None
        return self.composition.get_layer(self._selected_id)

    def edit(self, command) -> bool:
        """Execute a core command, resync UI, and refresh the preview."""
        try:
            self.undo_stack.execute(command)
        except (TypeError, ValueError, AttributeError, KeyError) as error:
            logger.warning('Edit rejected: %s', error)
            self.toast_overlay.add_toast(
                Adw.Toast.new(_('Could not apply the change: {}').format(error)))
            self._resync_ui()
            return False
        self.frames.invalidate()
        self._resync_ui()
        self._refresh()
        return True

    def _resync_ui(self) -> None:
        if self._selected_id is not None and not self.composition.has_layer(self._selected_id):
            self._selected_id = None
        self.layer_list.resync(self.composition, self._selected_id)
        self._bind_properties()

    def _bind_properties(self) -> None:
        self.properties.bind(self.selected_layer(), self.playback.current_time)

    def _on_select_layer(self, layer_id: str | None) -> None:
        self._selected_id = layer_id
        self._bind_properties()

    def add_layer_kind(self, kind: str) -> None:
        factory = FACTORIES.get(kind)
        if factory is None:
            return
        layer = factory(self.composition)
        if self.edit(AddLayerCommand(self.composition, layer)):
            self._selected_id = layer.id
            self.layer_list.resync(self.composition, self._selected_id)
            self._bind_properties()

    def delete_selected(self) -> None:
        layer = self.selected_layer()
        if layer is None:
            return
        display = list(reversed(self.composition.layers))
        index = display.index(layer)
        neighbour = None
        if len(display) > 1:
            neighbour = display[index - 1] if index > 0 else display[index + 1]
        next_id = neighbour.id if neighbour is not None else None
        if self.edit(RemoveLayerCommand(self.composition, layer.id)):
            self._selected_id = next_id
            self.layer_list.resync(self.composition, self._selected_id)
            self._bind_properties()

    def duplicate_selected(self) -> None:
        layer = self.selected_layer()
        if layer is None:
            return
        clone = layer.duplicate()
        index = self.composition.index_of(layer.id) + 1
        if self.edit(AddLayerCommand(self.composition, clone, index)):
            self._selected_id = clone.id
            self.layer_list.resync(self.composition, self._selected_id)
            self._bind_properties()

    def move_selected(self, delta: int) -> None:
        """Move selection in display order. ``delta`` +1 is up (toward top)."""
        layer = self.selected_layer()
        if layer is None:
            return
        old_index = self.composition.index_of(layer.id)
        # Display is reversed: up increases composition index.
        new_index = old_index + delta
        if new_index < 0 or new_index >= len(self.composition.layers):
            return
        self.edit(MoveLayerCommand(self.composition, layer.id, new_index))

    def rename_selected(self, name: str) -> None:
        layer = self.selected_layer()
        if layer is None:
            return
        self.edit(SetAttributeCommand(layer, 'name', name))

    def _on_visibility(self, layer_id: str, visible: bool) -> None:
        if not self.composition.has_layer(layer_id):
            return
        layer = self.composition.get_layer(layer_id)
        if layer.visible == visible:
            return
        self.edit(SetAttributeCommand(layer, 'visible', visible))

    def _on_property_edit(self, field: str, value: object) -> None:
        layer = self.selected_layer()
        if layer is None:
            return
        try:
            command = self._command_for_field(layer, field, value)
        except (TypeError, ValueError) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(_('Could not apply the change: {}').format(error)))
            self._bind_properties()
            return
        if command is None:
            self._bind_properties()
            return
        self.edit(command)

    def _command_for_field(self, layer, field: str, value: object):
        time = self.playback.current_time
        if field == 'position_x':
            return self._point_command(layer.position, time, x=float(value))
        if field == 'position_y':
            return self._point_command(layer.position, time, y=float(value))
        if field == 'scale_x':
            return self._scale_command(layer.scale, time, x=float(value))
        if field == 'scale_y':
            return self._scale_command(layer.scale, time, y=float(value))
        if field == 'rotation':
            return self._anim_command(layer.rotation, float(value))
        if field == 'opacity':
            return self._anim_command(layer.opacity, float(value) / 100.0)
        if field == 'color' and isinstance(layer, SolidLayer):
            return SetAttributeCommand(layer, 'color', value)
        if field == 'text_color' and isinstance(layer, TextLayer):
            return SetAttributeCommand(layer, 'color', value)
        if field == 'fill_color' and isinstance(layer, ShapeLayer):
            color = value if isinstance(value, Color) and value.a > 0 else value
            return SetAttributeCommand(layer, 'fill_color', color)
        if field == 'stroke_color' and isinstance(layer, ShapeLayer):
            return SetAttributeCommand(layer, 'stroke_color', value)
        if field in {'width', 'height', 'stroke_width', 'shape_type', 'text',
                     'font_family', 'font_size', 'alignment'} and hasattr(layer, field):
            return SetAttributeCommand(layer, field, value)
        if field in {'start_x', 'start_y'} and isinstance(layer, ShapeLayer):
            start = layer.start
            point = Point(float(value) if field == 'start_x' else start.x,
                          float(value) if field == 'start_y' else start.y)
            return SetAttributeCommand(layer, 'start', point)
        if field in {'end_x', 'end_y'} and isinstance(layer, ShapeLayer):
            end = layer.end
            point = Point(float(value) if field == 'end_x' else end.x,
                          float(value) if field == 'end_y' else end.y)
            return SetAttributeCommand(layer, 'end', point)
        return None

    def _anim_command(self, prop, value):
        if prop.is_animated:
            return None
        return SetPropertyValueCommand(prop, value)

    def _point_command(self, prop, time: float, *, x=None, y=None):
        if prop.is_animated:
            return None
        current = prop.base_value
        return SetPropertyValueCommand(prop, Point(
            current.x if x is None else x,
            current.y if y is None else y,
        ))

    def _scale_command(self, prop, time: float, *, x=None, y=None):
        if prop.is_animated:
            return None
        current = prop.base_value
        return SetPropertyValueCommand(prop, Scale(
            current.x if x is None else x,
            current.y if y is None else y,
        ))

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

        # Keep animated property readouts aligned with the playhead.
        layer = self.selected_layer()
        if layer is not None and self._layer_has_animation(layer):
            self.properties.bind(layer, time)

    def _layer_has_animation(self, layer) -> bool:
        return any(prop.is_animated for prop in (
            layer.position, layer.scale, layer.rotation, layer.opacity))

    def _report_render_error(self, frame_time, error):
        if self._failed_time == frame_time:
            return
        self._failed_time = frame_time
        logger.error('Could not render the frame at %.3f s: %s', frame_time, error)
        self.toast_overlay.add_toast(
            Adw.Toast.new(_('Could not render the preview: {}').format(error)))
