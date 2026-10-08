import ast
import pathlib
import subprocess
import sys

CORE_DIR = pathlib.Path(__file__).resolve().parent.parent / 'core'
FORBIDDEN = {'gi', 'cairo', 'Gtk', 'Adw', 'numpy', 'PIL'}
RENDERER = 'renderer.py'
EXPORTER = 'exporter.py'
CAIRO_MODULES = {RENDERER, EXPORTER}
RENDERER_EXTRA_MODULES = {'cairo', 'gi'}
RENDERER_GI_NAMESPACES = {'GdkPixbuf', 'GLib', 'Pango', 'PangoCairo'}
EXPORTER_EXTRA_MODULES = {'cairo'}


def test_importing_core_does_not_load_gtk_or_cairo():
    script = (
        'import sys\n'
        'import core, core.commands, core.easing, core.layers, core.project, '
        'core.properties, core.serialization\n'
        'loaded = sorted(name for name in ("gi", "cairo") if name in sys.modules)\n'
        'print(",".join(loaded))\n'
    )
    result = subprocess.run([sys.executable, '-c', script], cwd=CORE_DIR.parent,
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == ''


def imported_modules(source):
    """Yield (module, imported names) for each absolute import in ``source``."""
    tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, []
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            yield node.module, [alias.name for alias in node.names]


def test_core_sources_only_import_the_standard_library_and_core():
    sources = sorted(CORE_DIR.glob('*.py'))
    assert sources
    allowed = set(sys.stdlib_module_names)
    for source in sources:
        if source.name in CAIRO_MODULES:
            continue
        for name, _names in imported_modules(source):
            top = name.split('.')[0]
            assert top not in FORBIDDEN, f'{source.name} imports {name}'
            assert top in allowed, f'{source.name} imports non-stdlib module {name}'


def test_renderer_only_adds_cairo_pango_and_gdkpixbuf():
    source = CORE_DIR / RENDERER
    allowed = set(sys.stdlib_module_names) | RENDERER_EXTRA_MODULES
    for name, names in imported_modules(source):
        top = name.split('.')[0]
        assert top in allowed, f'{RENDERER} imports {name}'
        if name == 'gi.repository':
            assert set(names) <= RENDERER_GI_NAMESPACES, f'{RENDERER} imports {names}'
        else:
            assert not name.startswith('gi.repository.'), f'{RENDERER} imports {name}'


def test_exporter_only_adds_cairo():
    source = CORE_DIR / EXPORTER
    allowed = set(sys.stdlib_module_names) | EXPORTER_EXTRA_MODULES
    for name, _names in imported_modules(source):
        top = name.split('.')[0]
        assert top in allowed, f'{EXPORTER} imports {name}'
