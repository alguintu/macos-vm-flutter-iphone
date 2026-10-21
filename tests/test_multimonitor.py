import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


wrapper = load('wrapper', 'scripts/multimonitor/qemu-multimonitor')
image = load('image_patch', 'scripts/multimonitor/patch-opencore.py')
usb = load('usb_render', 'scripts/usb-lifecycle/render.py')


class ReproductionTests(unittest.TestCase):
    def config(self):
        return json.loads((ROOT / 'config/multimonitor.json.example').read_text())

    def args(self):
        return ['-name', 'tahoe', '-device', 'apple-gfx-pci,id=gfx',
                '-device', 'apple-gfx-iosurface-pci,id=ios', '-drive',
                'id=opencore,if=none,format=qcow2,file=' + str(Path.home() / '.local/share/reims-ctl/vms/tahoe/opencore.qcow2'),
                '-drive', 'id=disk,if=none,file=/mnt/vms/test.qcow2',
                '-drive', 'id=code,if=none,readonly=on,file=/mnt/vms/code.fd']

    def test_manifest_hashes_and_revisions(self):
        root = ROOT / 'patches/multimonitor'
        for entry in json.loads((root / 'manifest.json').read_text()).values():
            self.assertRegex(entry['revision'], r'^[0-9a-f]{40}$')
            self.assertEqual(hashlib.sha256((root / entry['patch']).read_bytes()).hexdigest(), entry['patch_sha256'])

    def test_wrapper_routes_two_heads_and_snapshots_only_writable_drives(self):
        config = self.config()
        wrapper.validate(config)
        args = wrapper.transform(self.args(), config)
        gfx = json.loads(args[args.index('-device') + 1])
        self.assertEqual(gfx['displays'], 2)
        self.assertEqual(gfx['display-modes'], config['modes'])
        self.assertIn('id=disk,if=none,file=/mnt/vms/test.qcow2,snapshot=on', args)
        self.assertIn('id=code,if=none,readonly=on,file=/mnt/vms/code.fd', args)
        self.assertIn('reims-pointer,chardev=reims-pointer,display=gfx,heads=2', args)
        self.assertIn('id=opencore,if=none,format=raw,file=' + config['opencore'] + ',snapshot=on', args)

    def test_persistent_mode_is_explicit(self):
        config = self.config() | {'snapshot': False}
        self.assertFalse(any('snapshot=on' in x for x in wrapper.transform(self.args(), config)))

    def test_wrong_vm_or_opencore_refused(self):
        for old, new in [('tahoe', 'another-vm'), ('id=opencore,if=none', 'id=opencore,if=ide')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                wrapper.transform([x.replace(old, new) for x in self.args()], self.config())

    def test_duplicate_or_missing_display_refused(self):
        for args in [self.args() + ['-device', 'apple-gfx-pci,id=gfx'], self.args()[0:2] + self.args()[4:]]:
            with self.assertRaises(ValueError):
                wrapper.transform(args, self.config())

    def test_unsafe_paths_modes_and_snapshot_types_refused(self):
        for key, value in [('opencore', '/tmp/a,b'), ('qemu', 'relative'), ('socket_dir', '/' + 'a' * 110),
                           ('modes', ['invalid']), ('snapshot', 'false'), ('vm', '../tahoe')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                wrapper.validate(self.config() | {key: value})

    def test_binary_patch_refuses_other_version(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            image.patch_binary(b'not the expected binary')

    def test_image_existing_output_is_not_modified(self):
        with tempfile.TemporaryDirectory() as temp:
            source, dest = Path(temp) / 'source', Path(temp) / 'dest'
            source.write_bytes(b'source'); dest.write_bytes(b'keep me')
            with patch.object(image.subprocess, 'run') as command, self.assertRaises(ValueError):
                image.patch_image(source, dest)
            command.assert_not_called()
            self.assertEqual(dest.read_bytes(), b'keep me')

    def test_gpt_efi_partition_not_assumed_first(self):
        with tempfile.TemporaryDirectory() as temp:
            data = bytearray(4096)
            data[512:520] = b'EFI PART'
            struct.pack_into('<QII', data, 512 + 72, 2, 2, 128)
            data[1152:1168] = uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b').bytes_le
            struct.pack_into('<QQ', data, 1152 + 32, 4, 7)
            path = Path(temp) / 'image'; path.write_bytes(data)
            self.assertEqual(image.efi_offset(path), 2048)
            struct.pack_into('<Q', data, 1152 + 40, 8); path.write_bytes(data)
            with self.assertRaises(ValueError): image.efi_offset(path)

    def test_usb_render_scopes_user_port_vm_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'rendered'
            usb.render(out, vm='devmac', user='alice', controller='0000:03:00.0', port='2')
            helper = (out / 'macos-vm-usb-devmac').read_text()
            rules = (out / '99-macos-vm-iphone-port.rules').read_text()
            service = (out / 'macos-vm-usb-devmac.service').read_text()
            compile(helper, '<rendered helper>', 'exec')
            self.assertIn('/sys/fs/cgroup/macos-vm-devmac', helper)
            self.assertIn("glob('*-2')", helper)
            self.assertIn('u:alice:rw', rules)
            self.assertIn('/0000:03:00.0/usb*/*-2/*-2:*', rules)
            self.assertIn('TEST!="/run/macos-vm-usb-devmac/active"', rules)
            self.assertIn('ExecStopPost=/usr/local/libexec/macos-vm-usb-devmac release', service)
            self.assertEqual((out / 'vm-user').read_text(), 'alice\n')
            self.assertNotIn('@VM@', helper + rules + service)
            with self.assertRaises(FileExistsError):
                usb.render(out, vm='devmac', user='alice', controller='0000:03:00.0', port='2')

    def test_usb_invalid_inputs_cannot_inject_rules_or_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            good = dict(vm='tahoe', user='alice', controller='0000:03:00.0', port='2')
            for key, value in [('user', 'alice\nOWNER="root"'), ('vm', '../escape'), ('port', '2.1'), ('controller', 'anything')]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    usb.render(Path(temp) / 'out', **(good | {key: value}))


if __name__ == '__main__':
    unittest.main()
