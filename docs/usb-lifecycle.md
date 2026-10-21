# Return the iPhone to Fedora when the VM exits

This supersedes the original always-reserved socket recipe. A root-owned systemd service reserves only the selected iPhone identity on one PCI controller/root port **while the VM cgroup is populated**. On normal exit, SIGKILL or failed startup, ExecStopPost removes the runtime lease, reapplies Fedora's USB rules, and restarts usbmuxd to clear cached denied-open state. A reboot clears the runtime marker. Other device identities remain with Fedora.

The reference machine's installed version was verified with a disposable cgroup process, SIGKILL/failed-start cases, and actual QEMU shutdowns. After the accepted dual-screen run, the cgroup was empty, the lease absent, the service inactive, and usbmuxd listed the phone again. A new physical-iPhone Flutter deployment was not repeated during the cursor test. The portable renderer below preserves that mechanism with configurable names/ports; install and physically validate it on each host.

## Render first; install only while the VM is off

Find the port with the existing `scripts/install-iphone-port.sh --list` (listing is read-only). This recipe supports a direct root port, not a dotted hub path. Use your own username, PCI controller and port:

```bash
repo=$HOME/Projects/macos-vm-flutter-iphone
rendered=$HOME/Build/tahoe-usb-lease
python3 "$repo/scripts/usb-lifecycle/render.py" "$rendered" \
  --vm tahoe --user "$USER" --controller 0000:02:00.0 --port 1
```

The output directory must be new. Rendering is unprivileged and changes no host setting. Review all four files. `macos-vm-usb-tahoe` contains the exact cgroup/port/identity match; the service creates `/run/macos-vm-usb-tahoe`, and the rule acts only while its root-owned `active` marker exists. The user marker binds the capped launcher's lease option to the configured user.

Validate syntax before installation:

```bash
python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$rendered/macos-vm-usb-tahoe"
udevadm verify "$rendered/99-macos-vm-iphone-port.rules"
systemd-analyze verify --man=no "$rendered/macos-vm-usb-tahoe.service"
```

Before installation, systemd verification may warn that `/usr/local/libexec/macos-vm-usb-tahoe` does not yet exist. Verify again after installation; other errors need fixing. Require `getent passwd "$USER"`, `setfacl`, `udevadm` and systemd on the target host. Keep the VM off throughout installation. Back up any existing files and stop/remove a previous lease or permanent reservation rule for this same device; do not layer conflicting rules. The original repository installer used `/etc/udev/rules.d/99-macos-vm-iphone-port.rules`. An Aeris-specific earlier installation used `99-tahoe-iphone-port.rules` and `eris-tahoe-usb.service`; those are not automatically migrated by this generic recipe.

Install the reviewed files (substitute your VM name consistently):

```bash
sudo install -D -o root -g root -m 0755 "$rendered/macos-vm-usb-tahoe" /usr/local/libexec/macos-vm-usb-tahoe
sudo install -D -o root -g root -m 0644 "$rendered/macos-vm-usb-tahoe.service" /etc/systemd/system/macos-vm-usb-tahoe.service
sudo install -D -o root -g root -m 0644 "$rendered/vm-user" /etc/macos-vm-usb/tahoe.user
sudo install -D -o root -g root -m 0644 "$rendered/99-macos-vm-iphone-port.rules" /etc/udev/rules.d/99-macos-vm-iphone-port.rules
sudo systemd-analyze verify --man=no /etc/systemd/system/macos-vm-usb-tahoe.service
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
sudo /usr/local/libexec/macos-vm-usb-tahoe release
```

Do **not** enable the service at boot, globally mask usbmuxd, or add unrestricted passwordless sudo. The existing privileged capped launcher starts the service only after entering the VM cgroup:

```bash
pkexec "$repo/scripts/start-vm-limited" --vm tahoe --limit 4G --usb-lease
# Add --qemu "$repo/scripts/multimonitor/qemu-multimonitor" for the dual-screen build.
```

Always use `--usb-lease` with this setup when the VM config forwards the phone; a plain `reims-ctl start` bypasses both the cap and lease. A renderer output is not an installed service, and an installed service is not physical acceptance.

## Verify the lifecycle

1. VM off: no `/run/macos-vm-usb-tahoe/active`; phone available to host usbmuxd; ordinary camera/MTP discovery allowed.
2. VM active: marker present, user has USB node access, usbmuxd cannot open that matching node. Guest EHCI sees the phone. Other device identities are unaffected by the rule.
3. Normal guest shutdown: QEMU/cgroup empty, service inactive, marker absent, Fedora usbmuxd sees the phone again. Merely restoring node permissions is insufficient—check discovery as well.
4. Separately test failed launch and abrupt QEMU exit using disposable disks before relying on crash recovery. Do not kill a working development VM to test this.

The service restarts usbmuxd at handoff to release/reopen handles. That can briefly interrupt host-side sessions on other phones even though their permission rules are unchanged. USB bus numbering can change at reboot; re-check the `hostbus` in the VM's existing usb-host config.

Rollback while the VM is off: stop the scoped service, run its `release` action, restore the backed-up rule/helper/unit or remove only the newly installed files, reload udev/systemd, and verify host discovery. Keep the capped launcher but omit `--usb-lease` after removing the service. Do not restore permanent reservation unless that is deliberately wanted.
