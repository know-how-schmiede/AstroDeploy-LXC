#!/usr/bin/python3
"""Runs only as the build user. Never import this in the root orchestrator."""
import json
from pathlib import Path
import re
import subprocess
import sys


class BuildError(Exception):
    """Only predefined stage codes cross the build/root boundary."""


def supports_container_build(script):
    """npm appends --config to the final command; never bypass preceding checks."""
    task = r'(?:npm\s+run\s+[A-Za-z0-9_:-]+|astro\s+check)'
    return isinstance(script, str) and bool(re.fullmatch(
        rf'(?:{task}\s*&&\s*)*astro\s+build', script.strip()))


def check(root, subdir, prepare=False, mode='server'):
    root = Path(root).resolve()
    project = root / subdir
    if project.is_symlink() or not project.resolve().is_relative_to(root):
        raise ValueError('Projektpfad verlässt das Repository')
    if (root / '.gitmodules').exists() or list(root.rglob('.lfsconfig')):
        raise ValueError('Submodule/Git LFS werden nicht unterstützt')
    for attrs in root.rglob('.gitattributes'):
        if 'filter=lfs' in attrs.read_text():
            raise ValueError('Git LFS wird nicht unterstützt')
    package = json.loads((project / 'package.json').read_text())
    if package.get('workspaces') or not (project / 'package-lock.json').is_file():
        raise ValueError('npm-Workspace nicht unterstützt oder package-lock.json fehlt')
    deps = package.get('dependencies', {}) | package.get('devDependencies', {})
    if 'astro' not in deps:
        raise ValueError('Dies ist kein unterstütztes Astro-Projekt: astro fehlt in package.json')
    if '@astrojs/node' not in deps and not prepare and mode == 'server':
        raise ValueError('Node-Adapter fehlt. Container-Vorbereitung im Setup aktivieren oder @astrojs/node im Projekt ergänzen.')
    if prepare and mode == 'server' and not supports_container_build(package.get('scripts', {}).get('build', '')):
        raise ValueError('Container-Vorbereitung benötigt ein Buildskript mit abschließendem "astro build". '
                         'Davor sind "npm run AUFGABE &&" und "astro check &&" möglich. '
                         'Für andere Buildskripte einen fertigen Node-Adapter verwenden und die Vorbereitung deaktivieren.')
    return package


def npm(project, args, stage):
    try:
        subprocess.run(['npm', *args], cwd=project, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        raise BuildError(stage) from None


def prepare_configuration(project):
    """Overlay the existing object; never rewrite its source or run it as root."""
    candidates = [project / ('astro.config.' + ext) for ext in ('mjs', 'js', 'ts', 'mts', 'cjs', 'cts')]
    configs = [path for path in candidates if path.exists()]
    overlay = project / '.astrodeploy.config.mjs'
    if len(configs) > 1 or overlay.exists() or overlay.is_symlink():
        raise BuildError('config')
    original = ('import original from ' + json.dumps('./' + configs[0].name) + ';\n') if configs else 'const original = {};\n'
    overlay.write_text(original + '''import node from '@astrojs/node';
import { fileURLToPath } from 'node:url';
if (!original || typeof original !== 'object' || Array.isArray(original)) {
  throw new Error('AstroDeploy benötigt einen objektbasierten Astro-Konfigurationsexport.');
}
export default {
  ...original,
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  outDir: fileURLToPath(new URL('./dist/', import.meta.url)),
  build: { ...original.build, server: 'server', client: 'client', serverEntry: 'entry.mjs' },
};
''', encoding='utf-8')
    return overlay.name


def build(project, adapter=None, mode='server'):
    npm(project, ['ci', '--include=dev', '--engine-strict'], 'dependencies')
    if adapter and mode == 'server':
        if not re.fullmatch(r'\d+\.\d+\.\d+', adapter):
            raise BuildError('adapter')
        package = json.loads((project / 'package.json').read_text())
        deps = package.get('dependencies', {}) | package.get('devDependencies', {})
        if '@astrojs/node' not in deps:
            astro_package = project / 'node_modules/astro/package.json'
            astro_version = json.loads(astro_package.read_text())['version']
            if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', astro_version):
                raise BuildError('adapter')
            # Pin the existing Astro version as well: adding the adapter must not upgrade Astro.
            npm(project, ['install', '--save-exact', '--include=dev', '--engine-strict', '--strict-peer-deps',
                          '@astrojs/node@' + adapter, 'astro@' + astro_version], 'adapter')
            if json.loads(astro_package.read_text())['version'] != astro_version:
                raise BuildError('adapter')
        overlay = prepare_configuration(project)
        npm(project, ['run', 'build', '--', '--config', overlay], 'build')
    else:
        npm(project, ['run', 'build'], 'build')
    if mode == 'server' and not (project / 'dist/server/entry.mjs').is_file():
        raise BuildError('entry')
    if not (project / 'dist').is_dir() or not any(p.is_file() for p in (project / 'dist').rglob('*')):
        raise BuildError('entry')


if __name__ == '__main__':
    if sys.argv[1] == 'check':
        try:
            check(sys.argv[2], sys.argv[3], prepare=len(sys.argv) > 4 and sys.argv[4] != '-',
                  mode=sys.argv[5] if len(sys.argv) > 5 else 'server')
        except (ValueError, OSError) as error:
            print('Projektprüfung: ' + str(error), file=sys.stderr)
            sys.exit(1)
    else:
        try:
            build(Path.cwd(), sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != '-' else None,
                  mode=sys.argv[3] if len(sys.argv) > 3 else 'server')
        except BuildError as error:
            print('ASTRODEPLOY_ERROR:' + str(error), flush=True)
            sys.exit(1)
        except Exception:
            print('ASTRODEPLOY_ERROR:build', flush=True)
            sys.exit(1)
