# Two displays with responsive border crossing

Status on 2026-10-22: **local physical acceptance on Fedora KDE/Wayland + Intel Tahoe 26.7**. The user described the final captured cursor as “visible, aligned, and lighter” and “workable.” It crosses the macOS display arrangement and clicks land where the visible cursor points. This is an opt-in experimental patch set, not an upstream Reims release.

The single-display rollback stays available. Do not update the copied OpenCore image with `reims-ctl update-opencore`: that would replace the version-specific guest patch. This recipe adds no Apple binaries, OSK, machine identity, signing material or disk images to the repository.

## What is needed, and why

1. Reims must expose the display-port count before the guest's version negotiation. `REIMS_VGPU_EARLY_DISPLAY_PORTS=1` changes only that discovery behavior.
2. The exact Intel APVDisplayPort binary needs port identity/index, secondary aperture and per-framebuffer readiness fixes. The patcher checks the whole original binary hash and all old instruction bytes, writes only a copied OpenCore image, and verifies the EFI member readback.
3. The ordinary tablet protocol loses the target display. An experimental QEMU socket input device preserves the head ID and button transitions; an SSH companion maps that ID to the macOS display's vendor/serial and current logical bounds.
4. Relative capture alone crossed correctly but felt heavy even with host acceleration. The accepted mode integrates accelerated motion on the host, uses destination viewport scaling, sends absolute coordinates, and draws a local cursor at those same quantized coordinates. Its transparent SDL child is independent of guest Vulkan frames. **Linux must enable SDL's renderer subsystem** for the Wayland texture framebuffer. A video-only SDL build creates the popup but fails to draw it.

The cursor is a compositor-rendered overlay, not a native hardware cursor plane. We have physical feedback, not measured end-to-end latency equality. The QEMU patch is an agent-assisted local experiment: do not submit it upstream under QEMU's current provenance policy. Reims upstream contribution needs its own review and full checks; this repo is a reproducibility record, not an upstream submission.

## 1. Prepare pinned source trees

Use a new build directory; the script refuses an existing destination. It downloads the two exact commits, validates patch hashes, and applies the patches. It does not install anything or start a VM.

```bash
repo=$HOME/Projects/macos-vm-flutter-iphone
build=$HOME/Build/reims-multimonitor
python3 "$repo/scripts/multimonitor/prepare-sources.py" "$build"
```

Pins and patch SHA256s: [`manifest.json`](../patches/multimonitor/manifest.json).

- Reims: `2ce320931917e8a07a00243f53656f8cd11306b2`
- QEMU: `bd95509aa307f48b13fe8497d8a1b64267cb4c3e`
- metal2vulkan remains the Reims Cargo.toml pin, `62cad6be548f7ebe8d901fdc754edf20acaae1b9`; the patch includes the missing lockfile source entries needed by a clean checkout.

Use the host dependencies from the main runbook, plus Git, Rust/Cargo, cbindgen, make, CMake, Ninja, Python 3, pkg-config, clang/lld, mtools and `qemu-img`. The installed reims-ctl distribution also supplies `qemu-img` at `~/.local/share/reims-ctl/qemu/current/bin/qemu-img`.

Build while the GPU is free and the VM is off:

```bash
export CARGO_TARGET_DIR="$build/target"
export CARGO_BUILD_JOBS=2
cd "$build/reims-vgpu"
cargo xtask dist
export PKG_CONFIG_PATH="$CARGO_TARGET_DIR/dist-vulkan/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
mkdir "$build/qemu-build"
cd "$build/qemu-build"
"$build/reims-vgpu/vendor/qemu/configure" \
  --prefix="$build/qemu-install" --target-list=x86_64-softmmu \
  --enable-kvm --disable-sdl --enable-gtk --enable-slirp --enable-pvg \
  --disable-docs --disable-werror
ninja -j2 qemu-system-x86_64
```

`--disable-sdl` above disables QEMU's independent SDL display backend. Reims's statically bundled SDL, including its renderer, remains enabled. Its guest windows render through Vulkan.

CPU checks (no GPU suite alongside a VM):

```bash
cd "$build/reims-vgpu"
cargo test -p reims-vgpu-window --lib
python3 -B -m unittest discover -s scripts/multimonitor -p 'test_*.py' -v
python3 -B scripts/multimonitor/test_qemu_pointer.py \
  --qemu "$build/qemu-build/qemu-system-x86_64" \
  --firmware-dir "$HOME/.local/share/reims-ctl/qemu/current/share/qemu"
```

The integration tree's merge gate is still `cargo xtask check` plus any affected suite checks documented by Reims. The focused tests and this local acceptance do not replace that gate.

## 2. Patch a new OpenCore copy

Shut the VM down and verify its PID is gone. Keep all images, including temporary images, on your VM drive. The output parent must already exist; the output file must not exist. Source OpenCore and guest disk are never overwritten by this tool.

```bash
export PATH="$HOME/.local/share/reims-ctl/qemu/current/bin:$PATH"
python3 "$repo/scripts/multimonitor/patch-opencore.py" \
  "$HOME/.local/share/reims-ctl/vms/tahoe/opencore.qcow2" \
  /mnt/vms/macos/tahoe/opencore-multimonitor.raw
```

Only this APVDisplayPort version is supported:

- Original SHA256: `02f2065b7ff64e8da80ea64603ee85f9667da994515e29a22eebc9524cf97f8f`
- Patched SHA256: `1cce406c091143a677831890ae426ccaf5ddd75a15042656886b6c622bcc816e`

