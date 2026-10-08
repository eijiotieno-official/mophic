# export_dialog.py
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

"""Export composition to MP4 dialog and worker thread."""

from __future__ import annotations

import threading
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from core.exporter import ExportCancelled, ExportError, export_composition, find_ffmpeg
from core.project import Composition
from core.renderer import CairoRenderer


class ExportDialog:
    """Modal export UI; runs FFmpeg encoding on a worker thread."""

    def __init__(self, parent: Gtk.Window, composition: Composition,
                 renderer: CairoRenderer, *, default_name: str = 'export.mp4') -> None:
        self._parent = parent
        self._composition = composition
        self._renderer = renderer
        self._default_name = default_name
        self._cancel = False
        self._thread: threading.Thread | None = None
        self._output: str | None = None

        self._dialog = Adw.Dialog()
        self._dialog.set_title(_('Export Video'))
        self._dialog.set_content_width(420)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_margin_top(18)
        box.set_margin_bottom(18)

        self._width = Gtk.SpinButton.new_with_range(16, 8192, 1)
        self._width.set_value(composition.width)
        self._height = Gtk.SpinButton.new_with_range(16, 8192, 1)
        self._height.set_value(composition.height)
        self._fps = Gtk.SpinButton.new_with_range(1, 240, 1)
        self._fps.set_digits(2)
        self._fps.set_value(composition.fps)

        def row(label, widget):
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            r.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            widget.set_hexpand(True)
            r.append(widget)
            box.append(r)

        row(_('Width'), self._width)
        row(_('Height'), self._height)
        row(_('FPS'), self._fps)

        self._progress = Gtk.ProgressBar(show_text=True, text=_('Ready'))
        box.append(self._progress)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                          halign=Gtk.Align.END)
        self._cancel_btn = Gtk.Button(label=_('Cancel'))
        self._export_btn = Gtk.Button(label=_('Export…'),
                                      css_classes=['suggested-action'])
        buttons.append(self._cancel_btn)
        buttons.append(self._export_btn)
        box.append(buttons)

        self._dialog.set_child(box)
        self._cancel_btn.connect('clicked', self._on_cancel_clicked)
        self._export_btn.connect('clicked', self._on_export_clicked)

        if find_ffmpeg() is None:
            self._progress.set_text(_('FFmpeg not found'))
            self._export_btn.set_sensitive(False)

    def present(self) -> None:
        self._dialog.present(self._parent)

    def _on_cancel_clicked(self, *_args) -> None:
        if self._thread and self._thread.is_alive():
            self._cancel = True
            self._progress.set_text(_('Cancelling…'))
            return
        self._dialog.close()

    def _on_export_clicked(self, *_args) -> None:
        dialog = Gtk.FileDialog(title=_('Export MP4'))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filt = Gtk.FileFilter(name=_('MP4 video'))
        filt.add_pattern('*.mp4')
        filters.append(filt)
        dialog.set_filters(filters)
        dialog.set_default_filter(filt)
        dialog.set_initial_name(self._default_name)

        def on_save(_d, result):
            try:
                file = dialog.save_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            path = file.get_path()
            if path and not path.lower().endswith('.mp4'):
                path = path + '.mp4'
            self._output = path
            self._start_export()

        dialog.save(self._parent, None, on_save)

    def _start_export(self) -> None:
        self._cancel = False
        self._export_btn.set_sensitive(False)
        self._width.set_sensitive(False)
        self._height.set_sensitive(False)
        self._fps.set_sensitive(False)
        self._progress.set_fraction(0)
        self._progress.set_text(_('Exporting…'))

        width = int(self._width.get_value())
        height = int(self._height.get_value())
        fps = float(self._fps.get_value())
        path = self._output
        composition = self._composition
        renderer = self._renderer

        def worker():
            try:
                export_composition(
                    composition,
                    path,
                    width=width,
                    height=height,
                    fps=fps,
                    renderer=renderer,
                    progress=lambda f: GLib.idle_add(self._set_progress, f),
                    cancel=lambda: self._cancel,
                )
            except ExportCancelled:
                GLib.idle_add(self._on_done, False, _('Export cancelled'))
            except ExportError as error:
                GLib.idle_add(self._on_done, False, str(error))
            else:
                GLib.idle_add(self._on_done, True, _('Export complete'))

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _set_progress(self, fraction: float) -> bool:
        self._progress.set_fraction(fraction)
        self._progress.set_text(_('Exporting… {:.0%}').format(fraction))
        return False

    def _on_done(self, ok: bool, message: str) -> bool:
        self._progress.set_text(message)
        self._export_btn.set_sensitive(True)
        self._width.set_sensitive(True)
        self._height.set_sensitive(True)
        self._fps.set_sensitive(True)
        if ok:
            toast = Adw.Toast.new(message)
            if isinstance(self._parent, Adw.ApplicationWindow):
                overlay = getattr(self._parent, 'toast_overlay', None)
                if overlay is not None:
                    overlay.add_toast(toast)
            self._dialog.close()
        return False
