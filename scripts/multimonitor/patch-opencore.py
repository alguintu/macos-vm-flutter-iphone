#!/usr/bin/env python3
"""Patch APVDisplayPort only in a NEW raw copy of a powered-off OpenCore image."""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import uuid

ORIGINAL = '02f2065b7ff64e8da80ea64603ee85f9667da994515e29a22eebc9524cf97f8f'
PATCHED = '1cce406c091143a677831890ae426ccaf5ddd75a15042656886b6c622bcc816e'
MEMBER = '::/EFI/OC/Kexts/APVDisplayPort.kext/Contents/MacOS/APVDisplayPort'
PATCHES = [
    (0x1b62, '4889c7be40000000', '8bbbd001000089fe'),
    (0x1ba7, 'ff9068020000', '660f1f440000'),
    (0x1bba, '4c89f2', '4c89fa'),
    (0x14ff, 'be00100000', 'be00000004'),
    (0x42d4, '0f94c1', 'b10190'),
    (0x42e8, '488bbbb0020000be000000004885ff7410be01000000', '85f6751d488bbbb00200004885ff7411be0100000090'),
    (0x43a3, '83bfd001000000751ac6837003000000', 'c683700300000083bfd0010000007513'),
    (0x1607, '83bfd001000000751ac6837003000000', 'c683700300000083bfd0010000007513'),
    (0x460a, '83bfd00100000074025dc34088b770030000', '4088b77003000083bfd00100000074025dc3'),
    (0x4626, '74eb', '74f2'),
]


def patch_binary(data):
    if hashlib.sha256(data).hexdigest() != ORIGINAL:
        raise ValueError('Unsupported APVDisplayPort SHA256; original version required')
    result = bytearray(data)
    for offset, old, new in PATCHES:
        old, new = bytes.fromhex(old), bytes.fromhex(new)
        if len(old) != len(new) or result[offset:offset + len(old)] != old:
            raise ValueError('Unexpected instruction bytes at ' + hex(offset))
        result[offset:offset + len(old)] = new
    if hashlib.sha256(result).hexdigest() != PATCHED:
        raise ValueError('Patched hash mismatch')
    return bytes(result)


def efi_offset(image):
    # reims-util images use GPT with 512-byte sectors. Reject other formats.
    with image.open('rb') as stream:
        stream.seek(512)
        header = stream.read(92)
        if len(header) != 92 or header[:8] != b'EFI PART':
            raise ValueError('Expected a GPT image with 512-byte sectors')
        lba, count, size = struct.unpack_from('<QII', header, 72)
        if not 1 <= count <= 4096 or not 128 <= size <= 4096:
            raise ValueError('Invalid GPT partition table')
        stream.seek(lba * 512)
        matches = []
        for _ in range(count):
            entry = stream.read(size)
            if len(entry) != size:
                raise ValueError('Truncated GPT partition table')
            if entry[:16] == uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b').bytes_le:
                first, last = struct.unpack_from('<QQ', entry, 32)
                if first > last or (last + 1) * 512 > image.stat().st_size:
                    raise ValueError('EFI partition outside image')
                matches.append(first * 512)
        if len(matches) != 1:
            raise ValueError('Expected exactly one EFI System Partition')
        return matches[0]


def patch_image(source, destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError('Output already exists; no image was changed')
    if not source.is_file():
        raise ValueError('Input must be an image file')
    with tempfile.TemporaryDirectory(prefix='.multimonitor-', dir=destination.parent) as temp:
        temp = Path(temp)
        image = temp / 'opencore.raw'
        subprocess.run(['qemu-img', 'convert', '-O', 'raw', str(source), str(image)], check=True)
        image_spec = str(image) + '@@' + str(efi_offset(image))
        binary = temp / 'APVDisplayPort'
        subprocess.run(['mcopy', '-i', image_spec, MEMBER, str(binary)], check=True)
        binary.write_bytes(patch_binary(binary.read_bytes()))
        subprocess.run(['mcopy', '-o', '-i', image_spec, str(binary), MEMBER], check=True)
        readback = temp / 'readback'
        subprocess.run(['mcopy', '-i', image_spec, MEMBER, str(readback)], check=True)
        if readback.read_bytes() != binary.read_bytes():
            raise ValueError('EFI readback mismatch')
        # Atomic, same-filesystem publish; fails if another process created the output.
        os.link(image, destination)
    print('Created', destination, 'APVDisplayPort sha256', PATCHED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=lambda s: Path(s).expanduser().absolute())
    parser.add_argument('destination', type=lambda s: Path(s).expanduser().absolute())
    args = parser.parse_args()
    patch_image(args.source, args.destination)