If the hash differs, stop and investigate that version. Do not remove the assertions or apply offsets to another binary. The existing source must already contain APVDisplayPort at `EFI/OC/Kexts/APVDisplayPort.kext/Contents/MacOS/APVDisplayPort`. The patcher discovers the single GPT EFI partition instead of assuming an offset. It does not edit your OpenCore identity or config.plist.

## 3. Configure the opt-in wrapper

Copy [`config/multimonitor.json.example`](../config/multimonitor.json.example) to `~/.config/reims-multimonitor.json` and replace **every** placeholder with absolute paths on your host. The wrapper runs as your normal VM user and reads that user's config. `firmware_dir` points at the installed QEMU firmware directory, not the OpenCore image. Socket paths cannot contain commas and must fit Unix's path limit.

The default `snapshot: true` makes writable guest/firmware drives disposable; `snapshot_dir` places temporary overlays on `/mnt/vms`. **Guest changes made in this mode are discarded on exit.** Use it for the first acceptance test. After acceptance, set `snapshot: false` deliberately for normal persistent development, with powered-off backups in place. This repository has not switched anyone's installed launcher automatically.

Start under the existing 4 GiB VRAM cap:

```bash
pkexec "$repo/scripts/start-vm-limited" --vm tahoe --limit 4G \
  --qemu "$repo/scripts/multimonitor/qemu-multimonitor"
```

If you installed the optional [temporary USB lease](usb-lifecycle.md), add `--usb-lease`. Keep the existing EHCI/usb-host device config; the mouse wrapper does not alter it. Do not install both a permanent USB reservation rule and the temporary lease rule for the same phone.

The wrapper refuses unexpected VM names/devices/OpenCore arguments, active sockets and non-socket files. It enables the three opt-ins, creates private sockets, and does not print QEMU argv (which contains private data). The guest's advertised choices are 1920×1080, 720×1440 and 1080×1920 at 60 Hz; these modes are configurable. The reference layout is 1920×1080 at (0,0) plus 720×1440 at (1920,0).

## 4. Connect the companion

Guest Remote Login and the `tahoe` SSH alias must already work. The helper uses `/usr/bin/python3`, ctypes and macOS frameworks; no pip dependencies. It requires existing Accessibility trust and checks it without changing permissions. Grant the actual process requested by macOS in System Settings → Privacy & Security → Accessibility if needed; do not disable TCC or edit its database. Verify the helper reaches `READY 1`; a trust error is not success.

After the desktop is ready, in a host terminal:

```bash
scp "$build/reims-vgpu/scripts/multimonitor/guest_pointer.py" tahoe:/tmp/guest_pointer.py
python3 -B "$build/reims-vgpu/scripts/multimonitor/relay.py" \
  --socket "$HOME/.local/state/reims-pointer/pointer.sock" \
  --layout-socket "$HOME/.local/state/reims-pointer/cursor-layout.sock" \
  --ssh-host tahoe --guest-helper /tmp/guest_pointer.py --heads 2
```

Use the socket directory from your JSON if different. Leave the relay running during use; reconnect it after each VM boot. If startup reports ambiguous/unavailable display identity while macOS is still booting, wait for the desktop and retry. The current default expects one apple-gfx device, display vendor 4102 and serials 1/2. The companion identifies displays by these fields, never enumeration order. Mirroring, missing/ambiguous identities and invalid maps are refused.

In macOS **System Settings → Displays → Arrange**, use an extended desktop and place the display rectangles where you want the cursor to cross. Linux window positions do not control this arrangement. Click a VM window to capture. Move across its connected guest border and click on the destination; **Ctrl+Alt+Super releases capture**. Layout changes or relay loss also release held input/capture; click to recapture afterward.

## Acceptance and shutdown

Verify visible motion, crossings both directions, clicks after crossing, and then any drag/scroll/modifier behavior your workflow needs. Do not accept invisible clicks or an apparently responsive cursor with offset clicks. A local overlay cannot appear in a QMP guest-framebuffer screenshot; inspect the real host windows.

The accepted five-minute run had zero FIFO resumes, peak CPU 68.375°C and GPU junction 61°C. An earlier unrelated-to-this-build input investigation had sustained load with thousands of FIFO resumes; its root cause is **not established**. Monitor CPU temperature, GPU activity and the QEMU log during first acceptance. Do not run an unrelated GPU workload alongside the VM. A 4 GiB VRAM cap is not a temperature or CPU guard. The local test stopped on CPU ≥85°C, GPU junction ≥90°C, 100 FIFO-1 resumes, or >12 CPU cores / >85% VM GPU-engine activity sustained 20 seconds, plus a five-minute deadline. These thresholds describe the reference run, not universal hardware limits.

Normal shutdown: Apple menu → Shut Down, then wait for QEMU to exit. Do not close a Reims display window as a shutdown shortcut. The original single-display launcher remains rollback: omit `--qemu` on the capped launcher. Stop the relay with Ctrl-C. If a USB lease was enabled, verify its service is inactive and the phone is visible to Fedora again.

Known remaining boundaries: guest-driven pointer warps are not reconciled while captured; only one guest desktop per process; broad cursor-shape, dragging, mixed-DPI, alternate compositor, sleep/wake and rearrangement acceptance are incomplete. The portable packaging scripts have offline tests and a real copied-image patch/readback check; first boot on a different host is still required.
