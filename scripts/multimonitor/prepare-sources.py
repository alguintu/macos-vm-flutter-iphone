#!/usr/bin/env python3
"""Fetch the pinned experimental sources into a NEW directory and apply verified patches."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / 'patches/multimonitor'


def prepare(destination):
    manifest = json.loads((PATCHES / 'manifest.json').read_text())
    for entry in manifest.values():
        patch = PATCHES / entry['patch']
        if hashlib.sha256(patch.read_bytes()).hexdigest() != entry['patch_sha256']:
            raise ValueError('Patch checksum mismatch: ' + patch.name)
    destination.mkdir(parents=True, exist_ok=False)
    for name, relative in [('reims_vgpu', 'reims-vgpu'), ('qemu', 'reims-vgpu/vendor/qemu')]:
        entry = manifest[name]
        repo = destination / relative
        repo.mkdir(parents=True, exist_ok=True)
        def git(*args):
            subprocess.run(['git', '-C', str(repo), *args], check=True)
        git('init')
        git('remote', 'add', 'origin', entry['url'])
        git('fetch', '--depth=1', 'origin', entry['revision'])
        git('checkout', '--detach', 'FETCH_HEAD')
        actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != entry['revision']:
            raise ValueError('Source revision mismatch')
        git('apply', '--check', str(PATCHES / entry['patch']))
        git('apply', str(PATCHES / entry['patch']))
    print('Prepared sources only; build using docs/multimonitor.md:', destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=lambda s: Path(s).expanduser().resolve())
    prepare(parser.parse_args().destination)
