"""Project-local Inkscape CLI adapter; no model execution or global PATH edits."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'planning/graphics_toolchain.json'


def configuration():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def local_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def invoke(executable, arguments, timeout=120):
    profile = ROOT / '<未收录-下载缓存>/graphics_tools/profile'
    profile.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['INKSCAPE_PROFILE_DIR'] = str(profile)
    for variable, folder in [('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache'),
                             ('XDG_CONFIG_HOME', 'config')]:
        location = ROOT / '<未收录-下载缓存>/graphics_tools' / folder
        location.mkdir(parents=True, exist_ok=True)
        env[variable] = str(location)
    return subprocess.run([str(executable), *map(str, arguments)], cwd=ROOT,
                          env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


def resolve_inkscape():
    candidates = []
    if os.environ.get('INKSCAPE_PATH'):
        candidates.append(os.environ['INKSCAPE_PATH'])
    candidates.extend(configuration()['inkscape']['cli_candidates'])
    if shutil.which('inkscape'):
        candidates.append(shutil.which('inkscape'))
    failures = []
    for value in dict.fromkeys(candidates):
        executable = local_path(value)
        if not executable.is_file():
            continue
        try:
            result = invoke(executable, ['--version'], timeout=30)
            version = (result.stdout + result.stderr).strip()
            if result.returncode == 0 and 'Inkscape' in version:
                return executable, version
            failures.append(f'{executable}: exit {result.returncode}: {version}')
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f'{executable}: {exc}')
    raise RuntimeError('No callable Inkscape CLI found. Set INKSCAPE_PATH to inkscape.com.\n'
                       + '\n'.join(failures))


def export_svg(source, destination, dpi=300, text_to_path=False, overwrite=False):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if source.suffix.lower() != '.svg':
        raise ValueError('Input must be an SVG master.')
    kind = destination.suffix.lower().lstrip('.')
    if kind not in {'png', 'pdf'}:
        raise ValueError('Output must be PNG or PDF; retain the original SVG as the editable master.')
    if text_to_path and kind != 'pdf':
        raise ValueError('--text-to-path is for PDF export.')
    if not 72 <= dpi <= 1200:
        raise ValueError('DPI must be between 72 and 1200.')
    if destination.exists() and not overwrite:
        raise FileExistsError(f'Output exists; use --overwrite explicitly: {destination}')
    executable, version = resolve_inkscape()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Render to a new file before replacing any explicitly selected output.
    with tempfile.TemporaryDirectory(prefix='inkscape-export-', dir=destination.parent) as work:
        temporary = Path(work) / ('rendered.' + kind)
        args = [str(source), '--export-area-page', '--export-type=' + kind,
                '--export-filename=' + str(temporary), '--export-dpi=' + str(dpi)]
        if text_to_path:
            args.append('--export-text-to-path')
        result = invoke(executable, args)
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError(f'Inkscape export failed ({result.returncode}):\n'
                               + result.stdout + result.stderr)
        # Moving directly out of TemporaryDirectory retains its restrictive
        # Windows ACL. Create a normal sibling instead: Windows inherits the
        # destination directory's ACL, while POSIX uses normal file creation.
        # Copy bytes only: copy2/copystat would also transfer unwanted metadata.
        staging = destination.parent / ('.inkscape-publish-' + uuid.uuid4().hex + '.tmp')
        staging_created = False
        try:
            with staging.open('xb') as published:
                staging_created = True
                with temporary.open('rb') as rendered:
                    shutil.copyfileobj(rendered, published)
                published.flush()
                os.fsync(published.fileno())
            if destination.exists() and not overwrite:
                raise FileExistsError(f'Output appeared during export: {destination}')
            # Both paths are now on the destination filesystem, and readers see
            # either the previous complete output or the new complete output.
            os.replace(staging, destination)
        finally:
            if staging_created:
                staging.unlink(missing_ok=True)
    return {'renderer': version, 'input': str(source), 'output': str(destination),
            'bytes': destination.stat().st_size, 'dpi': dpi,
            'text_to_path': text_to_path, 'warnings': result.stderr.strip()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('doctor', help='Check the configured Inkscape CLI and other local tool paths.')
    export = commands.add_parser('export', help='Render an SVG master to PNG or PDF without editing it.')
    export.add_argument('source')
    export.add_argument('--output', '-o', required=True)
    export.add_argument('--dpi', type=int, default=300)
    export.add_argument('--text-to-path', action='store_true')
    export.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    if args.action == 'doctor':
        executable, version = resolve_inkscape()
        report = {'inkscape': {'path': str(executable), 'version': version},
                  'configured_paths': {name: {'path': value, 'exists': local_path(value).exists()}
                    for name, value in configuration()['support_paths'].items()}}
    else:
        report = export_svg(args.source, args.output, args.dpi, args.text_to_path, args.overwrite)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
