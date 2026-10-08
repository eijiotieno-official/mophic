core_sources = [
  '__init__.py',
  'commands.py',
  'easing.py',
  'layers.py',
  'project.py',
  'properties.py',
  'renderer.py',
  'serialization.py',
]

# renderer.py needs pycairo and PyGObject, plus the Pango, PangoCairo and
# GdkPixbuf introspection data. The rest of core/ is standard library only.
import('python').find_installation('python3', modules: ['cairo', 'gi'])
dependency('pangocairo')
dependency('gdk-pixbuf-2.0')

install_data(core_sources, install_dir: pkgdatadir / 'core')
