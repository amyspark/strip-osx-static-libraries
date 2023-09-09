#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2023 Amyspark
# SPDX-License-Ref: MIT

from argparse import ArgumentParser
from pathlib import Path
import re
import shutil
import subprocess
from subprocess import CalledProcessError
import sys
import tempfile


def get_nm(args: ArgumentParser) -> Path:
    exe: Path | None = args.nm

    if not exe:
        alt_exe = shutil.which('nm')
        if not alt_exe:
            raise RuntimeError('A valid llvm-nm executable is needed')
        else:
            return Path(alt_exe)

    return args.nm


def get_exe(name: str) -> Path:
    exe = shutil.which(name)

    if not exe:
        raise RuntimeError(f'A valid {name} executable is needed')

    return Path(exe)


if __name__ == '__main__':
    parser = ArgumentParser(
        description='Manually strip Mach-O archive libraries',
        epilog='See https://developer.apple.com/documentation/xcode/build-settings-reference'
    )
    parser.add_argument('source', type=Path)
    parser.add_argument('dest', type=Path)
    parser.add_argument('--pattern', type=str,
                        help='Wildcard pattern of symbols to preserve')
    parser.add_argument('--nm', metavar='NM_PATH', type=Path,
                        help='Path to the llvm-nm executable')

    args = parser.parse_args()

    nm = get_nm(args)
    ld = get_exe('ld')

    source: Path = args.source
    dest: Path = args.dest

    # Only global symbols
    # Only symbol names
    # Use portable output format
    # Skip undefined symbols
    # Write pathname of the object file
    manifest = subprocess.run(
        [nm, '-gjPUA', source.absolute()], check=True, capture_output=True, text=True)

    # Now we need to match the symbols to the pattern

    # Here's the catch: Apple strip is silly enough to be unable to
    # -undefined suppress a .o because of the -two_level_namespace being
    # the default post-10.1. So we need to determine which objects have
    # matching symbols. The rest can be safely stripped.

    # The symbol listing format is as follows:
    # ./libgstrswebrtc.a[gstrswebrtc-3a8116aacab254c2.2u9b7sba8k2fvc9v.rcgu.o]: _gst_plugin_rswebrtc_get_desc T 500 0
    # Field 1 has the object name between brackets.
    # Field 2 is the symbol name.

    symbol_pattern = re.compile(args.pattern)
    file_pattern = re.compile(r'^.+\[(.+)\]:$')

    with tempfile.TemporaryDirectory(prefix='cerbero') as tmp:
        # List those symbols that will be kept
        symbols_to_keep: set[str] = set()

        for line in manifest.stdout.splitlines():
            data = line.split(' ')
            object_file = file_pattern.match(data[0])[1]
            symbol = data[1]

            if symbol_pattern.match(symbol):
                symbols_to_keep.add(symbol)

        module = source.with_suffix('.symbols')

        with module.open('w', encoding='utf-8') as f:
            f.write('# Stripped by Cerbero\n')

            for symbol in symbols_to_keep:
                f.write(f'{symbol}\n')

        print(f'Symbols to preserve:')
        for symbol in symbols_to_keep:
            print(f'\t{symbol}')

        # Unpack archive
        print(f"Unpacking {source.absolute()} with ar")
        subprocess.run([get_exe('ar'), 'xv', source.absolute()],
                       cwd=tmp, capture_output=True, text=True, check=True)

        # Now everything is flat in the pwd
        print('Performing Single-Object Prelinking')
        prelinked_obj = (Path(tmp) / source.name).with_suffix('.prelinked.o')
        try:
            subprocess.run(f'{get_exe("ld")} -r -exported_symbols_list {module} -o {prelinked_obj} *.o',
                           cwd=tmp, shell=True, capture_output=True, text=True, check=True)
        except CalledProcessError as e:
            print(e.stderr, file=sys.stderr)
            raise e

        # With the stripping done, all files now need to be rearchived
        print(f'Repacking library to {dest.absolute()}')
        try:
            subprocess.run([get_exe('libtool'), '-static', '-o', dest.absolute(),
                           prelinked_obj.absolute()], capture_output=True, text=True, check=True)
        except CalledProcessError as e:
            print(e.stderr, file=sys.stderr)
            raise e
