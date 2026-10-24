"""Offline integrity checks for the published shader reproduction package."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ShaderPackageTests(unittest.TestCase):
    def test_patch_integrity_and_scope(self):
        directory = ROOT / 'patches/flutter-shaders'
        manifest = json.loads((directory / 'manifest.json').read_text())
        for entry in manifest.values():
            self.assertRegex(entry['revision'], r'^[0-9a-f]{40}$')
            self.assertTrue(entry['url'].startswith('https://github.com/steelbrain/'))
        entry = manifest['metal2vulkan']
        patch = directory / entry['patch']
        self.assertEqual(hashlib.sha256(patch.read_bytes()).hexdigest(),
                         entry['patch_sha256'])
        stats = subprocess.check_output(
            ['git', 'apply', '--numstat', str(patch)], cwd=ROOT, text=True)
        self.assertEqual({line.split('\t')[2] for line in stats.splitlines()}, {
            'crates/metal2vulkan-air/src/abi/module.rs',
            'crates/metal2vulkan/src/memory/plan.rs',
            'crates/metal2vulkan/src/memory/plan/tests.rs',
            'crates/metal2vulkan/src/memory/window.rs',
        })
