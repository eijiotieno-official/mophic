"""Make the source-tree layout importable like the installed package.

The launcher puts ``pkgdatadir`` on ``sys.path``, so ``import mophic``,
``import core`` and ``import examples`` all work. Tests do the same by
exposing ``src/`` as the ``mophic`` package.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src'

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if 'mophic' not in sys.modules:
    package = types.ModuleType('mophic')
    package.__path__ = [str(SRC)]
    package.__file__ = str(SRC / '__init__.py')
    sys.modules['mophic'] = package
