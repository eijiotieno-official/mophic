# Mophic

A lightweight 2D motion graphics application for Linux, built with Python,
GTK 4 and libadwaita.

## Current status

**Phase 1 — application scaffold.**

The application opens a single empty libadwaita window. Editor functionality
(compositions, layers, timeline, keyframes, rendering, export) is not
implemented yet.

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
data/                              Desktop file, AppStream metadata, schema, D-Bus service, icons
po/                                Translation setup
src/                               Python package, launcher script and UI files
```

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
meson test -C build        # validates the desktop file, AppStream metadata and schema
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
