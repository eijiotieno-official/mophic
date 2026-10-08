import copy
import json

import pytest

from core.easing import EASE_IN, EASE_IN_OUT, EASE_OUT, LINEAR, cubic_bezier
from core.layers import ImageLayer, Layer, ShapeLayer, SolidLayer, TextLayer
from core.project import Composition, Project
from core.properties import Color, Point, Scale
from core.serialization import (ProjectFormatError, layer_to_dict,
                                load_project, project_from_dict,
                                project_from_json, project_to_dict,
                                project_to_json, save_project)


def build_project():
    project = Project(name='Example ✓')
    main = Composition(name='Main', width=1280, height=720, fps=24.0, duration=5.0,
                       background_color=Color(0.1, 0.2, 0.3, 1.0))
    project.add_composition(main)
    project.add_composition(Composition(name='Second', fps=30000 / 1001))

    background = SolidLayer(name='Background', color=Color(0.05, 0.05, 0.05, 1.0))
    box = ShapeLayer(name='Box', shape_type='rectangle', width=200, height=120,
                     fill_color=Color(1, 0.5, 0, 1), stroke_color=Color(0, 0, 0, 0.5),
                     stroke_width=3, position=Point(640, 360), anchor_point=Point(10, 5))
    circle = ShapeLayer(name='Circle', shape_type='ellipse', width=80, height=80,
                        fill_color=None, stroke_color=Color(1, 1, 1, 1), stroke_width=2)
    line = ShapeLayer(name='Line', shape_type='line', start=Point(-50, 0), end=Point(50, 0),
                      stroke_color=Color(1, 1, 1, 1), stroke_width=4, visible=False)
    title = TextLayer(name='Title', text='Hello, "world"\nline two', font_family='Cantarell',
                      font_size=96, color=Color(1, 1, 1, 1), alignment='center')
    image = ImageLayer(name='Logo', path='/home/user/Pictures/logo é.png', opacity=0.8)

    for layer in (background, box, circle, line, title, image):
        main.add_layer(layer)

    title.position.set_keyframe(0.0, Point(0, 360), EASE_OUT)
    title.position.set_keyframe(1.0, Point(640, 360), cubic_bezier(0.25, 0.1, 0.25, 1.0))
    title.position.set_keyframe(2 / 3, Point(320, 360), EASE_IN_OUT)
    title.opacity.set_keyframe(0.0, 0.0, EASE_IN)
    title.opacity.set_keyframe(0.5, 1.0)
    box.scale.set_keyframe(1 / 24, Scale(50, 50), LINEAR)
    box.scale.set_keyframe(2.0, Scale(150, 120))
    box.rotation.set_keyframe(0.0, -45.0)
    box.rotation.set_keyframe(4.999, 720.0, cubic_bezier(0.9, -0.5, 0.1, 1.5))
    return project


def test_round_trip_preserves_everything(tmp_path):
    project = build_project()
    path = tmp_path / 'example.aemvp.json'
    save_project(project, path)
    loaded = load_project(path)
    assert project_to_dict(loaded) == project_to_dict(project)

    main = loaded.compositions[0]
    original_main = project.compositions[0]
    assert [layer.id for layer in main.layers] == [layer.id for layer in original_main.layers]
    assert [type(layer) for layer in main.layers] == [type(layer) for layer in original_main.layers]
    assert main.id == original_main.id
    title = main.layers[4]
    assert title.position.value_at(0.5) == original_main.layers[4].position.value_at(0.5)
    assert title.position.keyframes[2].easing == cubic_bezier(0.25, 0.1, 0.25, 1.0)


def test_round_trip_preserves_exact_float_times(tmp_path):
    project = build_project()
    path = tmp_path / 'p.json'
    save_project(project, path)
    loaded = load_project(path)
    times = [k.time for k in loaded.compositions[0].layers[1].scale.keyframes]
    assert times == [1 / 24, 2.0]
    assert loaded.compositions[1].fps == 30000 / 1001


