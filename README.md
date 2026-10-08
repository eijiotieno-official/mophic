# Mophic

A lightweight 2D motion graphics application for Linux, built with Python,
GTK 4 and libadwaita.

## Current status

**MVP complete (Phases 1–8).**

Mophic edits layered compositions with keyframed transforms, a timeline,
project open/save with sidecar image assets, preview playback, undo/redo, and
H.264 MP4 export through FFmpeg. Visual quality is CPU Cairo (no GPU
compositor, no motion blur, limited text/shape fidelity compared with
professional tools).

## Application ID

```
io.github.eijiotieno.Mophic
```

## Project layout

```
io.github.eijiotieno.Mophic.json   Flatpak manifest (GNOME 51 + bundled FFmpeg)
meson.build                        Top-level Meson project
core/                              Model, commands, Cairo renderer, exporter
data/                              Desktop file, AppStream, schema, icons
examples/                          Demo composition, sample `.aemvp`, logo
src/                               GTK UI: window, timeline, properties, document
tests/                             pytest suite
```

`core/` never imports GTK, GDK or libadwaita. Everything except
`core/renderer.py` and `core/exporter.py` is stdlib-only; those two need
Cairo / PyGObject (exporter also needs a host or bundled `ffmpeg`).

## Features

| Area | Behaviour |
|---|---|
| Layers | Solid, shape (rect/ellipse/line), text, image; add/delete/duplicate/rename/reorder/visibility |
| Transform | Position, scale (%), rotation (°), opacity; keyframable |
| Timeline | Tracks for the selected layer; playhead scrub; diamond keyframes; drag to move; Delete removes KF |
| Properties | Edit values at the playhead; KF toggle; easing when a KF is selected |
| Projects | New / Open / Save / Save As (`.aemvp`); dirty indicator; confirm on quit |
| Assets | Sidecar `name.assets/images/`; relative image paths; missing images show a soft placeholder |
| Playback | Play/pause, loop, scrub, Home/End, frame step |
| Undo | Ctrl+Z / Ctrl+Shift+Z |
| Export | MP4 via Cairo → RGBA → FFmpeg `libx264` `yuv420p`, no audio |

### Sample project

`examples/mophic-demo.aemvp` (+ `examples/mophic-demo.assets/`) is the packaged
demo. **Open Demo** loads it. The CLI PNG demo remains:

```bash
python3 -m examples.phase3_demo
```

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+N / O / S | New / Open / Save |
| Ctrl+Shift+S | Save As |
| Ctrl+E | Export |
| Ctrl+Z / Ctrl+Shift+Z | Undo / Redo |
| Space | Play / Pause |
| Home / End | Start / end |
| Left / Right | Step one frame |
| Delete | Selected keyframe, else selected layer |

## Project files

Format `aemvp` version `1`. Image layer `path` values are project-relative when
saved (e.g. `demo.assets/images/logo.png`). Resolve against the project
directory at load/render.

## Export

```python
from core.exporter import export_composition, find_ffmpeg

export_composition(composition, 'out.mp4', width=1280, height=720, fps=30)
```

Requires FFmpeg with `libx264`. Override the binary with `MOPHIC_FFMPEG`.
Flatpak builds ship `/app/bin/ffmpeg` (no host spawn). Cancel deletes a
partial output file.

## Limitations (honest)

- CPU Cairo only; no GPU acceleration or multi-threaded render
- No audio, masks, effects, parenting, or 3D
- Text uses system fonts via Pango; no per-character animation
- Image decode via GdkPixbuf; missing files draw a magenta “Missing” tile
- Export scales by changing composition size on a deep-copied snapshot (no
  high-quality scaler beyond Cairo)
- Timeline shows only the selected layer’s transform tracks
- Continuous spin edits are not coalesced into a single undo step (keyframe
  drag commits once on release)

## Tests

```bash
python3 -m pytest
meson test -C build
```

Export tests skip when FFmpeg/`libx264` is unavailable. Window tests need a
display. Inside Flatpak SDK builds, pytest may be skipped by Meson.

## CLI build

```bash
meson setup build --prefix="$PWD/_install"
meson compile -C build
meson test -C build
meson install -C build
./_install/bin/mophic
```

## Flatpak build

```bash
flatpak-builder --user --install --force-clean flatpak-build io.github.eijiotieno.Mophic.json
flatpak run io.github.eijiotieno.Mophic
```

The manifest bundles **x264** and a minimal **FFmpeg** (rawvideo in, libx264
MP4 out) before the `mophic` module. Finish-args are Wayland/X11/DRI only.

## License

GPL-3.0-or-later. See [COPYING](COPYING).
