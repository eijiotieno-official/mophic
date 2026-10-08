# Mophic

A lightweight 2D motion graphics application for Linux, built with Python,
GTK 4 and libadwaita.

## Current status

**Phase 3 — CPU frame renderer.**

The `core/` package models projects, compositions, layers, animatable
properties, keyframes and easing, saves and loads them as JSON, and supports
undo/redo. `core/renderer.py` renders any composition at any time to a Cairo
image. It is fully tested and independent of GTK.

The application still opens a single empty libadwaita window. The editor UI,
preview, playback, timeline and export are not implemented yet.

## Application ID

```
io.github.eijiotieno.Mophic
```

The same ID is used by the Flatpak manifest, the desktop file, the AppStream
metadata, the GSettings schema, the D-Bus service, the icons, the GResource
prefix (`/io/github/eijiotieno/Mophic`) and `Adw.Application`.

## Project layout

```
io.github.eijiotieno.Mophic.json   Flatpak manifest (org.gnome.Platform/Sdk 51)
meson.build                        Top-level Meson project
core/                              Headless motion graphics model and Cairo renderer
data/                              Desktop file, AppStream metadata, schema, D-Bus service, icons
po/                                Translation setup
examples/                          Phase 3 demonstration script
src/                               GTK/libadwaita application, launcher script and UI files
tests/                             pytest suite for core/
```

`core/` never imports GTK, GDK or libadwaita; tests enforce this. Every module
except `core/renderer.py` uses only the Python standard library, and
`import core` does not load Cairo or PyGObject. It is installed next to the
application package (`share/mophic/core/`), so the UI can `import core`.

## Core model

| Module | Contents |
|---|---|
| `core/project.py` | `Project`, `Composition`, layer stack operations, time helpers |
| `core/layers.py` | `SolidLayer`, `ShapeLayer`, `TextLayer`, `ImageLayer` |
| `core/properties.py` | `Point`, `Scale`, `Color`, `Keyframe`, `AnimatableProperty` |
| `core/easing.py` | `linear`, `ease-in`, `ease-out`, `ease-in-out`, `cubic-bezier` |
| `core/serialization.py` | `save_project`, `load_project` |
| `core/commands.py` | Undoable commands and `UndoStack` |

Conventions:

- **Time** is in seconds (float). Frame `n` starts at `n / fps`;
  `frame_at_time(t)` is `floor(t * fps)` with a 1e-9 tolerance for
  floating-point error. A composition's `duration` is its exclusive end.
- **Composition defaults:** 1920×1080, 30 fps, 30 seconds, opaque black
  background.
- **Layer order:** `layers[0]` is the bottom layer, `layers[-1]` the top.
- **Transform:** coordinates are pixels, origin top-left, y down.
  `position` places the layer's static `anchor_point`; `scale` is in percent
  (100 = original size) and `rotation` in degrees clockwise, both around the
  anchor point; `opacity` runs from 0.0 to 1.0.
- **Colors** are RGBA with each channel from 0.0 to 1.0.
- **Keyframes:** with no keyframes a property has its base value; with one
  keyframe it has that value at all times; before the first and after the last
  keyframe it holds their values. Between two keyframes, the easing stored on
  the earlier keyframe shapes the interpolation. Setting a keyframe at an
  existing time replaces it.
- **Easing:** `ease-in` is `t²`, `ease-out` is `1 - (1 - t)²`, `ease-in-out`
  is smoothstep (`3t² - 2t³`), and `cubic-bezier` behaves like CSS
  `cubic-bezier()`. These are not exact copies of After Effects easing.
- **IDs** are UUID strings that survive save, load, undo and redo;
  `Layer.duplicate()` gives the copy a new ID.

## Project files

Projects are saved as indented, UTF-8 JSON with a fixed key order, so the
same project always produces the same file. Every file starts with:

```json
{
  "format": "aemvp",
  "version": 1,
  "name": "Example",
  "compositions": [ ... ]
}
```

Animatable properties are stored as a base value plus keyframes:

```json
"opacity": {
  "value": 1.0,
  "keyframes": [
    {"time": 0.0, "value": 0.0, "easing": {"type": "ease-out"}},
    {"time": 1.0, "value": 1.0, "easing": {"type": "cubic-bezier", "x1": 0.25, "y1": 0.1, "x2": 0.25, "y2": 1.0}}
  ]
}
```