def test_save_is_deterministic(tmp_path):
    project = build_project()
    first, second = tmp_path / 'a.json', tmp_path / 'b.json'
    save_project(project, first)
    save_project(load_project(first), second)
    assert first.read_bytes() == second.read_bytes()
    assert project_to_json(project) == first.read_text(encoding='utf-8')


def test_file_is_readable_versioned_json(tmp_path):
    path = tmp_path / 'p.json'
    save_project(build_project(), path)
    text = path.read_text(encoding='utf-8')
    assert text.startswith('{\n  "format": "aemvp",\n  "version": 1,\n  "name": ')
    assert text.endswith('}\n')
    assert 'Example ✓' in text
    data = json.loads(text)
    assert list(data) == ['format', 'version', 'name', 'compositions']
    layer = data['compositions'][0]['layers'][4]
    assert layer['type'] == 'text'
    assert list(layer)[:9] == ['id', 'type', 'name', 'visible', 'anchor_point',
                               'position', 'scale', 'rotation', 'opacity']
    assert layer['position']['keyframes'][0] == {
        'time': 0.0, 'value': {'x': 0.0, 'y': 360.0}, 'easing': {'type': 'ease-out'},
    }
    assert layer['position']['keyframes'][2]['easing'] == {
        'type': 'cubic-bezier', 'x1': 0.25, 'y1': 0.1, 'x2': 0.25, 'y2': 1.0,
    }


def test_layer_types_use_discriminators_not_class_names():
    data = project_to_dict(build_project())
    types = [layer['type'] for layer in data['compositions'][0]['layers']]
    assert types == ['solid', 'shape', 'shape', 'shape', 'text', 'image']


def test_save_replaces_existing_file_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / 'p.json'
    path.write_text('old', encoding='utf-8')
    path.chmod(0o640)
    save_project(build_project(), path)
    assert load_project(path).name == 'Example ✓'
    assert path.stat().st_mode & 0o777 == 0o640
    assert [p.name for p in tmp_path.iterdir()] == ['p.json']


def test_failed_save_removes_its_temporary_file(tmp_path):
    target = tmp_path / 'occupied'
    target.mkdir()
    with pytest.raises(OSError):
        save_project(build_project(), target)
    assert [p.name for p in tmp_path.iterdir()] == ['occupied']


def test_serializing_unknown_layer_class_fails():
    class VideoLayer(Layer):
        layer_type = 'video'

    with pytest.raises(TypeError):
        layer_to_dict(VideoLayer(name='Video'))


def test_empty_project_round_trip():
    project = Project(name='Empty')
    assert project_to_dict(project_from_dict(project_to_dict(project))) == project_to_dict(project)


# Strict loading


def valid_data():
    return project_to_dict(build_project())


def expect_error(data, fragment):
    with pytest.raises(ProjectFormatError) as info:
        project_from_dict(data)
    assert fragment in str(info.value)
    return info.value


def test_wrong_format_is_rejected():
    data = valid_data()
    data['format'] = 'other'
    expect_error(data, 'format')


def test_missing_format_is_rejected():
    data = valid_data()
    del data['format']
    expect_error(data, 'format')


@pytest.mark.parametrize('version', [2, 0, '1', 1.0, True, None])
def test_wrong_version_is_rejected(version):
    data = valid_data()
    data['version'] = version
    expect_error(data, 'version')


def test_newer_version_is_reported_as_unsupported():
    data = valid_data()
    data['version'] = 2
    expect_error(data, 'unsupported version 2')


def test_unknown_layer_type_is_rejected():
    data = valid_data()
    data['compositions'][0]['layers'][1]['type'] = 'video'
    expect_error(data, "compositions[0].layers[1].type: unknown layer type 'video'")


def test_missing_key_is_rejected():
    data = valid_data()
    del data['compositions'][0]['layers'][4]['font_size']
    expect_error(data, "compositions[0].layers[4]: missing key 'font_size'")


def test_unknown_key_is_rejected():
    data = valid_data()
    data['compositions'][0]['extra'] = 1
    expect_error(data, "compositions[0]: unknown key 'extra'")


