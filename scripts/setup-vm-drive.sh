#!/usr/bin/bash
# Format a blank disk as a Btrfs drive for VM and emulator images and mount it.
#
#   sudo setup-vm-drive.sh --device /dev/disk/by-path/... --model "Exact Model String" --size BYTES \
#       [--mount /mnt/vms] [--label "Virtual Machines"]
#
# Refuses unless the device matches the given model and exact size, has no
# partitions or signatures, and is not mounted; then asks for a typed YES.
# Mount options: noatime,nofail,x-gvfs-show. No compression: VM images are
# rewritten constantly. Backs up /etc/fstab before adding the entry.
set -euo pipefail

dev="" model="" size="" mnt=/mnt/vms label="Virtual Machines"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --device) dev=$2; shift 2 ;;
        --model) model=$2; shift 2 ;;
        --size) size=$2; shift 2 ;;
        --mount) mnt=$2; shift 2 ;;
        --label) label=$2; shift 2 ;;
        -h | --help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
done
[[ -n $dev && -n $model && -n $size ]] || { echo "Need --device, --model and --size (see lsblk -dbo NAME,MODEL,SIZE)." >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
[[ -b $dev ]] || { echo "No block device at $dev" >&2; exit 1; }

real=$(readlink -f "$dev")
actual_model=$(lsblk -dno MODEL "$real" | xargs)
actual_size=$(lsblk -dbno SIZE "$real")
echo "Target: $real  model='$actual_model'  size=$actual_size bytes"
[[ $actual_model == "$model" ]] || { echo "Model mismatch, aborting." >&2; exit 1; }
[[ $actual_size == "$size" ]] || { echo "Size mismatch, aborting." >&2; exit 1; }
[[ $(lsblk -no NAME "$real" | wc -l) -eq 1 ]] || { echo "Disk has partitions, aborting." >&2; exit 1; }
[[ -z $(wipefs --no-act "$real") ]] || { echo "Disk has signatures, aborting." >&2; exit 1; }
[[ -z $(lsblk -no MOUNTPOINTS "$real" | xargs) ]] || { echo "Disk is mounted, aborting." >&2; exit 1; }
if grep -q " $mnt " /etc/fstab; then echo "$mnt is already in /etc/fstab, aborting." >&2; exit 1; fi

read -r -p "Erase $real ($actual_model) and create Btrfs '$label' at $mnt? Type YES: " answer
[[ $answer == YES ]] || { echo "Cancelled."; exit 1; }

parted -s "$real" mklabel gpt mkpart vms btrfs 1MiB 100%
udevadm settle
part=$(lsblk -lnpo NAME,TYPE "$real" | awk '$2 == "part" {print $1; exit}')
mkfs.btrfs -q -L "$label" "$part"
uuid=$(blkid -s UUID -o value "$part")

cp -a /etc/fstab "/etc/fstab.bak-$(date +%Y%m%d-%H%M%S)"
echo "UUID=$uuid $mnt btrfs defaults,noatime,nofail,x-gvfs-show 0 0" >>/etc/fstab
mkdir -p "$mnt"
systemctl daemon-reload
mount "$mnt"
chown "${SUDO_USER:-root}:" "$mnt"
findmnt "$mnt"
