"""Build the isolated WIN-03 runtime from verified local archives."""

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import shutil
import stat
import struct
import zipfile


ROOT = Path(__file__).resolve().parents[2]
LOCK = Path(__file__).with_name('runtime_lock.json')
NATIVE_SUFFIXES = {'.dll', '.exe', '.pyd'}
AMD64 = 0x8664


def sha256(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def check_input(path, item):
    if path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
        raise ValueError(f"Input differs from runtime lock: {item['file']}")


def extract(archive, destination):
    with zipfile.ZipFile(archive) as package:
        entries = set()
        for member in package.infolist():
            relative = PureWindowsPath(member.filename)
            casefold_name = relative.as_posix().casefold()
            if (not relative.parts or relative.anchor or '..' in relative.parts
                    or ':' in member.filename or casefold_name in entries
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError(f'Unsafe package entry: {member.filename}')
            entries.add(casefold_name)
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)


def pe_machine(path):
    with path.open('rb') as file:
        header = file.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ValueError(f'Missing DOS header: {path.name}')
        file.seek(struct.unpack_from('<I', header, 60)[0])
        magic, machine = struct.unpack('<4sH', file.read(6))
    if magic != b'PE\0\0' or machine != AMD64:
        raise ValueError(f'Expected AMD64 PE: {path.name}')
    return 'AMD64'


def inventory(directory):
    files = []
    for path in sorted(directory.rglob('*'), key=lambda entry: entry.as_posix()):
        if not path.is_file():
            continue
        entry = {'path': path.relative_to(directory).as_posix(),
                 'bytes': path.stat().st_size, 'sha256': sha256(path)}
        if path.suffix.casefold() in NATIVE_SUFFIXES:
            entry['pe_machine'] = pe_machine(path)
        files.append(entry)
    return files


def build(downloads, output):
    lock = json.loads(LOCK.read_bytes())
    for item in lock['files']:
        check_input(downloads / item['file'], item)
    if not output.is_relative_to(ROOT / 'tmp') or output == ROOT / 'tmp':
        raise ValueError('Choose a new output directory under this checkout’s tmp/')
    output.mkdir(parents=True)
    runtime = output / 'runtime'
    for item in lock['files']:
        source = downloads / item['file']
        if item['role'] == 'runtime':
            extract(source, runtime)
        elif item['role'] == 'sbom':
            shutil.copyfile(source, runtime / 'CPython-SBOM.spdx.json')
        else:
            extract(source, runtime / 'packages')

    major, minor, _ = lock['python'].split('.')
    stem = f'python{major}{minor}'
    isolated_path = runtime / f'{stem}._pth'
    with isolated_path.open('w', encoding='ascii', newline='\n') as file:
        file.write(f'{stem}.zip\n.\npackages\n')

    files = inventory(runtime)
    manifest = {'schema': 'win03-runtime-build-1', 'lock_sha256': sha256(LOCK), 'files': files}
    receipt = output / 'runtime-manifest.json'
    with receipt.open('w', encoding='utf-8', newline='\n') as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)
        file.write('\n')
    print(f"{len(files)} files, {sum('pe_machine' in item for item in files)} AMD64 PE files; SHA-256 {sha256(receipt)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloads', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.downloads.resolve(), args.out.resolve())


if __name__ == '__main__':
    main()
