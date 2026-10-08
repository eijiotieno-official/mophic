"""Round-trip project + short export smoke test."""

import subprocess

import pytest

from core import Color, Composition, SolidLayer, load_project
from core.exporter import export_composition, find_ffmpeg
from examples.demo_project import build_demo_composition
from mophic.document import DocumentController, ProjectSettings


def _have_ffmpeg_x264():
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False
    try:
        out = subprocess.run([ffmpeg, '-hide_banner', '-encoders'],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return 'libx264' in out.stdout


requires_ffmpeg = pytest.mark.skipif(
    not _have_ffmpeg_x264(), reason='needs ffmpeg with libx264')


@requires_ffmpeg
def test_save_reload_and_export(tmp_path):
    doc = DocumentController()
    doc.new_project(ProjectSettings(name='Clip', width=320, height=180,
                                    fps=10, duration=0.5,
                                    background_color=Color(0.05, 0.05, 0.1, 1)))
    doc.composition.add_layer(SolidLayer(color=Color(0.9, 0.3, 0.2, 1)))
    path = tmp_path / 'clip.aemvp'
    doc.save_as(path)

    loaded = load_project(path)
    comp = loaded.compositions[0]
    assert comp.width == 320
    out = tmp_path / 'clip.mp4'
    export_composition(comp, out)
    assert out.is_file() and out.stat().st_size > 200


@requires_ffmpeg
def test_demo_composition_exports(tmp_path):
    comp = build_demo_composition()
    # Shorten for speed.
    comp.duration = 0.2
    out = tmp_path / 'demo.mp4'
    export_composition(comp, out, width=320, height=180, fps=10)
    assert out.is_file()