Each layer has an explicit `"type"` of `solid`, `shape`, `text` or `image`.
Loading is strict: an unknown format or version, a missing or unknown key, a
wrong type or an invalid value raises `ProjectFormatError` naming the exact
location, such as `compositions[0].layers[2].opacity.keyframes[1].time`.

## Rendering

```python
from core.renderer import CairoRenderer

frame = CairoRenderer().render_frame(composition, 2.0)
frame.write_png('frame.png')
frame.pixel(10, 20)   # Pixel(r, g, b, a), 0–255, premultiplied
```

`CairoRenderer` draws on the CPU into a `cairo.FORMAT_ARGB32` surface at the
composition's resolution. It needs pycairo, PyGObject, Pango/PangoCairo and
GdkPixbuf, all part of the GNOME 51 runtime; Meson checks for them. It does
not use GTK, so it runs in a plain `python3` process.

- The background is painted first (a transparent background stays
  transparent), then `layers[0]` through `layers[-1]`. Invisible layers are
  skipped. Rendering never changes the composition.
- Each layer is transformed as described under *Core model*. Opacity fades the
  whole layer, so overlapping fill and stroke do not show through each other.
  Strokes are drawn in layer space and scale with the layer.
- **Shapes:** rectangles and ellipses are centered on the layer origin and
  filled, then stroked; lines run from `start` to `end` and are stroked only.
- **Text** is laid out with Pango using system fonts. The first line's
  baseline is at the layer origin; `left`, `center` and `right` alignment put
  the start, middle or end of the text there. Hinting is off so text renders
  identically at any position.
- **Images** (PNG, JPEG and other formats GdkPixbuf supports) are drawn at
  their natural pixel size with their top-left corner at the layer origin,
  and filtered bilinearly. Each renderer caches decoded images by resolved
  path; a missing or unreadable file raises `RenderError`.
- `RenderedFrame.surface` stores each pixel as a native-endian 32-bit word,
  alpha in the top byte, then red, green and blue, premultiplied by alpha.
  `RenderedFrame.pixel()` decodes it the same way on every machine.

Rendering the same composition at the same time always gives the same pixels.

### Demo

```bash
python3 -m examples.phase3_demo
```

This builds a 1920×1080, 30 fps, 5 second composition with a background,
animated title, subtitle, rectangle, ellipse, growing line, fading highlight
and an image, and writes its frame at 2.0 s to `_output/phase3-render.png`.
`_output/` is ignored by Git.

## Tests

The core tests use pytest and run without GTK. The renderer tests also need
pycairo, PyGObject, Pango and GdkPixbuf. From the project root:

```bash
python3 -m pytest
```

`meson test -C build` runs the same suite together with the metadata checks.
pytest is not part of the GNOME SDK, so inside Flatpak builds the core test is
skipped.

## GNOME Builder

1. Start GNOME Builder and choose **Open a Project**, then select this
   directory. From a terminal: `gnome-builder -p .`
2. Builder detects `io.github.eijiotieno.Mophic.json` and creates a build
   configuration that uses the `org.gnome.Sdk//51` runtime. You can check it
   under **Configure Project**.
3. Click **Build** (the hammer button, or <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Alt</kbd>+<kbd>B</kbd>).
4. Click **Run** (the play button, or <kbd>Shift</kbd>+<kbd>Ctrl</kbd>+<kbd>Space</kbd>).

## CLI build

The launcher script loads its Python modules and GResource bundle from the
install prefix, so install into a local prefix before running:

```bash
meson setup build --prefix="$PWD/_install"
meson compile -C build
meson test -C build        # metadata checks and the core test suite
meson install -C build
./_install/bin/mophic
```

If `build/` already exists, run `meson setup --reconfigure build` instead of
`meson setup build`.

## Flatpak build

Build the manifest, install it into your user installation, and run it:

```bash
flatpak-builder --user --install --force-clean flatpak-build io.github.eijiotieno.Mophic.json
flatpak run io.github.eijiotieno.Mophic
```

The manifest builds the working tree directly (a `dir` source), so
uncommitted changes are included. Local build output (`build`, `_install`,
`flatpak-build`) is skipped.

## License

GPL-3.0-or-later. See [COPYING](COPYING).
