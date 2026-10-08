# serialization.py
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

"""JSON project files.

Files are UTF-8 JSON indented by two spaces, with keys in a fixed order,
so saving the same project always produces the same bytes. The top level
holds ``format`` (``PROJECT_FORMAT``), ``version`` (``PROJECT_VERSION``),
``name`` and ``compositions``.

Loading is strict: an unknown format or version, a missing or unknown
key, a wrong JSON type, a duplicate keyframe time or any value the model
rejects raises ``ProjectFormatError`` naming the offending location, for
example ``compositions[0].layers[2].opacity.keyframes[1].time``.
"""

import json
import os
import tempfile
from collections.abc import Callable
from typing import Any

from .easing import Easing
from .layers import (LAYER_TYPES, ImageLayer, Layer, ShapeLayer, SolidLayer,
                     TextLayer)
from .project import PROJECT_FORMAT, PROJECT_VERSION, Composition, Project
from .properties import AnimatableProperty, Color, Point, Scale, check_number

_TRANSFORM_PROPERTIES = ('position', 'scale', 'rotation', 'opacity')
_LAYER_BASE_KEYS = ('id', 'type', 'name', 'visible', 'anchor_point') + _TRANSFORM_PROPERTIES
_LAYER_KEYS: dict[str, tuple[str, ...]] = {
    'solid': ('color',),
    'shape': ('shape_type', 'width', 'height', 'start', 'end',
              'fill_color', 'stroke_color', 'stroke_width'),
    'text': ('text', 'font_family', 'font_size', 'color', 'alignment'),
    'image': ('path',),
}
_COMPOSITION_KEYS = ('id', 'name', 'width', 'height', 'fps', 'duration',
                     'background_color', 'layers')
_PROJECT_KEYS = ('format', 'version', 'name', 'compositions')


class ProjectFormatError(ValueError):
    """A project file is malformed, unsupported or contains invalid values."""


# Writing


def _encode_color(color: Color | None) -> dict[str, float] | None:
    if color is None:
        return None
    return {'r': color.r, 'g': color.g, 'b': color.b, 'a': color.a}


def _encode_vector(value: Point | Scale) -> dict[str, float]:
    return {'x': value.x, 'y': value.y}


def _encode_value(value: Any) -> Any:
    if isinstance(value, (Point, Scale)):
        return _encode_vector(value)
    return value


def _encode_easing(easing: Easing) -> dict[str, Any]:
    data: dict[str, Any] = {'type': easing.kind}
    if easing.kind == 'cubic-bezier':
        data.update(x1=easing.x1, y1=easing.y1, x2=easing.x2, y2=easing.y2)
    return data


def _encode_property(prop: AnimatableProperty) -> dict[str, Any]:
    return {
        'value': _encode_value(prop.base_value),
        'keyframes': [
            {
                'time': keyframe.time,
                'value': _encode_value(keyframe.value),
                'easing': _encode_easing(keyframe.easing),
            }
            for keyframe in prop.keyframes
        ],
    }


def layer_to_dict(layer: Layer) -> dict[str, Any]:
    """Return the JSON-compatible representation of ``layer``."""
    data: dict[str, Any] = {
        'id': layer.id,
        'type': layer.layer_type,
        'name': layer.name,
        'visible': layer.visible,
        'anchor_point': _encode_vector(layer.anchor_point),
    }
    for name in _TRANSFORM_PROPERTIES:
        data[name] = _encode_property(getattr(layer, name))

    if isinstance(layer, SolidLayer):
        data['color'] = _encode_color(layer.color)
    elif isinstance(layer, ShapeLayer):
        data.update(
            shape_type=layer.shape_type,
            width=layer.width,
            height=layer.height,
            start=_encode_vector(layer.start),
            end=_encode_vector(layer.end),
            fill_color=_encode_color(layer.fill_color),
            stroke_color=_encode_color(layer.stroke_color),
            stroke_width=layer.stroke_width,
        )
    elif isinstance(layer, TextLayer):
        data.update(
            text=layer.text,
            font_family=layer.font_family,
            font_size=layer.font_size,
            color=_encode_color(layer.color),
            alignment=layer.alignment,
        )
    elif isinstance(layer, ImageLayer):
        data['path'] = layer.path
    else:
        raise TypeError(f'cannot serialize layer type {type(layer).__name__}')
    return data


def composition_to_dict(composition: Composition) -> dict[str, Any]:
    """Return the JSON-compatible representation of ``composition``."""
    return {
        'id': composition.id,
        'name': composition.name,
        'width': composition.width,
        'height': composition.height,
        'fps': composition.fps,
        'duration': composition.duration,
        'background_color': _encode_color(composition.background_color),
        'layers': [layer_to_dict(layer) for layer in composition.layers],
    }


