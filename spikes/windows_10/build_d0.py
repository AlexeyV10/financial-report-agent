"""Stage the offline D0 Windows package and build its per-user installer."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import stat
import subprocess
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NSIS_SHA256 = 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'
D0_SOURCE_SHA256 = 'ebabc9e49fbde3063f63f98393a271734bc16d0686ea035938ccd8d90db2caf0'
SHELL_EXE = 'ProjectPractice-WIN10.exe'
LAUNCHER_EXE = 'ProjectPractice.exe'
INSTALLER_EXE = 'ProjectPractice-WIN10-D0-setup.exe'
D0_MODULES = ('input_contracts', 'input_binding', 'russian_input', 'service_b', 'service_contracts',
              'd0_service', 'd0_viewer')
D0_FILES = ('report.pdf', 'catalog.json', 'dictionary.json', 'admission.json', 'manifest.json',
            'retrieval_config.json', 'search_lexicon.json')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def add(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def verify_d0_assets(demo):
    manifest = json.loads((demo / 'manifest.json').read_bytes())
    pdf = demo / 'report.pdf'
    if (manifest['schema'] != 'win10-own-fixture-1' or manifest['resource_id'] != 'd0-own-v1'
            or manifest['page'] != 1 or manifest['bytes'] != pdf.stat().st_size
            or manifest['sha256'] != D0_SOURCE_SHA256 or sha(pdf) != D0_SOURCE_SHA256):
        raise ValueError('Expected the reviewed own D0 source')
    for name in D0_FILES[1:]:
        json.loads((demo / name).read_bytes())


def build_tools(archive, out):
    if sha(archive) != NSIS_SHA256:
        raise ValueError('Expected the reviewed NSIS 3.13 ZIP')
    with ZipFile(archive) as installer:
        for member in installer.infolist():
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.filename
                    or ':' in member.filename or path.parts[:1] != ('nsis-3.13',)):
                raise ValueError('Unexpected archive member')
        installer.extractall(out)
    return out / 'nsis-3.13'


def run_build(command, log, *, timeout):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=timeout)
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'{Path(command[0]).name} exited with {result.returncode}; see {log.name}')


def compile_launcher(payload, out):
    framework = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319'
    command = [
        str(framework / 'csc.exe'), '/nologo', '/warnaserror+', '/target:winexe', '/platform:x64',
        '/optimize+', '/codepage:65001', '/main:LaunchD0', '/out:' + str(payload / LAUNCHER_EXE),
        '/win32manifest:' + str(ROOT / 'spikes/windows_01/wpf.manifest'), '/reference:System.Xaml.dll',
    ]
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase'):
        command.append('/reference:' + str(framework / 'WPF' / (name + '.dll')))
    command.append(str(HERE / 'LaunchD0.cs'))
    run_build(command, out / 'launcher-build.log', timeout=30)
    add(payload / (SHELL_EXE + '.config'), payload / (LAUNCHER_EXE + '.config'))
    return sha(framework / 'csc.exe')


def inventory_files(payload):
    records = []
    for path in sorted(payload.rglob('*')):
        attributes = path.stat(follow_symlinks=False)
        if attributes.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Package must contain only ordinary files and directories')
        if stat.S_ISREG(attributes.st_mode):
            records.append({'path': path.relative_to(payload).as_posix(), 'bytes': attributes.st_size,
                            'sha256': sha(path)})
    return records


def nsis_path(relative):
    if any(ch in relative for ch in '"$\r\n\\'):
        raise ValueError('Unsafe filename in package')
    return '"$INSTDIR\\' + relative.replace('/', '\\') + '"'


def nsis_includes(payload, out, inventory):
    names = [nsis_path(item['path']) for item in inventory]
    directories = sorted((path.relative_to(payload) for path in payload.rglob('*') if path.is_dir()),
                         key=lambda path: (-len(path.parts), path.as_posix()))
    directories = [nsis_path(path.as_posix()) for path in directories]
    attributes = out / 'readonly-files.nsh'
    attributes.write_text(''.join(f'SetFileAttributes {name} READONLY\n' for name in names), encoding='utf-8')
    guards = out / 'uninstall-guards.nsh'
    guards.write_text(''.join(f'!insertmacro RejectRedirectedPath {name}\n' for name in directories[::-1] + names),
                      encoding='utf-8')
    uninstall = out / 'uninstall-files.nsh'
    uninstall.write_text(''.join(f'SetFileAttributes {name} NORMAL\nDelete {name}\n' for name in names)
                         + ''.join(f'RMDir {directory}\n' for directory in directories), encoding='utf-8')
    return attributes, guards, uninstall


def smoke(payload, out):
    smoke_root = out / 'Проверка частной среды'
    workspaces = smoke_root / 'workspaces'
    workspaces.mkdir(parents=True)
    app_data = smoke_root / 'AppData'
    app_data.mkdir()
    vault = workspaces / 'Учебный проект'
    cwd = smoke_root / 'Пустой каталог'
    cwd.mkdir()
    command = [str(payload / 'runtime/python.exe'), '-I', '-B', '-X', 'utf8',
               str(payload / 'app/spikes/windows_10/d0_cli.py'), '--install-root', str(payload),
               '--app-data', str(app_data), '--vault', str(vault), '--provision']
    result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=45)
    if result.stderr or result.stdout.count(b'\n') != 1:
        raise RuntimeError(f'Private provisioning smoke failed (code {result.returncode})')
    receipt = json.loads(result.stdout)
    if result.returncode:
        reason = receipt.get('reason', '')
        if type(reason) is not str or re.fullmatch(r'[a-z][a-z0-9_]{0,63}', reason) is None:
            reason = 'unexpected_worker_status'
        raise RuntimeError(f'Private provisioning smoke failed (code {result.returncode}: {reason})')
    if (receipt.get('schema') != 'win10-d0-1' or receipt.get('status') != 'answered'
            or receipt.get('operation') != 'provision' or not (vault / 'workspace.json').is_file()
            or not (vault / 'vault.sqlite3').is_file() or any(cwd.iterdir())):
        raise RuntimeError('Private provisioning smoke did not create the expected isolated project')
    return {'unicode_vault': True, 'private_worker': True, 'cwd_empty': True, 'status': receipt['status']}


def record_build(out, runtime, payload, compiler_sha, inventory, installer_receipt, proof):
    receipt = {
        'schema': 'win10-d0-build-1',
        'python_runtime': json.loads((ROOT / 'spikes/windows_03/runtime_lock.json').read_bytes())['python'],
        'runtime_manifest_sha256': sha(runtime / 'runtime-manifest.json'),
        'nsis_version': '3.13',
        'nsis_archive_sha256': NSIS_SHA256,
        'launcher_compiler_sha256': compiler_sha,
        'installer': installer_receipt,
        'signed': False,
        'install_location': r'%LOCALAPPDATA%\Programs\Проектная практика D0',
        'workspace_location': r'%LOCALAPPDATA%\ProjectPracticeWIN10\workspaces',
        'payload_file_count': len(inventory),
        'payload_bytes': sum(item['bytes'] for item in inventory),
        'payload_manifest_sha256': sha(payload / 'payload.json'),
        'provisioning_smoke': proof,
    }
    write_json(out / 'build-receipt.json', receipt)
    print(json.dumps(receipt, ensure_ascii=True))


def build(args):
    if sys.platform != 'win32':
        raise RuntimeError('This package must be built on Windows')
    out = args.out.resolve()
    scratch = ROOT / 'tmp'
    if out == scratch or not out.is_relative_to(scratch):
        raise ValueError('Use a new output path under this checkout’s tmp directory')
    runtime, legacy_demo, d0_demo, archive = (
        path.resolve(strict=True) for path in (args.runtime_build, args.legacy_demo, args.d0_demo, args.nsis_archive)
    )
    verify_d0_assets(d0_demo)
    out.mkdir(parents=True)
    nsis = build_tools(archive, out / 'tools')
    payload = out / 'payload'
    stage = runpy.run_path(str(ROOT / 'spikes/windows_08/check_shell.py'))
    old, _ = stage['stage_install'](runtime, legacy_demo, payload, executable_name=SHELL_EXE)
    legacy_pdf = legacy_demo / 'own-demo-v1.pdf'
    if sha(legacy_pdf) != old['OWN_PDF_SHA']:
        raise ValueError('Expected the reviewed WIN-01 fictional PDF')
    add(legacy_pdf, payload / 'app/assets/demo/own-demo-v1.pdf')
    for name in D0_FILES:
        add(d0_demo / name, payload / 'app/assets/d0' / name)
    for name in D0_MODULES:
        relative = Path('src/financial_assistant') / (name + '.py')
        add(ROOT / relative, payload / 'app' / relative)
    for relative in ('scripts/extract_pdf_v2.py', 'spikes/windows_10/d0_cli.py'):
        add(ROOT / relative, payload / 'app' / relative)

    licenses = payload / 'licenses'
    add(nsis / 'COPYING', licenses / 'NSIS-COPYING.txt')
    add(runtime / 'runtime-manifest.json', licenses / 'runtime-manifest.json')
    (licenses / 'PROJECT-NOTICE.txt').write_text(
        'Учебная сборка. Лицензия на код проекта пока не выбрана. Оба вымышленных PDF созданы '
        'для проекта и разрешены к распространению. CPython LICENSE.txt и SBOM находятся в runtime, '
        'лицензии библиотек — в runtime/packages, .NET Framework предоставляется Windows.\n',
        encoding='utf-8',
    )
    compiler_sha = compile_launcher(payload, out)

    write_json(payload / 'payload.json', {'schema': 'win10-d0-payload-1',
                                        'files': inventory_files(payload)})
    inventory = inventory_files(payload)
    for item in inventory:
        (payload / item['path']).chmod(stat.S_IREAD)
    proof = smoke(payload, out)
    if inventory_files(payload) != inventory:
        raise RuntimeError('The private provisioning smoke changed installed files')
    readonly, guards, uninstall = nsis_includes(payload, out, inventory)

    installer_receipt = None
    if not args.payload_only:
        installer = out / INSTALLER_EXE
        command = [str(nsis / 'makensis.exe'), '/V4', '/INPUTCHARSET', 'UTF8']
        command.extend(f'/D{name}={path}' for name, path in (
            ('PAYLOAD', payload), ('OUTPUT', installer), ('READONLY_LIST', readonly),
            ('UNINSTALL_GUARD_LIST', guards), ('UNINSTALL_LIST', uninstall),
        ))
        command.append(str(HERE / 'installer.nsi'))
        run_build(command, out / 'installer-build.log', timeout=180)
        installer_receipt = {'name': installer.name, 'bytes': installer.stat().st_size, 'sha256': sha(installer)}

    record_build(out, runtime, payload, compiler_sha, inventory, installer_receipt, proof)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', required=True, type=Path)
    parser.add_argument('--legacy-demo', required=True, type=Path)
    parser.add_argument('--d0-demo', required=True, type=Path)
    parser.add_argument('--nsis-archive', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--payload-only', action='store_true')
    build(parser.parse_args())


if __name__ == '__main__':
    main()
