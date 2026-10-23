# macOS VM for Flutter iPhone development (Tahoe on reims-vgpu)

A macOS Tahoe virtual machine on Fedora for building Flutter/iOS apps and running them on a real iPhone, without a Mac and without a Hackintosh reboot. The host keeps running; agents and humans drive the guest over SSH.

- **Graphics:** [reims-vgpu](https://github.com/steelbrain/reims-vgpu) gives the guest a GPU-accelerated paravirtual device (Metal 2) backed by the host's Vulkan driver. No GPU passthrough, so a single-GPU host keeps its desktop.
- **iPhone:** forwarded from one selected host USB socket onto an emulated EHCI controller in the guest. The new [temporary lease](docs/usb-lifecycle.md) returns it to Fedora when the VM exits. Xcode pairs, Developer Mode works, and `flutter run` with hot reload works on the device.
- **Xcode:** 26.6 Universal, the last release that runs on Intel/x86 macOS.

**Procedure: [runbook.md](runbook.md).** Read its "Known failures" section before trying alternatives.

For SSH-controlled development with the app visible on the physical phone, see
[headless iPhone development](docs/headless.md). The macOS desktop session stays
logged in for signing while Reims opens no host window.

**2026-10-22 progress:** [two displays and responsive border crossing](docs/multimonitor.md), with pinned source patches, a hash-checked OpenCore copy patcher, the guest-aware mouse companion, and opt-in launcher. Physical feedback on the reference host: **visible, aligned, lighter, workable**. The [USB lifecycle recipe](docs/usb-lifecycle.md) replaces permanent socket reservation. Normal single-display launch remains rollback; the experimental wrapper defaults to disposable disk snapshots.

## Contents

| Path | Purpose |
| --- | --- |
| [runbook.md](runbook.md) | Setup from a bare Fedora host, daily use, acceptance checks, known failures, rollback |
| [scripts/start-vm-limited](scripts/start-vm-limited) | Start the VM in its own cgroup with a VRAM cap (run via `pkexec`) |
| [scripts/install-iphone-port.sh](scripts/install-iphone-port.sh) | Legacy permanent reservation; use `--list` to discover a port, then prefer the temporary lease |
| [scripts/setup-vm-drive.sh](scripts/setup-vm-drive.sh) | Format a blank disk as the Btrfs VM drive, with identity checks |
| [config/vm.toml.example](config/vm.toml.example) | reims-ctl VM settings including the iPhone passthrough devices |
| [config/ssh-config.example](config/ssh-config.example) | Host-side SSH alias for the guest |
| [docs/multimonitor.md](docs/multimonitor.md) | Reproduce the accepted dual-display mouse candidate, build, test and roll back |
| [patches/multimonitor/](patches/multimonitor/) | Pinned Reims/QEMU source patches and provenance |
| [scripts/multimonitor/](scripts/multimonitor/) | Fresh source preparation, copied OpenCore patching and opt-in QEMU wrapper |
| [docs/usb-lifecycle.md](docs/usb-lifecycle.md) | VM-lifetime USB lease, reviewable templates, install and physical checks |
| [docs/simulator.md](docs/simulator.md) | Fix the iOS Simulator's sustained 600% CPU (`mediaanalysisd`), with diagnosis and verification |
| [scripts/check](scripts/check) | Local packaging tests and syntax checks; no VM or privileged changes |
| [archive/](archive/) | A usbmux relay approach that did **not** work, kept for reference |

## Limits

- **Intel sunset.** Xcode 27 and later are Apple-silicon only, and Homebrew has dropped Intel Macs. When Apple starts requiring the Xcode 27 SDK for App Store uploads (historically each April), this VM can still build and test but can no longer publish. Plan an Apple silicon Mac or hosted macOS CI before then.
- **Metal 2 only.** The guest has no Metal 3. An iPhone Simulator boot and pixels on the second display were verified locally; broad Simulator compatibility is untested. Each simulator device needs [one daemon disabled](docs/simulator.md) or it holds 6–8 host cores.
- **Free signing.** A free Apple Account's Personal Team signs 7-day development profiles; rebuild to renew.
- **One socket.** The selected USB socket hands only the iPhone (`05ac:12a8`) to the VM. With the temporary lease, it returns on VM exit; other device identities stay with the host.

## Reference machine (tested 2026-10-21)

The values the runbook was verified with. Substitute your own.

| Item | Aeris |
| --- | --- |
| Host | Fedora 44 KDE, Ryzen 9 5950X, MSI B550M Mortar WiFi, 64 GB |
| GPU | RX 6900 XT, RADV (Mesa 26.2.4), dmem region `drm/0000:2d:00.0/vram`, cap 4 GiB |
| reims-vgpu | commit `2ce32093`, QEMU fork `bd95509` (QEMU 11.1.50) |
| Guest | macOS 26.7 (25G229), OpenCore identity iMac20,1, 16 vCPU, 14 GiB, 1920×1080 |
| Storage | Btrfs "Virtual Machines" drive at `/mnt/vms` |
| iPhone socket | Front USB-C, chipset controller `0000:02:00.0`, root port 1 (USB 2 bus 1). That controller's IOMMU group also holds SATA, NVMe and Ethernet, so it is **not** VFIO-assignable; usb-host forwarding avoids that |
| Phone | iPhone 17 Pro (iPhone18,1), iOS 26.6 |
| Toolchain | Xcode 26.6 (17F113), iOS 26.5 SDK, Flutter 3.47.2 |
