# Runbook: macOS Tahoe VM with iPhone deployment

Repeatable procedure for building, running and repairing the VM, written so another person or agent can pick it up cold. Everything here was performed and verified on the [reference machine](README.md#reference-machine-tested-2026-10-21) on 2026-10-21 unless marked otherwise. Read [Known failures](#known-failures) before improvising.

**2026-10-22 follow-up:** the original procedure below is the single-display baseline. For the accepted dual-display mouse candidate use [multimonitor.md](docs/multimonitor.md); for automatic USB return on VM exit use [usb-lifecycle.md](docs/usb-lifecycle.md), which supersedes permanent reservation in section 7. The iPhone Simulator has since booted and displayed on the second monitor; full compatibility is still unverified. Before using a simulator device, disable its `mediaanalysisd` as described in [simulator.md](docs/simulator.md), or it holds 6–8 host CPU cores.

Conventions: **Host** = Fedora shell as your normal user. **Guest (SSH)** = `ssh tahoe '…'`. **Guest (desktop)** = Terminal.app in the VM window. Steps that need a password say whose: host sudo, Mac account, or Apple Account. Agents should hand password steps to the human in a terminal and never type them.

Placeholders: `<vm>` VM name (examples use `tahoe`), `<vm-dir>` = `~/.local/share/reims-ctl/vms/<vm>`, `<storage>` VM drive (examples use `/mnt/vms`).

## 0. Quick reference

| Task | Command |
| --- | --- |
| Start | Host: `pkexec <repo>/macos-vm/scripts/start-vm-limited --vm tahoe` |
| Stop | Guest: Apple menu → Shut Down, or host: `reims-ctl stop tahoe` |
| Shell | `ssh tahoe` |
| Push code | Host repo: `git push tahoe <branch>` |
| Run on the iPhone | Guest (desktop): a `.command` launcher that runs `flutter run -d <udid>` |
| Check the iPhone | `ssh tahoe 'xcrun devicectl list devices'`: expect `available (paired)` |

**Never start the VM from an agent's tool shell or an app's integrated terminal** with plain `reims-ctl start`: QEMU joins that app's cgroup scope, so quitting the app can kill the VM, and it escapes the VRAM cap. Use `start-vm-limited`.

## 1. Host prerequisites (Fedora 44)

- `/dev/kvm` usable by your user. IOMMU is not required.
- An AMD GPU on RADV (NVIDIA hosts are reims-supported but untested here), with access to `/dev/udmabuf` (Fedora grants an ACL).
- `vm.max_map_count`: reims needs about `memory_mib × 64 + 81920`. Fedora's default 1048576 covers about 14.75 GiB of guest RAM.
- Kernel `dmem` cgroup controller for the VRAM cap: `cat /sys/fs/cgroup/dmem.capacity` must list your GPU's `vram` region.
- Build dependencies (host sudo; expect related packages such as Mesa to be upgraded too):

```bash
sudo dnf install -y clang lld libslirp-devel libfdt-devel pipewire-devel pulseaudio-libs-devel alsa-lib-devel libXrandr-devel libXcursor-devel libXi-devel libXfixes-devel libXScrnSaver-devel libXtst-devel libxkbcommon-devel wayland-devel libdecor-devel mesa-libEGL-devel mesa-libGL-devel libdrm-devel mesa-libgbm-devel dbus-devel systemd-devel gtk3-devel
```

- Storage: a dedicated Btrfs drive keeps VM I/O off the system disk and allows instant `cp --reflink=always` checkpoints. [`scripts/setup-vm-drive.sh`](scripts/setup-vm-drive.sh) formats a **blank** disk after verifying its model and size.

## 2. Build reims-vgpu

```bash
git clone https://github.com/steelbrain/reims-vgpu.git ~/Projects/reims-vgpu
```

Read `scripts/install-ctl.sh` first. It installs only under `~/.local/share/reims-ctl`, `~/.cache/reims-ctl` and `~/.cargo/bin`; on Fedora it prints package names instead of installing them.

```bash
bash ~/Projects/reims-vgpu/scripts/install-ctl.sh --yes
```

```bash
~/.cargo/bin/reims-ctl doctor
```

Every line should be `ok`. `doctor` checks `vm.max_map_count` against its default 16 GiB guest, so a 14 GiB guest can ignore that one.

## 3. Create the VM

### Fresh install (reims-documented; not the path used on the reference machine)

```bash
reims-ctl create tahoe --macos 26.6.2 --offline --start
```

Erase the virtual disk as APFS in Recovery, install, then `reims-ctl eject tahoe`. Continue at step 3.4.

### From an existing OSX-KVM install (the reference path)

1. Copy the powered-off disk (reflink on Btrfs), and put `OVMF_CODE.fd` / `OVMF_VARS.fd` as **raw** files beside the old OpenCore image (`qemu-img convert -O raw`; Fedora's code image is `/usr/share/edk2/ovmf/OVMF_CODE_4M.qcow2`).
2. Create the VM around it, keeping the old network MAC (the OpenCore ROM value is derived from it):

```bash
reims-ctl create tahoe --disk <storage>/macos/tahoe/macos.qcow2 --disk-mode in-place --opencore <dir>/OpenCore.qcow2 --mac <mac> --cpus 16 --memory 14G --resolution 1920x1080 --logs --ssh-port 2222
```

3. In `<vm-dir>/vm.toml`, set `disk_port` to the SATA port the disk had when macOS was installed (4 for OSX-KVM).
4. Rebuild OpenCore with reims's kexts (`ReimsVgpu.kext`, Lilu), which Tahoe needs. `reims-ctl update-opencore` cannot read OSX-KVM images ("EFI system partition is not FAT32"), so run reims-util directly. It supports only **iMac20,1** and iMacPro1,1; keeping the old UUID and ROM and letting it generate a serial/MLB is fine if no Apple Account was signed in at the system level. Keep its JSON output private (it contains the identity):

```bash
reims-util opencore --json -o <vm-dir>/opencore.qcow2 --model iMac20,1 --uuid <uuid> --rom <rom-hex> --no-ovmf --show-picker
```

   Do not pass `--show-vm`; hiding the VM is what lets Apple services behave normally.
5. Set Metal's error mode once from Recovery (OpenCore picker → Recovery → Utilities → Terminal). Without it, WindowServer and the icon service crash at login:

```bash
cd /Volumes/*Data/Library/Preferences && defaults write "$PWD/.GlobalPreferences" METAL_ERROR_MODE -int 5 && chmod 644 .GlobalPreferences.plist && reboot
```

6. Snapshot the result: power off, then `cp --reflink=always` the disk into `<storage>/macos/checkpoints/<date>/`.

## 4. Guest basics

1. Setup Assistant: create a local account and **skip system-level Apple Account sign-in**. Nothing below needs it.
2. Remote Login: guest System Settings → General → Sharing → Remote Login (Mac password). Make a dedicated host key, type its **public** half into the guest's `~/.ssh/authorized_keys` (`chmod 600`), and add [`config/ssh-config.example`](config/ssh-config.example) to the host's `~/.ssh/config`. Check: `ssh tahoe sw_vers`.
3. Optional: Accessibility → Display → Reduce Transparency and Reduce Motion lower GPU load.

## 5. Xcode 26.6 Universal

The App Store offers only the newest Xcode (27.x, `arm64` only), so it hides Xcode from an Intel guest. Use the developer portal with a **free** Apple Account:

1. Accept the Apple Developer Agreement once (Apple Developer app, or developer.apple.com/account).
2. In the **guest's** Safari, signed in, open `https://developer.apple.com/download/all/` first. It sets the cookie that direct downloads need; without it they fail with "Your account can't access this page".
3. Download `https://download.developer.apple.com/Developer_Tools/Xcode_26.6/Xcode_26.6_Universal.xip`. It must be **Universal**, not "Apple silicon".
4. Verify and expand (guest SSH):

```bash
ssh tahoe 'pkgutil --check-signature ~/Downloads/Xcode_26.6_Universal.xip | head -2'
```

```bash
ssh tahoe 'cd /Applications && xip --expand ~/Downloads/Xcode_26.6_Universal.xip'
```

5. Select it, accept the license (the human accepts; Mac password), and run first-launch setup:

```bash
ssh -t tahoe 'sudo xcode-select -s /Applications/Xcode.app/Contents/Developer && sudo xcodebuild -license accept && sudo xcodebuild -runFirstLaunch && xcodebuild -version'
```

   Running `git` or `xcode-select -p` before this pops a Command Line Tools installer; cancel it.
6. Optional Simulator runtime (about 8 GB): `ssh tahoe 'xcodebuild -downloadPlatform iOS'`.
7. Guest (desktop): Xcode → Settings → Accounts → + → Apple Account. A free account becomes a Personal Team.

## 6. Flutter and code

1. Flutter: Homebrew is unavailable on Intel. Download the official archive and check its SHA-256 against `https://storage.googleapis.com/flutter_infra_release/releases/releases_macos.json` (entry with `dart_sdk_arch: x64`). Unzip to `~/sdk/flutter`, add `~/sdk/flutter/bin` to `PATH` in `~/.zprofile`, then run `flutter config --no-analytics` and `flutter precache --ios`.
2. CocoaPods is unnecessary for Swift Package Manager projects. Without Homebrew, projects that still need it require a Ruby-gem install.
3. Guest `~/.gitconfig`: your name and email, plus `receive.denyCurrentBranch = updateInstead`.
4. Push from the host, so forge credentials never enter the VM:

```bash
ssh tahoe 'git init -q ~/src/<repo>'
```

```bash
git remote add tahoe tahoe:src/<repo>
```

```bash
git push tahoe <branch>
```

   After the first push, check out that branch once in the guest. Workspaces/monorepos must be pushed whole.

## 7. iPhone

The working design: an **emulated EHCI (USB 2) controller** in the guest, with the phone forwarded onto it by `usb-host`, and the host told to keep its hands off that one socket.

1. **Pick a socket** and find its controller and port: plug the iPhone in, then run `scripts/install-iphone-port.sh --list`. Root ports only (no hubs). This does not use VFIO, so the controller may share an IOMMU group with anything.
2. **Reserve it** (host sudo). The rule matches only the iPhone on that controller and port, makes its node root-owned with an ACL for your user, and hides it from usbmuxd, gphoto2 and MTP. The script verifies that the `usbmuxd` user cannot open the node and you can:

```bash
sudo ./scripts/install-iphone-port.sh --user "$USER" --controller <pci-address> --port <n>
```

   Desktop "Camera"/"USB device detected" notifications afterwards are cosmetic.
3. **VM config:** add the two devices from [`config/vm.toml.example`](config/vm.toml.example) to `extra_args`, with `hostbus` = the controller's USB 2 bus and `hostport` = the port. Cold boot verified: the guest loads `AppleUSBEHCIPCI` with the iPhone beneath it. Whether `guest-reset=off` and `pipeline=off` are each required is untested. Re-check `hostbus` after host reboots.
   To add them to a running VM, use QMP `device_add`; the guest only enumerates a hot-added EHCI controller after a guest restart.
4. **Pair:** unlock the phone, then **Trust This Computer** and enter the passcode. Then Settings → Privacy & Security → **Developer Mode**. It only appears after Xcode has seen the phone; the phone restarts, then confirm **Turn On**.
5. **Verify** (guest SSH): `xcrun devicectl device info details --device <id>` should show `pairingState: paired`, `tunnelState: connected`, `ddiServicesAvailable: true`, `developerModeStatus: enabled`.
6. **Build and run from the guest desktop session, not SSH.** Code signing over SSH fails with "User interaction is not allowed" (the login keychain belongs to the GUI session). Put `flutter run` in a `.command` file and open it with Terminal.app; agents can trigger that with `ssh tahoe 'open -a Terminal <file>.command'`. The first run per phone copies about 8 GB of device symbols. The first launch needs the phone's Settings → General → VPN & Device Management → developer profile → **Trust**. Debug Flutter builds launch only from Flutter tooling, not from the home screen.
7. Free Personal Team profiles expire after 7 days; rebuild to renew.

## 8. VRAM cap

reims's QEMU held about 11.5 of 16 GiB VRAM on the reference machine and logged Vulkan OutOfMemory errors. [`scripts/start-vm-limited`](scripts/start-vm-limited) enables the `dmem` controller, creates `/sys/fs/cgroup/macos-vm-<vm>` with a `dmem.max` (default 4 GiB) on the GPU's VRAM region (auto-detected when there is exactly one), and starts reims-ctl inside it as you. It refuses to start a VM that is already running. `--dry-run` shows the plan.

## 9. Acceptance checks

Run after any rebuild, host reboot or config change.

| Check | Command | Expect |
| --- | --- | --- |
| Cgroup | `cat /proc/$(cat <vm-dir>/qemu.pid)/cgroup` | `0::/macos-vm-<vm>` |
| VRAM cap | `cat /sys/fs/cgroup/macos-vm-<vm>/dmem.max` | your region and limit |
| GPU | `ssh tahoe 'system_profiler SPDisplaysDataType'` | `Reims vGPU`, `Metal Support: Metal 2` |
| Xcode | `ssh tahoe 'xcodebuild -version'` | `Xcode 26.6` |
| iPhone | `ssh tahoe 'xcrun devicectl list devices'` | `available (paired)` |
| Socket reserved | `journalctl -u usbmuxd -n 20` after replugging | `LIBUSB_ERROR_ACCESS` for the reserved phone |
| App | the `.command` launcher | app runs; hot reload keeps state |

Not yet verified on the reference machine: a host reboot (USB bus numbering), and the iOS Simulator.

## Known failures

Do not repeat these without new evidence.

| Tried | Result |
| --- | --- |
| Bare-metal Hackintosh | Abandoned: AMD kernel patches, board SSDTs and USB mapping, plus a reboot to switch OS |
| OSX-KVM graphics (`vmware-svga`) | Unaccelerated; macOS has no driver for virtio-gpu, QXL or VMware SVGA |
| Single-GPU passthrough | Blanks the host desktop while the VM runs |
| `reims-ctl update-opencore` on an OSX-KVM image | Fails: that ESP is FAT16. Use `reims-util opencore` |
| reims-util with `MacPro7,1` | Unsupported; use iMac20,1 |
| Xcode from the App Store | Not offered: current versions are `arm64` only |
| Homebrew | Refuses Intel Macs |
| iPhone via `usb-host` on QEMU's **xHCI** | Auto-placed behind a 12 Mb/s hub (speed mismatch); on a root port: reset loop ("device firmware changed"), plus `apple_mfi_fastcharge` and host usbmuxd contending; with `guest-reset=false` the loop stops but the guest's usbmuxd never lists the phone |
| Unloading `apple_mfi_fastcharge` | Removes one contender, not sufficient alone |
| usbmux relay (host usbmuxd → socat → guest socket swap; see [archive/](archive/)) | usbmux and lockdown work, but Xcode 26's CoreDevice reports `pairingState: unsupported` for an iOS 26 phone |
| VFIO of a whole USB controller | Works in principle, but takes every socket on that controller from the host, and chipset controllers usually share IOMMU groups with storage and network |
| Signing or `flutter run` over SSH | "User interaction is not allowed" (keychain); use the guest desktop session |
| Headless Android emulator on the same host without `-gpu host` | Bundled SwiftShader segfaults about 20 s in (unrelated to macOS, but bites on the same machines) |
| Leaving a fresh iOS 26.5 simulator to "settle" | Its `mediaanalysisd` runs CPU text-embedding inference at 600–700% for minutes. Disable it per device ([simulator.md](docs/simulator.md)); do not disable other simulator daemons |
| `plutil -replace` on a simulator's `disabled.plist` | Reads the dots in launchd labels as a key path and fails; use PlistBuddy |
| `pkill -f <pattern>` from an agent shell | Matches the agent's own command line; kill by PID |

## Rollback

- **Return the iPhone to the host:** stop the VM (or `device_del` the `usb-host` device), delete `/etc/udev/rules.d/99-macos-vm-iphone-port.rules`, `sudo udevadm control --reload-rules`, replug.
- **Broken guest:** stop the VM and reflink-copy the checkpoint back over the live disk. Identity and OpenCore are unaffected.
- **Remove the VRAM cgroup:** after the VM stops, `sudo rmdir /sys/fs/cgroup/macos-vm-<vm>`.
