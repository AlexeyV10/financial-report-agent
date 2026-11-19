"""Verify the private stock runtime against the existing fictional WIN-02 PDF."""

import argparse
from contextlib import closing
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import ssl
import sys


ROOT = Path(__file__).resolve().parents[2]
RENDER_BASELINE = ROOT / 'evaluation/windows_02_2026-11-11/host-diagnostic.json'


def loaded_module_location(name, runtime):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    handle = kernel.GetModuleHandleW(name)
    if not handle:
        raise RuntimeError(f'Expected loaded Windows module: {name}')
    path_buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetModuleFileNameW(handle, path_buffer, len(path_buffer))
    if not 0 < length < len(path_buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    path = Path(path_buffer.value).resolve()
    if path.is_relative_to(runtime):
        return 'private_runtime'
    return 'system32' if path.parent == (Path(os.environ['SystemRoot']) / 'System32').resolve() else 'outside_runtime'


def verify_fts5():
    with closing(sqlite3.connect(':memory:')) as database:
        database.execute('CREATE VIRTUAL TABLE smoke USING fts5(body)')
        database.execute('INSERT INTO smoke VALUES (?)', ('own fixture only',))
        rows = database.execute('SELECT body FROM smoke WHERE smoke MATCH ?', ('fixture',)).fetchall()
    if rows != [('own fixture only',)]:
        raise RuntimeError('FTS5 smoke query returned an unexpected result')


def probe(demo):
    runtime = Path(sys.prefix).resolve()
    lock = json.loads(Path(__file__).with_name('runtime_lock.json').read_bytes())
    if (sys.version.split()[0] != lock['python'] or ctypes.sizeof(ctypes.c_void_p) != 8
            or not (runtime / 'CPython-SBOM.spdx.json').is_file()
            or not sys.flags.isolated or not sys.flags.no_user_site
            or not all(Path(value).resolve().is_relative_to(runtime) for value in sys.path)):
        raise RuntimeError('Run this probe with the locked, isolated Windows x64 runtime')

    expected = json.loads(RENDER_BASELINE.read_bytes())
    source = demo / 'own-demo-v1.pdf'
    if source.stat().st_size != 2327 or hashlib.sha256(source.read_bytes()).hexdigest() != expected['source_sha']:
        raise ValueError('The PDF is not the pinned fictional fixture')

    verify_fts5()
    import PIL
    import pypdfium2
    if PIL.__version__ != '13.0.0' or str(pypdfium2.PYPDFIUM_INFO) != '5.15.2':
        raise RuntimeError('The image and PDF modules do not match the lock')
    for module in (PIL, pypdfium2):
        if not Path(module.__file__).resolve().is_relative_to(runtime / 'packages'):
            raise RuntimeError('Expected packaged modules in the locked runtime')

    # These are explicit, trusted checkout imports for this test only.
    sys.path.append(str(ROOT / 'spikes/windows_01'))
    from adapter import DemoAdapter
    from renderer import PdfiumRenderer

    adapter = DemoAdapter(demo)
    answer = adapter.run('win03-runtime-probe')
    display = answer['financial_result']['display_value']
    render_metadata = []
    for rotation in (0, 90, 180, 270):
        frame = PdfiumRenderer().render(adapter, 2, rotation, 2)
        render_metadata.append({key: value for key, value in frame.items() if key != 'png'})
    if display != expected['display'] or render_metadata != expected['renders']:
        raise RuntimeError('Calculation or source rectangle changed')

    libraries = ('python314.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'ucrtbase.dll',
                 'sqlite3.dll', 'libcrypto-3.dll', 'libssl-3.dll', 'pdfium.dll')
    native = {name: loaded_module_location(name, runtime) for name in libraries}
    for name, location in native.items():
        expected_location = 'system32' if name == 'ucrtbase.dll' else 'private_runtime'
        if location != expected_location:
            raise RuntimeError(f'Unexpected origin of loaded module: {name} ({location})')
    return {'schema': 'win03-runtime-probe-1', 'python': lock['python'], 'platform': 'Windows AMD64',
            'isolated': sys.flags.isolated, 'no_user_site': sys.flags.no_user_site,
            'sqlite': sqlite3.sqlite_version, 'fts5': True, 'openssl': ssl.OPENSSL_VERSION,
            'pillow': PIL.__version__, 'pypdfium2': str(pypdfium2.PYPDFIUM_INFO),
            'pdfium': str(pypdfium2.PDFIUM_INFO), 'native_modules': native,
            'display': display, 'source_sha256': expected['source_sha'],
            'renders': render_metadata, 'model_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.demo.resolve()), indent=2))


if __name__ == '__main__':
    main()
