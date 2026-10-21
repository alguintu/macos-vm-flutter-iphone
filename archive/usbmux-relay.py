#!/usr/bin/env python3
"""Replace macOS usbmuxd socket with a relay to Fedora usbmuxd (via QEMU slirp 10.0.2.2:27015).
Run with sudo. Ctrl-C or SIGTERM restores Apple usbmuxd socket."""
import os, signal, socket, sys, threading

SOCK, ORIG = "/var/run/usbmuxd", "/var/run/usbmuxd.apple"
REMOTE = ("10.0.2.2", 27015)

def pump(src, dst):
    try:
        while (data := src.recv(65536)):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass

def handle(client):
    try:
        remote = socket.create_connection(REMOTE, timeout=5)
        remote.settimeout(None)
    except OSError as e:
        print(f"relay: cannot reach {REMOTE}: {e}", file=sys.stderr); client.close(); return
    threading.Thread(target=pump, args=(client, remote), daemon=True).start()
    pump(remote, client)
    client.close(); remote.close()

def restore(*_):
    try: os.unlink(SOCK)
    except FileNotFoundError: pass
    if os.path.exists(ORIG): os.rename(ORIG, SOCK)
    print("relay: Apple usbmuxd socket restored"); sys.exit(0)

if os.geteuid() != 0: sys.exit("run with sudo")
if not os.path.exists(ORIG): os.rename(SOCK, ORIG)
elif os.path.exists(SOCK): os.unlink(SOCK)
srv = socket.socket(socket.AF_UNIX); srv.bind(SOCK); os.chmod(SOCK, 0o666); srv.listen(64)
signal.signal(signal.SIGTERM, restore); signal.signal(signal.SIGINT, restore)
print(f"relay: {SOCK} -> {REMOTE[0]}:{REMOTE[1]}")
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
