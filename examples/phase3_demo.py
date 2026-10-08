# phase3_demo.py
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

"""Render the demonstration composition to ``_output/phase3-render.png``.

Run from the project root with ``python3 -m examples.phase3_demo``.
"""

import pathlib

from core.renderer import CairoRenderer
from examples.demo_project import build_demo_composition

OUTPUT_DIR = pathlib.Path(__file__).resolve().parent.parent / '_output'
RENDER_TIME = 2.0


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    comp = build_demo_composition()
    frame = CairoRenderer().render_frame(comp, RENDER_TIME)
    output = OUTPUT_DIR / 'phase3-render.png'
    frame.write_png(output)
    print(f'Wrote {output} ({frame.width}x{frame.height}, t={RENDER_TIME}s)')


if __name__ == '__main__':
    main()
