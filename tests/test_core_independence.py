import ast
import pathlib
import subprocess
import sys

CORE_DIR = pathlib.Path(__file__).resolve().parent.parent / 'core'
FORBIDDEN = {'gi', 'cairo', 'Gtk', 'Adw', 'numpy', 'PIL'}


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


def test_core_sources_only_import_the_standard_library_and_core():
    sources = sorted(CORE_DIR.glob('*.py'))
    assert sources
    allowed = set(sys.stdlib_module_names)
    for source in sources:
        tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split('.')[0]
                assert top not in FORBIDDEN, f'{source.name} imports {name}'
                assert top in allowed, f'{source.name} imports non-stdlib module {name}'