def project_to_dict(project: Project) -> dict[str, Any]:
    """Return the JSON-compatible representation of ``project``."""
    return {
        'format': project.format,
        'version': project.version,
        'name': project.name,
        'compositions': [composition_to_dict(c) for c in project.compositions],
    }


def project_to_json(project: Project) -> str:
    """Return the exact text ``save_project`` writes for ``project``."""
    return json.dumps(project_to_dict(project), indent=2, ensure_ascii=False,
                      allow_nan=False) + '\n'


def save_project(project: Project, path: str | os.PathLike[str]) -> None:
    """Write ``project`` to ``path`` as JSON.

    The file is written to a temporary file in the same directory and then
    renamed over ``path``, so an existing file is never left half-written.
    """
    text = project_to_json(project)
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path))
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644

    handle = tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=directory,
                                         prefix=f'.{os.path.basename(path)}.',
                                         suffix='.tmp', delete=False)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(handle.name, mode)
        os.replace(handle.name, path)
    except BaseException:
        os.unlink(handle.name)
        raise


# Reading


def _join(path: str, key: str) -> str:
    return f'{path}.{key}' if path else key


def _error(path: str, message: str) -> ProjectFormatError:
    return ProjectFormatError(f'{path}: {message}' if path else message)


def _object(data: Any, path: str, keys: tuple[str, ...]) -> dict[str, Any]:
    """Check that ``data`` is an object with exactly ``keys``."""
    if not isinstance(data, dict):
        raise _error(path, f'expected an object, got {_json_type(data)}')
    for key in keys:
        if key not in data:
            raise _error(path, f'missing key {key!r}')
    unknown = sorted(set(data) - set(keys))
    if unknown:
        raise _error(path, f'unknown key {unknown[0]!r}')
    return data


def _json_type(value: Any) -> str:
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, (int, float)):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    return 'object'


def _list(data: Any, path: str) -> list[Any]:
    if not isinstance(data, list):
        raise _error(path, f'expected an array, got {_json_type(data)}')
    return data


