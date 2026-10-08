"""Export pipeline tests: pixel conversion and small MP4 encode."""

import subprocess

import cairo
import pytest

from core import Color, Composition, SolidLayer
from core.exporter import (ExportCancelled, ExportError, argb32_to_rgba,
                           export_composition, find_ffmpeg)


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


def test_find_ffmpeg_honours_env(monkeypatch, tmp_path):
    fake = tmp_path / 'ffmpeg'
    fake.write_text('#!/bin/sh\n', encoding='utf-8')
    fake.chmod(0o755)
    monkeypatch.setenv('MOPHIC_FFMPEG', str(fake))
    assert find_ffmpeg() == str(fake)


def test_find_ffmpeg_missing(monkeypatch):
    monkeypatch.delenv('MOPHIC_FFMPEG', raising=False)
    monkeypatch.setattr('core.exporter.shutil.which', lambda _name: None)
    monkeypatch.setattr('core.exporter.os.path.isfile', lambda _p: False)
    assert find_ffmpeg() is None


def test_argb32_to_rgba_opaque_red():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2, 1)
    ctx = cairo.Context(surface)
    ctx.set_source_rgba(1, 0, 0, 1)
    ctx.paint()
    rgba = argb32_to_rgba(surface)
    assert len(rgba) == 8
    assert rgba[0:4] == bytes((255, 0, 0, 255))


def test_argb32_to_rgba_flattens_over_background():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
    ctx = cairo.Context(surface)
    ctx.set_operator(cairo.OPERATOR_SOURCE)
    ctx.set_source_rgba(0, 0, 0, 0)
    ctx.paint()
    rgba = argb32_to_rgba(surface, Color(1, 1, 1, 1))
    assert rgba == bytes((255, 255, 255, 255))


def test_export_missing_ffmpeg_raises(monkeypatch, tmp_path):
    monkeypatch.setattr('core.exporter.find_ffmpeg', lambda: None)
    comp = Composition(width=64, height=64, duration=0.1, fps=10)
    comp.add_layer(SolidLayer(color=Color(1, 0, 0, 1)))
    with pytest.raises(ExportError, match='FFmpeg'):
        export_composition(comp, tmp_path / 'out.mp4')


@requires_ffmpeg
def test_export_small_mp4(tmp_path):
    comp = Composition(width=320, height=180, duration=1.0, fps=10.0,
                       background_color=Color(0.1, 0.1, 0.2, 1))
    comp.add_layer(SolidLayer(color=Color(0.8, 0.2, 0.1, 1)))
    out = tmp_path / 'clip.mp4'
    seen = []

    def progress(fraction):
        seen.append(fraction)

    export_composition(comp, out, progress=progress)
    assert out.is_file()
    assert out.stat().st_size > 500
    assert seen and seen[-1] == pytest.approx(1.0)

    ffmpeg = find_ffmpeg()
    probe = subprocess.run(
        [ffmpeg, '-i', str(out), '-f', 'null', '-'],
        capture_output=True, text=True,
    )
    # ffmpeg writes probe info to stderr
    combined = probe.stderr
    assert '320x180' in combined or '320x' in combined
    assert 'h264' in combined.lower() or 'H.264' in combined


@requires_ffmpeg
def test_export_cancel_deletes_partial(tmp_path):
    comp = Composition(width=320, height=180, duration=2.0, fps=15.0)
    comp.add_layer(SolidLayer(color=Color(0, 1, 0, 1)))
    out = tmp_path / 'partial.mp4'
    calls = {'n': 0}

    def cancel():
        calls['n'] += 1
        return calls['n'] > 3

    with pytest.raises(ExportCancelled):
        export_composition(comp, out, cancel=cancel)
    assert not out.exists()
