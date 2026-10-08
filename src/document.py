# document.py
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

"""Project document lifecycle: new/open/save, assets, dirty tracking."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from core import Color, Composition, ImageLayer, Project, load_project, save_project
from core.serialization import ProjectFormatError

ASSETS_SUFFIX = '.assets'
IMAGES_DIR = 'images'
DEMO_FILENAME = 'mophic-demo.aemvp'


def demo_project_path() -> Path | None:
    """Locate the installed or source-tree sample project, if present."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / 'examples' / DEMO_FILENAME,  # source tree
        here.parent.parent / DEMO_FILENAME,  # flat install layout
    ]
    # Installed: …/share/mophic/mophic/document.py → …/share/mophic/examples/
    share = here.parent.parent
    candidates.append(share / 'examples' / DEMO_FILENAME)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True)
class ProjectSettings:
    """Settings for a blank project."""

    name: str = 'Untitled'
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    duration: float = 5.0
    background_color: Color = Color(0.0, 0.0, 0.0, 1.0)


def assets_dir_for(project_path: Path) -> Path:
    """Return ``stem.assets`` next to ``project_path``."""
    return project_path.parent / f'{project_path.stem}{ASSETS_SUFFIX}'


def images_dir_for(project_path: Path) -> Path:
    return assets_dir_for(project_path) / IMAGES_DIR


def resolve_image_path(path: str, project_path: Path | None) -> Path:
    """Resolve an ImageLayer path to an absolute filesystem path."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if project_path is not None:
        return (project_path.parent / candidate).resolve()
    return candidate.resolve()


class DocumentController:
    """Owns the active project, path, and dirty/revision state."""

    def __init__(self, project: Project | None = None, path: Path | None = None) -> None:
        if project is None:
            project = self._blank_project(ProjectSettings())
        self.project = project
        self.path = Path(path) if path is not None else None
        self.history_revision = 0
        self.saved_revision = 0
        self._pending_imports: dict[str, Path] = {}  # layer_id -> absolute source

    @staticmethod
    def _blank_project(settings: ProjectSettings) -> Project:
        project = Project(name=settings.name)
        composition = Composition(
            name='Main',
            width=settings.width,
            height=settings.height,
            fps=settings.fps,
            duration=settings.duration,
            background_color=settings.background_color,
        )
        project.add_composition(composition)
        return project

    @property
    def composition(self) -> Composition:
        if not self.project.compositions:
            raise RuntimeError('project has no compositions')
        return self.project.compositions[0]

    @property
    def is_dirty(self) -> bool:
        return self.history_revision != self.saved_revision

    @property
    def display_name(self) -> str:
        if self.path is not None:
            return self.path.stem
        return self.project.name

    def note_edit(self) -> None:
        self.history_revision += 1

    def note_undo(self) -> None:
        self.history_revision = max(0, self.history_revision - 1)

    def note_redo(self) -> None:
        self.history_revision += 1

    def mark_clean(self) -> None:
        self.saved_revision = self.history_revision

    def new_project(self, settings: ProjectSettings | None = None) -> None:
        self.project = self._blank_project(settings or ProjectSettings())
        self.path = None
        self.history_revision = 0
        self.saved_revision = 0
        self._pending_imports.clear()

    def open(self, path: str | Path) -> None:
        path = Path(path)
        project = load_project(path)
        if not project.compositions:
            raise ProjectFormatError('project has no compositions')
        self.project = project
        self.path = path
        self.history_revision = 0
        self.saved_revision = 0
        self._pending_imports.clear()

    def save(self) -> Path:
        if self.path is None:
            raise ValueError('no path; use save_as')
        return self.save_as(self.path)

    def save_as(self, path: str | Path) -> Path:
        path = Path(path)
        if path.suffix.lower() != '.aemvp':
            path = path.with_suffix('.aemvp')
        self._normalize_assets(path)
        save_project(self.project, path)
        self.path = path
        self.mark_clean()
        self._pending_imports.clear()
        return path

    def resolve_path(self, image_path: str) -> Path:
        return resolve_image_path(image_path, self.path)

    def is_missing_image(self, image_path: str) -> bool:
        return not self.resolve_path(image_path).is_file()

    def register_pending_import(self, layer_id: str, source: str | Path) -> None:
        """Remember an absolute source file to copy on first save."""
        self._pending_imports[layer_id] = Path(source).resolve()

    def import_image_for_layer(self, layer: ImageLayer, source: str | Path) -> str:
        """Set ``layer.path``; copy into assets if the project is already saved."""
        source = Path(source).resolve()
        if self.path is not None:
            dest = self._copy_into_assets(source, self.path)
            relative = dest.relative_to(self.path.parent).as_posix()
            layer.path = relative
            self._pending_imports.pop(layer.id, None)
            return relative
        layer.path = str(source)
        self.register_pending_import(layer.id, source)
        return layer.path

    def _normalize_assets(self, project_path: Path) -> None:
        """Copy pending/external images into ``stem.assets/images/`` and relativize."""
        images = images_dir_for(project_path)
        images.mkdir(parents=True, exist_ok=True)
        for composition in self.project.compositions:
            for layer in composition.layers:
                if not isinstance(layer, ImageLayer):
                    continue
                source = self._pending_imports.get(layer.id)
                if source is None:
                    current = resolve_image_path(layer.path, self.path or project_path)
                    if not current.is_file():
                        continue
                    # Already relative under this project's assets?
                    try:
                        rel = current.resolve().relative_to(project_path.parent.resolve())
                        if rel.as_posix().startswith(f'{project_path.stem}{ASSETS_SUFFIX}/'):
                            layer.path = rel.as_posix()
                            continue
                    except ValueError:
                        pass
                    source = current
                dest = self._copy_into_assets(source, project_path)
                layer.path = dest.relative_to(project_path.parent).as_posix()

    def _copy_into_assets(self, source: Path, project_path: Path) -> Path:
        images = images_dir_for(project_path)
        images.mkdir(parents=True, exist_ok=True)
        dest = images / source.name
        if dest.resolve() != source.resolve():
            counter = 1
            stem, suffix = source.stem, source.suffix
            while dest.exists() and dest.resolve() != source.resolve():
                dest = images / f'{stem}_{counter}{suffix}'
                counter += 1
            if not dest.exists():
                shutil.copy2(source, dest)
        return dest
