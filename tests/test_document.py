"""DocumentController tests (no GUI dialogs)."""

from pathlib import Path

import pytest

from core import Color, ImageLayer, Project, load_project
from core.serialization import ProjectFormatError
from examples.demo_project import LOGO_PATH, build_demo_composition
from mophic.document import DocumentController, ProjectSettings, assets_dir_for, images_dir_for


def test_new_project_empty_composition():
    doc = DocumentController()
    doc.new_project(ProjectSettings(name='Blank', width=640, height=360, fps=24, duration=2))
    assert doc.project.name == 'Blank'
    assert doc.composition.width == 640
    assert doc.composition.height == 360
    assert doc.composition.fps == 24
    assert doc.composition.duration == 2
    assert len(doc.composition.layers) == 0
    assert doc.path is None
    assert not doc.is_dirty


def test_dirty_revision_tracks_edits_and_undo():
    doc = DocumentController()
    assert not doc.is_dirty
    doc.note_edit()
    assert doc.is_dirty
    doc.note_edit()
    assert doc.history_revision == 2
    doc.mark_clean()
    assert not doc.is_dirty
    doc.note_undo()
    assert doc.is_dirty
    doc.note_redo()
    assert not doc.is_dirty


def test_save_load_round_trip(tmp_path):
    doc = DocumentController()
    doc.new_project(ProjectSettings(name='Round', width=320, height=180, duration=1))
    path = tmp_path / 'round.aemvp'
    doc.save_as(path)
    assert path.is_file()
    assert not doc.is_dirty
    assert doc.path == path

    other = DocumentController()
    other.open(path)
    assert other.project.name == 'Round'
    assert other.composition.width == 320
    assert other.composition.height == 180
    assert not other.is_dirty


def test_first_save_copies_image_into_assets(tmp_path):
    doc = DocumentController()
    doc.new_project(ProjectSettings(name='Assets', width=200, height=200, duration=1))
    layer = ImageLayer(name='Logo', path=str(LOGO_PATH))
    doc.composition.add_layer(layer)
    doc.import_image_for_layer(layer, LOGO_PATH)
    assert Path(layer.path).is_absolute()

    path = tmp_path / 'demo.aemvp'
    doc.save_as(path)
    assert layer.path.startswith('demo.assets/images/')
    asset = tmp_path / layer.path
    assert asset.is_file()
    assert images_dir_for(path).is_dir()

    loaded = DocumentController()
    loaded.open(path)
    image = next(layer for layer in loaded.composition.layers if isinstance(layer, ImageLayer))
    assert not Path(image.path).is_absolute()
    assert loaded.resolve_path(image.path).is_file()
    assert not loaded.is_missing_image(image.path)


def test_missing_asset_detected(tmp_path):
    doc = DocumentController()
    doc.new_project(ProjectSettings(name='Miss', width=100, height=100, duration=1))
    layer = ImageLayer(path=str(tmp_path / 'gone.png'))
    doc.composition.add_layer(layer)
    path = tmp_path / 'miss.aemvp'
    doc.save_as(path)
    # Path may stay absolute if file missing during normalize.
    loaded = DocumentController()
    loaded.open(path)
    image = loaded.composition.layers[0]
    assert isinstance(image, ImageLayer)
    assert loaded.is_missing_image(image.path)


def test_open_invalid_raises(tmp_path):
    bad = tmp_path / 'bad.aemvp'
    bad.write_text('{not json', encoding='utf-8')
    doc = DocumentController()
    with pytest.raises(ProjectFormatError):
        doc.open(bad)


def test_save_appends_extension(tmp_path):
    doc = DocumentController()
    doc.new_project(ProjectSettings(name='Ext'))
    path = doc.save_as(tmp_path / 'noext')
    assert path.suffix == '.aemvp'
    assert path.is_file()


def test_assets_dir_helpers():
    path = Path('/tmp/foo/bar.aemvp')
    assert assets_dir_for(path) == Path('/tmp/foo/bar.assets')
    assert images_dir_for(path) == Path('/tmp/foo/bar.assets/images')
