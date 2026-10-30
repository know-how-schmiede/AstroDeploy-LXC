#!/usr/bin/python3
"""Runs only as the build user. Never import this in the root orchestrator."""
import json
from pathlib import Path
import subprocess
import sys


def check(root, subdir):
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
    if 'astro' not in deps or '@astrojs/node' not in deps:
        raise ValueError('Astro und @astrojs/node müssen in package.json stehen')


if __name__ == '__main__':
    if sys.argv[1] == 'check':
        check(sys.argv[2], sys.argv[3])
    else:
        for command in (['npm', 'ci', '--include=dev', '--engine-strict'], ['npm', 'run', 'build']):
            subprocess.run(command, check=True)
