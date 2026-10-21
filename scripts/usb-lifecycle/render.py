#!/usr/bin/env python3
"""Render a scoped USB lease for review; never installs files or changes host state."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def render(output, *, vm, user, controller, port, vid='05ac', pid='12a8'):
    values = {'VM': vm, 'USER': user, 'CONTROLLER': controller, 'PORT': str(port), 'VID': vid, 'PID': pid}
    patterns = {'VM': r'[A-Za-z0-9_-]+', 'USER': r'[a-z_][a-z0-9_-]*[$]?',
                'CONTROLLER': r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]',
                'PORT': r'[1-9][0-9]*', 'VID': r'[0-9a-f]{4}', 'PID': r'[0-9a-f]{4}'}
    if any(not re.fullmatch(patterns[k], v) for k, v in values.items()):
        raise ValueError('Invalid VM/user/PCI/root-port/USB identity')
    output.mkdir(parents=True, exist_ok=False)
    name = 'macos-vm-usb-' + vm
    for source, destination in [('lease.py.in', name), ('lease.service.in', name + '.service'),
                                ('lease.rules.in', '99-macos-vm-iphone-port.rules')]:
        text = (ROOT / source).read_text()
        for key, value in values.items():
            text = text.replace('@' + key + '@', value)
        if '@VM@' in text:
            raise ValueError('Unexpanded template')
        (output / destination).write_text(text)
    (output / 'vm-user').write_text(user + '\n')
    (output / name).chmod(0o755)
    print('Rendered only; review and install using docs/usb-lifecycle.md:', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=lambda x: Path(x).expanduser().absolute())
    for name in ('vm', 'user', 'controller', 'port'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--vid', default='05ac')
    parser.add_argument('--pid', default='12a8')
    args = vars(parser.parse_args())
    render(**args)
