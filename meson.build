project('xxx', 'c')

x = shared_library('xxx', files('test.c', 'test2.c'), gnu_symbol_visibility: 'inlineshidden', link_args: ['-r'], name_suffix: 'a')

y = static_library('xxx2', files('test.c', 'test2.c'), gnu_symbol_visibility: 'inlineshidden')

z = custom_target(
    'xxx3',
    command: [find_program('libtool'), '-static', '-o', '@OUTPUT@', '@INPUT@'],
    input: x,
    output: 'libxxx3.a',
    install: true,
    install_dir: 'lib',
)