def test_key_from_other_layer_type_is_rejected():
    data = valid_data()
    data['compositions'][0]['layers'][0]['path'] = '/x.png'
    expect_error(data, "unknown key 'path'")


def test_invalid_keyframe_time_reports_its_path():
    data = valid_data()
    data['compositions'][0]['layers'][4]['opacity']['keyframes'][1]['time'] = -1
    expect_error(data, 'compositions[0].layers[4].opacity.keyframes[1].time')


def test_duplicate_keyframe_time_is_rejected():
    data = valid_data()
    keyframes = data['compositions'][0]['layers'][4]['opacity']['keyframes']
    keyframes.append(copy.deepcopy(keyframes[0]))
    expect_error(data, 'duplicate keyframe time')


def test_unknown_easing_is_rejected():
    data = valid_data()
    data['compositions'][0]['layers'][4]['opacity']['keyframes'][0]['easing'] = {'type': 'bounce'}
    expect_error(data, "unknown easing kind 'bounce'")


def test_cubic_bezier_missing_point_is_rejected():
    data = valid_data()
    del data['compositions'][0]['layers'][4]['position']['keyframes'][2]['easing']['y2']
    expect_error(data, "missing key 'y2'")


@pytest.mark.parametrize('mutate, fragment', [
    (lambda d: d['compositions'][0].update(width=0), 'compositions[0]: width must be > 0'),
    (lambda d: d['compositions'][0].update(width=1280.0), 'width must be an int'),
    (lambda d: d['compositions'][0].update(fps=-1), 'fps must be > 0'),
    (lambda d: d['compositions'][0]['background_color'].update(r=2),
     'compositions[0].background_color'),
    (lambda d: d['compositions'][0]['layers'][5]['opacity'].update(value=1.5),
     'compositions[0].layers[5]'),
    (lambda d: d['compositions'][0]['layers'][4]['position'].update(value=[0, 0]),
     'compositions[0].layers[4].position.value: expected an object'),
    (lambda d: d['compositions'][0]['layers'][4]['rotation'].update(value='0'),
     'compositions[0].layers[4].rotation.value'),
    (lambda d: d['compositions'][0]['layers'][4].update(alignment='justify'), 'alignment'),
    (lambda d: d['compositions'][0]['layers'][4].update(visible='yes'), 'visible'),
    (lambda d: d['compositions'][0].update(layers={}), 'compositions[0].layers: expected an array'),
    (lambda d: d['compositions'][0]['layers'].__setitem__(2, 'circle'),
     'compositions[0].layers[2]: expected an object, got string'),
    (lambda d: d['compositions'][0]['layers'][4]['opacity']['keyframes'][0].update(easing='linear'),
     'compositions[0].layers[4].opacity.keyframes[0].easing: expected an object'),
])
def test_invalid_values_are_rejected_with_location(mutate, fragment):
    data = valid_data()
    mutate(data)
    expect_error(data, fragment)


def test_duplicate_layer_ids_are_rejected():
    data = valid_data()
    layers = data['compositions'][0]['layers']
    layers[1]['id'] = layers[0]['id']
    expect_error(data, 'compositions[0].layers[1]: a layer with id')


def test_duplicate_composition_ids_are_rejected():
    data = valid_data()
    data['compositions'][1]['id'] = data['compositions'][0]['id']
    expect_error(data, 'compositions[1]: a composition with id')


def test_non_object_root_is_rejected():
    expect_error([], 'expected a JSON object')


def test_nan_is_rejected_on_load():
    text = project_to_json(build_project()).replace('"fps": 24.0', '"fps": NaN', 1)
    with pytest.raises(ProjectFormatError, match='NaN'):
        project_from_json(text)


def test_invalid_json_is_rejected():
    with pytest.raises(ProjectFormatError, match='invalid JSON'):
        project_from_json('{"format": ')


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(ProjectFormatError, match='duplicate key'):
        project_from_json('{"format": "aemvp", "format": "aemvp"}')


def test_load_missing_file_raises_os_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / 'missing.json')


def test_format_error_is_a_value_error():
    assert issubclass(ProjectFormatError, ValueError)
