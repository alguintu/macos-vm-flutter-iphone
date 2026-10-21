#!/usr/bin/bash
# Reserve one physical USB socket's iPhone for a macOS VM (QEMU usb-host passthrough).
#
# Installs a udev rule matching the iPhone only on the given USB controller and
# root port. The device node becomes root-owned with an ACL for the VM user, and
# usbmuxd, gphoto2 and MTP probing are told to leave it alone. usbmuxd drops to
# its unprivileged user before opening USB devices, so it cannot claim the phone,
# while every other socket keeps working with the host's usbmuxd.
#
#   install-iphone-port.sh --list
#   sudo install-iphone-port.sh --user NAME --controller 0000:02:00.0 --port 1 [--vid 05ac --pid 12a8] [--dry-run]
#
# Only root ports are supported (a phone behind a hub has a dotted port path).
set -euo pipefail

rule_path=/etc/udev/rules.d/99-macos-vm-iphone-port.rules
user="" controller="" port="" vid=05ac pid=12a8 dry_run=0

list_apple_devices() {
    local found=0 path real ctrl
    for path in /sys/bus/usb/devices/*; do
        [[ -f $path/idVendor && $(cat "$path/idVendor") == 05ac ]] || continue
        real=$(readlink -f "$path")
        ctrl=$(grep -o -E '[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]/usb[0-9]+' <<<"$real" | tail -1)
        printf '%s  %s:%s  controller=%s  port=%s  speed=%sM\n' "$(basename "$path")" \
            "$(cat "$path/idVendor")" "$(cat "$path/idProduct")" "${ctrl%%/*}" \
            "$(basename "$path" | cut -d- -f2)" "$(cat "$path/speed")"
        found=1
    done
    [[ $found == 1 ]] || echo "No Apple USB devices connected." >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --list) list_apple_devices; exit 0 ;;
        --user) user=$2; shift 2 ;;
        --controller) controller=$2; shift 2 ;;
        --port) port=$2; shift 2 ;;
        --vid) vid=$2; shift 2 ;;
        --pid) pid=$2; shift 2 ;;
        --dry-run) dry_run=1; shift ;;
        -h | --help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
done

[[ -n $user && -n $controller && -n $port ]] || { echo "Need --user, --controller and --port (see --list)." >&2; exit 2; }
id -u "$user" >/dev/null 2>&1 || { echo "No such user: $user" >&2; exit 2; }
[[ $controller =~ ^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$ && -e /sys/bus/pci/devices/$controller ]] ||
    { echo "Not a PCI device on this host: $controller" >&2; exit 2; }
[[ $port =~ ^[0-9]+$ ]] || { echo "--port must be a root port number" >&2; exit 2; }
[[ $vid =~ ^[0-9a-f]{4}$ && $pid =~ ^[0-9a-f]{4}$ ]] || { echo "--vid/--pid must be 4 lowercase hex digits" >&2; exit 2; }

rule="# Reserve the iPhone on $controller root port $port for $user's QEMU process (macos-vm).
SUBSYSTEM==\"usb\", ENV{DEVTYPE}==\"usb_device\", KERNELS==\"$controller\", KERNEL==\"*-$port\", ATTR{idVendor}==\"$vid\", ATTR{idProduct}==\"$pid\", OWNER:=\"root\", GROUP:=\"root\", MODE:=\"0600\", ENV{USBMUX_SUPPORTED}=\"0\", ENV{SYSTEMD_WANTS}=\"\", ENV{ID_GPHOTO2}=\"\", ENV{GPHOTO2_DRIVER}=\"\", ENV{ID_MTP_DEVICE}=\"\", ENV{MTP_NO_PROBE}=\"1\", RUN+=\"/usr/bin/setfacl -m u:$user:rw \$env{DEVNAME}\""

if [[ $dry_run == 1 ]]; then
    echo "Would install $rule_path:"; echo "$rule"; exit 0
fi
[[ $EUID -eq 0 ]] || { echo "Run with sudo (or use --dry-run)." >&2; exit 1; }

tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
printf '%s\n' "$rule" >"$tmp"
if udevadm verify --help >/dev/null 2>&1; then udevadm verify "$tmp"; fi
if [[ -e $rule_path ]] && ! cmp -s "$tmp" "$rule_path"; then
    cp -a "$rule_path" "$rule_path.bak-$(date +%Y%m%d-%H%M%S)"
fi
install -o root -g root -m 0644 "$tmp" "$rule_path"
udevadm control --reload-rules

count=0
for path in /sys/bus/usb/devices/*-"$port"; do
    [[ -f $path/idVendor && $(cat "$path/idVendor") == "$vid" && $(cat "$path/idProduct") == "$pid" ]] || continue
    [[ $(readlink -f "$path") == */"$controller"/usb*/*-"$port" ]] || continue
    udevadm trigger --action=change "$path"
    udevadm settle --timeout=10
    printf -v node '/dev/bus/usb/%03d/%03d' "$(cat "$path/busnum")" "$(cat "$path/devnum")"
    if id -u usbmuxd >/dev/null 2>&1 && { runuser -u usbmuxd -- test -r "$node" || runuser -u usbmuxd -- test -w "$node"; }; then
        echo "ERROR: usbmuxd can still open $node." >&2; exit 1
    fi
    runuser -u "$user" -- test -w "$node" || { echo "ERROR: $user cannot open $node." >&2; exit 1; }
    stat -c "Reserved %n: %U:%G %a (+ACL $user)" "$node"
    count=$((count + 1))
done
[[ $count -gt 0 ]] || echo "Rule installed; no matching iPhone is connected on that port right now."

# A runtime mask from earlier troubleshooting is no longer needed.
if [[ $(systemctl is-enabled usbmuxd.service 2>/dev/null || true) == masked-runtime ]]; then
    systemctl unmask --runtime usbmuxd.service
fi
echo "Done. Other sockets keep using the host usbmuxd; the reserved iPhone is left to QEMU."
