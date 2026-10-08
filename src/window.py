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
from pathlib import Path

from gi.repository import Adw
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from core import Color, Composition, Point, Project, Scale
from core.commands import (
    AddLayerCommand,
    MoveKeyframeCommand,
    MoveLayerCommand,
    RemoveKeyframeCommand,
    RemoveLayerCommand,
    SetAttributeCommand,
    SetKeyframeCommand,
    SetKeyframeEasingCommand,
    SetPropertyValueCommand,
    UndoStack,
)
from core.easing import LINEAR, Easing
from core.layers import ImageLayer, ShapeLayer, SolidLayer, TextLayer
from core.renderer import CairoRenderer, RenderError
from core.serialization import ProjectFormatError
from examples.demo_project import build_demo_composition

from .document import DocumentController, ProjectSettings, demo_project_path
from .export_dialog import ExportDialog
from .layer_factory import FACTORIES, create_image_layer
from .layer_list import LayerListPanel
from .playback import FrameCache, PlaybackController, format_time, last_frame_time
from .preview import FramePreview
from .properties_panel import PropertiesPanel
from .timeline import TimelineWidget
from .timeline_geometry import snap_time

logger = logging.getLogger(__name__)


@Gtk.Template(resource_path='/io/github/eijiotieno/Mophic/window.ui')
class MophicWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'MophicWindow'

    toast_overlay = Gtk.Template.Child()
    layers_host = Gtk.Template.Child()
    properties_host = Gtk.Template.Child()
    preview_area = Gtk.Template.Child()
    timeline_host = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    time_scale = Gtk.Template.Child()
    time_adjustment = Gtk.Template.Child()
    time_label = Gtk.Template.Child()

    def __init__(self, composition: Composition | None = None, **kwargs):
        super().__init__(**kwargs)
        if composition is not None:
            project = Project(name=composition.name or 'Untitled')
            project.add_composition(composition)
            self.document = DocumentController(project=project)
        else:
            demo = demo_project_path()
            if demo is not None:
                try:
                    self.document = DocumentController()
                    self.document.open(demo)
                except (OSError, ProjectFormatError):
                    project = Project(name='Mophic Demo')
                    project.add_composition(build_demo_composition())
                    self.document = DocumentController(project=project)
            else:
                project = Project(name='Mophic Demo')
                project.add_composition(build_demo_composition())
                self.document = DocumentController(project=project)

        self.composition = self.document.composition
        self.undo_stack = UndoStack()
        self._selected_id: str | None = None
        self._failed_time: float | None = None
        self._selected_kf: tuple[str, float] | None = None
        self._quit_after_save = False

        base = self.document.path.parent if self.document.path else None
        self.preview = FramePreview(self.preview_area)
        self.renderer = CairoRenderer(base_directory=base)
        self.frames = FrameCache(self.renderer, self.composition)
        self.playback = PlaybackController(self.composition, self.preview_area, self._refresh)

        self.layer_list = LayerListPanel(hexpand=True, vexpand=True)
        self.properties = PropertiesPanel(hexpand=True, vexpand=True)
        self.timeline = TimelineWidget(hexpand=True, vexpand=True)
        self.layers_host.append(self.layer_list)
        self.properties_host.append(self.properties)
        self.timeline_host.append(self.timeline)

        self.layer_list.connect_handlers(
            on_select=self._on_select_layer,
            on_visibility=self._on_visibility,
            on_add=self.add_layer_kind,
            on_delete=self.delete_selected,
            on_duplicate=self.duplicate_selected,
            on_move=self.move_selected,
            on_rename=self.rename_selected,
        )
        self.properties.connect_handlers(
            on_edit=self._on_property_edit,
            resolve_image=self.document.resolve_path,
        )
        self.timeline.connect_handlers(
            on_seek=self._on_timeline_seek,
            on_move_keyframe=self._on_move_keyframe,
            on_remove_keyframe=self._on_remove_keyframe,
            on_select_keyframe=self._on_select_keyframe,
        )
        self.timeline.set_composition(self.composition.duration, self.composition.fps)

        self._add_actions()
        self.time_adjustment.configure(0.0, 0.0, self.composition.duration,
                                       1.0 / self.composition.fps, 1.0, 0.0)
        self.time_scale.set_sensitive(self.playback.can_play)
        self.time_scale.connect('change-value', self._on_time_scale_change_value)
        self.connect('close-request', self._on_close_request)

        self._selected_id = self._initial_selection_id()
        self.layer_list.resync(self.composition, self._selected_id)
        self._bind_properties()
        self._bind_timeline()
        self._update_title()
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

        for name, handler in (
            ('new', self._action_new),
            ('open', self._action_open),
            ('save', self._action_save),
            ('save-as', self._action_save_as),
            ('open-demo', self._action_open_demo),
            ('export', self._action_export),
            ('undo', self._action_undo),
            ('redo', self._action_redo),
            ('goto-start', self._action_goto_start),
            ('goto-end', self._action_goto_end),
            ('step-back', self._action_step_back),
            ('step-forward', self._action_step_forward),
            ('delete', self._action_delete),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', handler)
            self.add_action(action)
        self._update_history_actions()

    def _on_add_layer_action(self, _action, parameter):
        if parameter is not None:
            self.add_layer_kind(parameter.get_string())

    def _on_loop_change_state(self, action, value):
        action.set_state(value)
        self.playback.set_loop(value.get_boolean())

    def _on_time_scale_change_value(self, _scale, _scroll_type, value):
        self.playback.set_time(value)
        return True

    def _on_timeline_seek(self, time: float) -> None:
        snapped = snap_time(time, self.composition.fps, self.composition.duration)
        self.playback.set_time(snapped)

    def _on_close_request(self, _window):
        self.playback.pause()
        if self.document.is_dirty:
            self._confirm_discard(on_discard=self._force_close, on_save=self._save_then_quit)
            return True
        return False

    def _force_close(self) -> None:
        self.destroy()

    def _save_then_quit(self) -> None:
        self._quit_after_save = True
        self._action_save(None, None)

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
        self.document.note_edit()
        self.frames.invalidate()
        self._resync_ui()
        self._update_title()
        self._update_history_actions()
        self._refresh()
        return True

    def _update_history_actions(self) -> None:
        undo = self.lookup_action('undo')
        redo = self.lookup_action('redo')
        if undo is not None:
            undo.set_enabled(self.undo_stack.can_undo)
        if redo is not None:
            redo.set_enabled(self.undo_stack.can_redo)

    def _action_undo(self, *_args) -> None:
        if not self.undo_stack.can_undo:
            return
        try:
            self.undo_stack.undo()
        except IndexError:
            return
        self.document.note_undo()
        self.frames.invalidate()
        self._resync_ui()
        self._update_title()
        self._update_history_actions()
        self._refresh()

    def _action_redo(self, *_args) -> None:
        if not self.undo_stack.can_redo:
            return
        try:
            self.undo_stack.redo()
        except IndexError:
            return
        self.document.note_redo()
        self.frames.invalidate()
        self._resync_ui()
        self._update_title()
        self._update_history_actions()
        self._refresh()

    def _action_export(self, *_args) -> None:
        self.playback.pause()
        dialog = ExportDialog(
            self,
            self.composition,
            self.renderer,
            default_name=f'{self.document.display_name}.mp4',
        )
        dialog.present()

    def _action_goto_start(self, *_args) -> None:
        self.playback.set_time(0.0)

    def _action_goto_end(self, *_args) -> None:
        self.playback.set_time(last_frame_time(self.composition))

    def _action_step_back(self, *_args) -> None:
        step = 1.0 / max(self.composition.fps, 1e-9)
        self.playback.set_time(self.playback.current_time - step)

    def _action_step_forward(self, *_args) -> None:
        step = 1.0 / max(self.composition.fps, 1e-9)
        self.playback.set_time(self.playback.current_time + step)

    def _action_delete(self, *_args) -> None:
        self.delete_selected()

    def _adopt_document(self) -> None:
        """Wire UI to ``self.document`` after new/open."""
        self.playback.pause()
        self.composition = self.document.composition
        self.undo_stack.clear()
        self._selected_kf = None
        base = self.document.path.parent if self.document.path else None
        self.renderer.set_base_directory(base)
        self.frames.set_composition(self.composition)
        self.playback.set_composition(self.composition)
        self.time_adjustment.configure(0.0, 0.0, self.composition.duration,
                                       1.0 / max(self.composition.fps, 1e-9), 1.0, 0.0)
        play = self.lookup_action('play-pause')
        if play is not None:
            play.set_enabled(self.playback.can_play)
        self.time_scale.set_sensitive(self.playback.can_play)
        self._selected_id = self._initial_selection_id()
        self._resync_ui()
        self._update_title()
        self._update_history_actions()
        self._refresh()

    def _update_title(self) -> None:
        name = self.document.display_name
        dirty = ' •' if self.document.is_dirty else ''
        self.set_title(f'Mophic — {name}{dirty}')

    def _resync_ui(self) -> None:
        if self._selected_id is not None and not self.composition.has_layer(self._selected_id):
            self._selected_id = None
        self.layer_list.resync(self.composition, self._selected_id)
        self._bind_properties()
        self._bind_timeline()

    def _bind_properties(self) -> None:
        self.properties.bind(self.selected_layer(), self.playback.current_time)
        if self._selected_kf is not None:
            self.properties.set_selected_keyframe(*self._selected_kf)
        else:
            self.properties.set_selected_keyframe(None, None)

    def _bind_timeline(self) -> None:
        self.timeline.set_composition(self.composition.duration, self.composition.fps)
        self.timeline.set_layer(self.selected_layer())
        self.timeline.set_time(self.playback.current_time)

    def _on_select_layer(self, layer_id: str | None) -> None:
        self._selected_id = layer_id
        self._selected_kf = None
        self._bind_properties()
        self._bind_timeline()

    def _on_select_keyframe(self, track: str | None, time: float | None) -> None:
        if track is None or time is None:
            self._selected_kf = None
        else:
            self._selected_kf = (track, time)
        self.properties.set_selected_keyframe(track, time)

    def _on_move_keyframe(self, track: str, old_time: float, new_time: float) -> None:
        layer = self.selected_layer()
        if layer is None:
            return
        prop = getattr(layer, track)
        self.edit(MoveKeyframeCommand(prop, old_time, new_time))

    def _on_remove_keyframe(self, track: str, time: float) -> None:
        layer = self.selected_layer()
        if layer is None:
            return
        prop = getattr(layer, track)
        if self.edit(RemoveKeyframeCommand(prop, time)):
            self._selected_kf = None

    # --- File actions ------------------------------------------------------------------

    def _confirm_discard(self, *, on_discard, on_save) -> None:
        dialog = Adw.AlertDialog.new(
            _('Save changes?'),
            _('There are unsaved changes in “{}”.').format(self.document.display_name),
        )
        dialog.add_response('cancel', _('Cancel'))
        dialog.add_response('discard', _('Discard'))
        dialog.add_response('save', _('Save'))
        dialog.set_response_appearance('discard', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance('save', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('save')
        dialog.set_close_response('cancel')

        def on_response(_dialog, response):
            if response == 'discard':
                on_discard()
            elif response == 'save':
                on_save()

        dialog.connect('response', on_response)
        dialog.present(self)

    def _action_new(self, *_args) -> None:
        if self.document.is_dirty:
            self._confirm_discard(
                on_discard=self._show_new_project_dialog,
                on_save=lambda: self._save_then(self._show_new_project_dialog),
            )
            return
        self._show_new_project_dialog()

    def _show_new_project_dialog(self) -> None:
        dialog = Adw.Dialog()
        dialog.set_title(_('New Project'))
        dialog.set_content_width(420)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_margin_top(18)
        box.set_margin_bottom(18)

        name = Gtk.Entry(text='Untitled', placeholder_text=_('Name'))
        width = Gtk.SpinButton.new_with_range(16, 8192, 1)
        width.set_value(1920)
        height = Gtk.SpinButton.new_with_range(16, 8192, 1)
        height.set_value(1080)
        fps = Gtk.SpinButton.new_with_range(1, 240, 1)
        fps.set_digits(2)
        fps.set_value(30)
        duration = Gtk.SpinButton.new_with_range(0.1, 3600, 0.1)
        duration.set_digits(2)
        duration.set_value(5)
        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        rgba = color_btn.get_rgba()
        rgba.red = rgba.green = rgba.blue = 0.0
        rgba.alpha = 1.0
        color_btn.set_rgba(rgba)

        def row(label, widget):
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            r.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            widget.set_hexpand(True)
            r.append(widget)
            box.append(r)

        box.append(Gtk.Label(label=_('Name'), xalign=0))
        box.append(name)
        row(_('Width'), width)
        row(_('Height'), height)
        row(_('FPS'), fps)
        row(_('Duration (s)'), duration)
        row(_('Background'), color_btn)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=_('Cancel'))
        create = Gtk.Button(label=_('Create'), css_classes=['suggested-action'])
        buttons.append(cancel)
        buttons.append(create)
        box.append(buttons)
        dialog.set_child(box)

        cancel.connect('clicked', lambda *_: dialog.close())

        def on_create(*_a):
            rgba = color_btn.get_rgba()
            settings = ProjectSettings(
                name=name.get_text().strip() or 'Untitled',
                width=int(width.get_value()),
                height=int(height.get_value()),
                fps=float(fps.get_value()),
                duration=float(duration.get_value()),
                background_color=Color(rgba.red, rgba.green, rgba.blue, rgba.alpha),
            )
            self.document.new_project(settings)
            self._adopt_document()
            dialog.close()

        create.connect('clicked', on_create)
        dialog.present(self)

    def _action_open(self, *_args) -> None:
        if self.document.is_dirty:
            self._confirm_discard(
                on_discard=self._run_open_dialog,
                on_save=lambda: self._save_then(self._run_open_dialog),
            )
            return
        self._run_open_dialog()

    def _run_open_dialog(self) -> None:
        dialog = Gtk.FileDialog(title=_('Open Project'))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filt = Gtk.FileFilter(name=_('Mophic projects'))
        filt.add_pattern('*.aemvp')
        filters.append(filt)
        dialog.set_filters(filters)
        dialog.set_default_filter(filt)

        def on_open(_dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            try:
                self.document.open(file.get_path())
            except (OSError, ProjectFormatError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(_('Could not open project: {}').format(error)))
                return
            self._adopt_document()

        dialog.open(self, None, on_open)

    def _action_open_demo(self, *_args) -> None:
        def do_open():
            path = demo_project_path()
            if path is None:
                self.toast_overlay.add_toast(Adw.Toast.new(_('Demo project not found')))
                return
            try:
                self.document.open(path)
            except (OSError, ProjectFormatError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(_('Could not open demo: {}').format(error)))
                return
            self._adopt_document()

        if self.document.is_dirty:
            self._confirm_discard(
                on_discard=do_open,
                on_save=lambda: self._save_then(do_open),
            )
            return
        do_open()

    def _action_save(self, *_args) -> None:
        if self.document.path is None:
            self._action_save_as()
            return
        try:
            self.document.save()
        except OSError as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(_('Could not save: {}').format(error)))
            return
        self.renderer.set_base_directory(self.document.path.parent)
        self.frames.invalidate()
        self._update_title()
        self.toast_overlay.add_toast(Adw.Toast.new(_('Project saved')))
        if self._quit_after_save:
            self._quit_after_save = False
            self.destroy()

    def _action_save_as(self, *_args) -> None:
        dialog = Gtk.FileDialog(title=_('Save Project As'))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filt = Gtk.FileFilter(name=_('Mophic projects'))
        filt.add_pattern('*.aemvp')
        filters.append(filt)
        dialog.set_filters(filters)
        dialog.set_default_filter(filt)
        dialog.set_initial_name(f'{self.document.display_name}.aemvp')

        def on_save(_dialog, result):
            try:
                file = dialog.save_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            try:
                self.document.save_as(file.get_path())
            except OSError as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(_('Could not save: {}').format(error)))
                return
            self.renderer.set_base_directory(self.document.path.parent)
            self.frames.invalidate()
            self._update_title()
            self._bind_properties()
            self.toast_overlay.add_toast(Adw.Toast.new(_('Project saved')))
            if self._quit_after_save:
                self._quit_after_save = False
                self.destroy()

        dialog.save(self, None, on_save)

    def _save_then(self, continuation) -> None:
        if self.document.path is None:
            # Save As, then continue after — for simplicity call save-as and skip continuation
            # unless path already exists. User must save as first; then retry.
            self._pending_after_save = continuation
            self._action_save_as()
            return
        try:
            self.document.save()
        except OSError as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(_('Could not save: {}').format(error)))
            return
        self._update_title()
        continuation()

    def add_layer_kind(self, kind: str, *, image_path: str | None = None) -> None:
        if kind == 'image' and image_path is None:
            self._add_image_layer_dialog()
            return
        if kind == 'image':
            layer = create_image_layer(self.composition, path=image_path)
            self.document.import_image_for_layer(layer, image_path)
        else:
            factory = FACTORIES.get(kind)
            if factory is None:
                return
            layer = factory(self.composition)
        if self.edit(AddLayerCommand(self.composition, layer)):
            self._selected_id = layer.id
            self.layer_list.resync(self.composition, self._selected_id)
            self._bind_properties()
            self._bind_timeline()

    def _add_image_layer_dialog(self) -> None:
        dialog = Gtk.FileDialog(title=_('Add Image'))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filt = Gtk.FileFilter(name=_('Images'))
        for pattern in ('*.png', '*.jpg', '*.jpeg', '*.webp'):
            filt.add_pattern(pattern)
        filters.append(filt)
        dialog.set_filters(filters)
        dialog.set_default_filter(filt)

        def on_open(_dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            path = file.get_path()
            layer = create_image_layer(self.composition, path=path)
            self.document.import_image_for_layer(layer, path)
            if self.edit(AddLayerCommand(self.composition, layer)):
                self._selected_id = layer.id
                self.layer_list.resync(self.composition, self._selected_id)
                self._bind_properties()
                self._bind_timeline()

        dialog.open(self, None, on_open)

    def delete_selected(self) -> None:
        if self._selected_kf is not None:
            track, time = self._selected_kf
            self._on_remove_keyframe(track, time)
            return
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
            self._bind_timeline()

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
            self._bind_timeline()

    def move_selected(self, delta: int) -> None:
        """Move selection in display order. ``delta`` +1 is up (toward top)."""
        layer = self.selected_layer()
        if layer is None:
            return
        old_index = self.composition.index_of(layer.id)
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
        except (TypeError, ValueError, KeyError) as error:
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
        if field == 'toggle_keyframe':
            return self._toggle_keyframe_command(layer, str(value), time)
        if field == 'keyframe_easing':
            if self._selected_kf is None or not isinstance(value, Easing):
                return None
            track, kf_time = self._selected_kf
            return SetKeyframeEasingCommand(getattr(layer, track), kf_time, value)
        if field == 'position_x':
            return self._point_command(layer.position, time, x=float(value))
        if field == 'position_y':
            return self._point_command(layer.position, time, y=float(value))
        if field == 'scale_x':
            return self._scale_command(layer.scale, time, x=float(value))
        if field == 'scale_y':
            return self._scale_command(layer.scale, time, y=float(value))
        if field == 'rotation':
            return self._anim_command(layer.rotation, time, float(value))
        if field == 'opacity':
            return self._anim_command(layer.opacity, time, float(value) / 100.0)
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

    def _toggle_keyframe_command(self, layer, track: str, time: float):
        prop = getattr(layer, track)
        if prop.has_keyframe(time):
            return RemoveKeyframeCommand(prop, time)
        return SetKeyframeCommand(prop, time, prop.value_at(time), LINEAR)

    def _anim_command(self, prop, time: float, value):
        if prop.is_animated:
            easing = LINEAR
            existing = prop.get_keyframe(time)
            if existing is not None:
                easing = existing.easing
            return SetKeyframeCommand(prop, time, value, easing)
        return SetPropertyValueCommand(prop, value)

    def _point_command(self, prop, time: float, *, x=None, y=None):
        current = prop.value_at(time) if prop.is_animated else prop.base_value
        new_value = Point(
            current.x if x is None else x,
            current.y if y is None else y,
        )
        if prop.is_animated:
            easing = LINEAR
            existing = prop.get_keyframe(time)
            if existing is not None:
                easing = existing.easing
            return SetKeyframeCommand(prop, time, new_value, easing)
        return SetPropertyValueCommand(prop, new_value)

    def _scale_command(self, prop, time: float, *, x=None, y=None):
        current = prop.value_at(time) if prop.is_animated else prop.base_value
        new_value = Scale(
            current.x if x is None else x,
            current.y if y is None else y,
        )
        if prop.is_animated:
            easing = LINEAR
            existing = prop.get_keyframe(time)
            if existing is not None:
                easing = existing.easing
            return SetKeyframeCommand(prop, time, new_value, easing)
        return SetPropertyValueCommand(prop, new_value)

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
        self.timeline.set_time(time)
        if playback.is_playing:
            self.play_button.set_icon_name('media-playback-pause-symbolic')
            self.play_button.set_tooltip_text(_('Pause'))
        else:
            self.play_button.set_icon_name('media-playback-start-symbolic')
            self.play_button.set_tooltip_text(_('Play'))

        layer = self.selected_layer()
        if layer is not None and self._layer_has_animation(layer):
            self.properties.bind(layer, time)
            if self._selected_kf is not None:
                self.properties.set_selected_keyframe(*self._selected_kf)

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
