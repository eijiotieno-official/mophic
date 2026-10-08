"""Shared pytest fixtures.

Makes the source-tree layout importable like the installed package, and
provides one session-wide GTK application for window tests.
"""

import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from core import Color, Composition, Point, ShapeLayer

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src'
RESOURCE_XML = SRC / 'mophic.gresource.xml'

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if 'mophic' not in sys.modules:
    package = types.ModuleType('mophic')
    package.__path__ = [str(SRC)]
    package.__file__ = str(SRC / '__init__.py')
    sys.modules['mophic'] = package


def _have_display():
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Gtk
        return bool(Gtk.init_check())
    except Exception:
        return False


requires_display = pytest.mark.skipif(
    not _have_display() or shutil.which('glib-compile-resources') is None,
    reason='needs a display and glib-compile-resources',
)


@pytest.fixture(scope='session')
def gresource(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp('gresource')
    out = out_dir / 'mophic.gresource'
    subprocess.run(
        ['glib-compile-resources',
         f'--sourcedir={SRC}',
         f'--target={out}',
         str(RESOURCE_XML)],
        check=True,
    )
    return out


@pytest.fixture(scope='session')
def app(gresource):
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Adw, Gio

    resource = Gio.Resource.load(str(gresource))
    resource._register()
    Adw.init()
    application = Adw.Application(application_id='io.github.eijiotieno.Mophic.tests')
    application.register()
    from mophic.window import MophicWindow  # noqa: F401
    yield application
    application.release()


@pytest.fixture
def window_class(app):
    from mophic.window import MophicWindow
    return MophicWindow


def small_comp(duration=2.0, fps=10.0):
    """A tiny composition so window tests stay fast."""
    comp = Composition(width=64, height=36, fps=fps, duration=duration,
                       background_color=Color(0.1, 0.2, 0.3, 1.0))
    layer = ShapeLayer(shape_type='rectangle', width=20, height=10,
                       fill_color=Color(1, 0, 0, 1), position=Point(32, 18))
    layer.opacity.set_keyframe(0.0, 0.0)
    layer.opacity.set_keyframe(duration, 1.0)
    comp.add_layer(layer)
    return comp


def make_window(window_class, app, composition=None):
    return window_class(application=app, composition=composition or small_comp())