def _build(path: str, factory: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Call a model constructor, reporting its validation errors at ``path``."""
    try:
        return factory(*args, **kwargs)
    except (TypeError, ValueError, KeyError, IndexError) as error:
        message = error.args[0] if isinstance(error, KeyError) and error.args else error
        raise _error(path, str(message)) from error


def _decode_color(data: Any, path: str) -> Color:
    fields = _object(data, path, ('r', 'g', 'b', 'a'))
    return _build(path, Color, fields['r'], fields['g'], fields['b'], fields['a'])


def _decode_optional_color(data: Any, path: str) -> Color | None:
    return None if data is None else _decode_color(data, path)


def _decode_vector(data: Any, path: str, vector_type: type) -> Point | Scale:
    fields = _object(data, path, ('x', 'y'))
    return _build(path, vector_type, fields['x'], fields['y'])


def _decode_value(data: Any, path: str, value_type: type) -> Any:
    if value_type in (Point, Scale):
        return _decode_vector(data, path, value_type)
    return _build(path, check_number, 'value', data)


def _decode_easing(data: Any, path: str) -> Easing:
    if not isinstance(data, dict):
        raise _error(path, f'expected an object, got {_json_type(data)}')
    kind = data.get('type')
    if kind == 'cubic-bezier':
        fields = _object(data, path, ('type', 'x1', 'y1', 'x2', 'y2'))
        return _build(path, Easing, kind, fields['x1'], fields['y1'], fields['x2'], fields['y2'])
    _object(data, path, ('type',))
    return _build(path, Easing, kind)


def _base_value(data: Any, path: str, value_type: type) -> Any:
    fields = _object(data, path, ('value', 'keyframes'))
    return _decode_value(fields['value'], _join(path, 'value'), value_type)


def _load_keyframes(prop: AnimatableProperty, data: dict[str, Any], path: str) -> None:
    keyframes_path = _join(path, 'keyframes')
    for index, item in enumerate(_list(data['keyframes'], keyframes_path)):
        item_path = f'{keyframes_path}[{index}]'
        fields = _object(item, item_path, ('time', 'value', 'easing'))
        time_path = _join(item_path, 'time')
        time = _build(time_path, check_number, 'time', fields['time'])
        if time < 0.0:
            raise _error(time_path, f'keyframe time must be >= 0, got {time!r}')
        if prop.has_keyframe(time):
            raise _error(time_path, f'duplicate keyframe time {time!r}')
        value = _decode_value(fields['value'], _join(item_path, 'value'), prop.value_type)
        easing = _decode_easing(fields['easing'], _join(item_path, 'easing'))
        _build(item_path, prop.set_keyframe, time, value, easing)


def _decode_layer(data: Any, path: str) -> Layer:
    if not isinstance(data, dict):
        raise _error(path, f'expected an object, got {_json_type(data)}')
    layer_type = data.get('type')
    if layer_type not in LAYER_TYPES:
        raise _error(_join(path, 'type'), f'unknown layer type {layer_type!r}')
    fields = _object(data, path, _LAYER_BASE_KEYS + _LAYER_KEYS[layer_type])

    kwargs: dict[str, Any] = {
        'id': fields['id'],
        'name': fields['name'],
        'visible': fields['visible'],
        'anchor_point': _decode_vector(fields['anchor_point'], _join(path, 'anchor_point'), Point),
        'position': _base_value(fields['position'], _join(path, 'position'), Point),
        'scale': _base_value(fields['scale'], _join(path, 'scale'), Scale),
        'rotation': _base_value(fields['rotation'], _join(path, 'rotation'), float),
        'opacity': _base_value(fields['opacity'], _join(path, 'opacity'), float),
    }

    if layer_type == 'solid':
        kwargs['color'] = _decode_color(fields['color'], _join(path, 'color'))
    elif layer_type == 'shape':
        kwargs.update(
            shape_type=fields['shape_type'],
            width=fields['width'],
            height=fields['height'],
            start=_decode_vector(fields['start'], _join(path, 'start'), Point),
            end=_decode_vector(fields['end'], _join(path, 'end'), Point),
            fill_color=_decode_optional_color(fields['fill_color'], _join(path, 'fill_color')),
            stroke_color=_decode_optional_color(fields['stroke_color'], _join(path, 'stroke_color')),
            stroke_width=fields['stroke_width'],
        )
    elif layer_type == 'text':
        kwargs.update(
            text=fields['text'],
            font_family=fields['font_family'],
            font_size=fields['font_size'],
            color=_decode_color(fields['color'], _join(path, 'color')),
            alignment=fields['alignment'],
        )
    else:
        kwargs['path'] = fields['path']

    layer = _build(path, LAYER_TYPES[layer_type], **kwargs)
    for name in _TRANSFORM_PROPERTIES:
        _load_keyframes(getattr(layer, name), fields[name], _join(path, name))
    return layer


def _decode_composition(data: Any, path: str) -> Composition:
    fields = _object(data, path, _COMPOSITION_KEYS)
    composition = _build(
        path, Composition,
        id=fields['id'],
        name=fields['name'],
        width=fields['width'],
        height=fields['height'],
        fps=fields['fps'],
        duration=fields['duration'],
        background_color=_decode_color(fields['background_color'], _join(path, 'background_color')),
    )
    layers_path = _join(path, 'layers')
    for index, item in enumerate(_list(fields['layers'], layers_path)):
        item_path = f'{layers_path}[{index}]'
        _build(item_path, composition.add_layer, _decode_layer(item, item_path))
    return composition


def project_from_dict(data: Any) -> Project:
    """Build a ``Project`` from its JSON-compatible representation.

    Raises ``ProjectFormatError`` if ``data`` is not a valid version 1
    ``aemvp`` project.
    """
    if not isinstance(data, dict):
        raise _error('', f'expected a JSON object, got {_json_type(data)}')
    if data.get('format') != PROJECT_FORMAT:
        raise _error('format', f'expected {PROJECT_FORMAT!r}, got {data.get("format")!r}')
    version = data.get('version')
    if isinstance(version, bool) or not isinstance(version, int):
        raise _error('version', f'expected an integer, got {_json_type(version)}')
    if version != PROJECT_VERSION:
        raise _error('version', f'unsupported version {version} (supported: {PROJECT_VERSION})')

    fields = _object(data, '', _PROJECT_KEYS)
    project = _build('name', Project, name=fields['name'])
    for index, item in enumerate(_list(fields['compositions'], 'compositions')):
        item_path = f'compositions[{index}]'
        _build(item_path, project.add_composition, _decode_composition(item, item_path))
    return project


def _reject_constant(name: str) -> None:
    raise ProjectFormatError(f'invalid JSON number {name}')


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectFormatError(f'duplicate key {key!r}')
        result[key] = value
    return result


def project_from_json(text: str) -> Project:
    """Parse project JSON text. Raises ``ProjectFormatError``."""
    try:
        data = json.loads(text, parse_constant=_reject_constant,
                          object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise ProjectFormatError(f'invalid JSON: {error}') from error
    return project_from_dict(data)


def load_project(path: str | os.PathLike[str]) -> Project:
    """Read a project file written by ``save_project``.

    Raises ``ProjectFormatError`` for invalid content and ``OSError`` if
    the file cannot be read.
    """
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    return project_from_json(text)
