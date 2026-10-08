pytest_python = import('python').find_installation('python3',
  modules: ['pytest'],
  required: false,
)

if pytest_python.found()
  test('Core tests', pytest_python,
    args: ['-m', 'pytest', '-q', '-p', 'no:cacheprovider'],
    workdir: meson.project_source_root(),
  )
endif
