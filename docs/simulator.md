# iOS Simulator: sustained 600% CPU from `mediaanalysisd`

A freshly booted iOS 26.5 Simulator in this VM can hold 6–8 host CPU cores for
minutes while its screen sits idle, with GPU bursts to 99%. The cause is a
background daemon inside the simulated device, not the VM, Reims or the display
setup. The fix is to disable that one daemon per simulator device. It has been
applied and verified on the reference machine.

## Diagnosis (reference machine, 2026-10-21)

Reproduce only when you need fresh evidence; the load is real heat on the host.

1. Boot a simulator device and watch host load. Here QEMU held about 8 CPU
   core-equivalents with near-zero graphics-engine use once the burst ended.
   A host thread sample put the time in QEMU's KVM vCPU threads, not its
   rendering workers, so the load comes from guest code.
2. Find the guest process:

   ```bash
   ssh tahoe 'top -l 2 -o cpu -n 8 -stats pid,command,cpu | tail -9'
   ```

   The simulated device's `mediaanalysisd` ran at 610–714% CPU.
3. Sample it read-only for 3 seconds (`ssh tahoe 'sample <pid> 3'`). The hot
   stack was `MADServiceTextProcessingTask` → `MADTextEmbeddingTask` →
   `MADSharedTextEncoder` → Core ML `MLE5Engine` → Espresso
   `BnnsCpuInferenceOperation::ExecuteSync` → `BNNSGraphContextExecute_v2`:
   background text-embedding inference running on the CPU.

The same daemon and load were reported independently on a fresh iOS 26.5
simulator on Apple hardware (about half the CPU of the first ten minutes,
peaking near 660%), with the same fix:
[Llamenos-Hotline/llamenos-platform#2060](https://github.com/Llamenos-Hotline/llamenos-platform/issues/2060),
[PR #2061](https://github.com/Llamenos-Hotline/llamenos-platform/pull/2061).
That PR warns against disabling other simulator daemons. This procedure
disables only these two labels.

## Where the setting lives

launchd inside a simulator (`launchd_sim`) keeps its enable/disable overrides on
the **Mac side**, not in the device's data folder:

```text
/private/var/tmp/com.apple.CoreSimulator.SimDevice.<UDID>/disabled.plist
```

It is a dictionary of launchd label → boolean, `true` meaning disabled. It was
found with a throwaway device: disable the daemon, shut down and boot again (the
setting held and the daemon stayed off), then `lsof` on that device's
`launchd_sim` pointed at this directory. The directory survives VM reboots. It
already exists for any device that has booted; for a never-booted device you
can create it in advance, and the first boot honours it (verified on an iPad
Pro 13-inch (M5)).

Labels to disable: `com.apple.mediaanalysisd` and `com.apple.mediaanalysisd.service`.

## Apply

All commands run in the guest. Prefix with `ssh tahoe '…'` from the host, or run
them in the guest's Terminal. List devices and their UDIDs:

```bash
xcrun simctl list devices available
```

### Booted device

```bash
u=YOUR-DEVICE-UDID   # from simctl list
for l in com.apple.mediaanalysisd com.apple.mediaanalysisd.service; do
  xcrun simctl spawn "$u" launchctl disable "user/foreground/$l"
done
```

Disabling does not stop a daemon that is already running. Restart the device
once (`xcrun simctl shutdown "$u"`, then boot it again) for the change to take
effect.

### Shut-down or never-booted device

Use this when you must not boot the device. Edit the file with PlistBuddy:
`plutil -replace` reads the dots in the labels as a key path and fails. Back up
an existing file first, since booted devices also keep their default overrides
in it.

```bash
u=YOUR-DEVICE-UDID   # from simctl list
d=/private/var/tmp/com.apple.CoreSimulator.SimDevice.$u
f=$d/disabled.plist
mkdir -p -m 700 "$d"
[ -f "$f" ] && cp -p "$f" "$f.bak-$(date +%Y%m%d)"
for l in com.apple.mediaanalysisd com.apple.mediaanalysisd.service; do
  /usr/libexec/PlistBuddy -c "Set :$l true" "$f" >/dev/null 2>&1 \
    || /usr/libexec/PlistBuddy -c "Add :$l bool true" "$f"
done
plutil -lint "$f"
```

`Set` fails when the key is missing, and `Add` then creates it (and the file,
if needed). Leave other keys in the file alone.

## Verify

Boot the device, then:

```bash
u=YOUR-DEVICE-UDID   # from simctl list
xcrun simctl spawn "$u" launchctl print-disabled user/foreground | grep mediaanal
xcrun simctl spawn "$u" launchctl list | grep mediaanal
```

Expect both labels `=> disabled` from the first command and no output from the
second. For a shut-down device, `plutil -p
/private/var/tmp/com.apple.CoreSimulator.SimDevice.<UDID>/disabled.plist` should
show both labels `=> true`.

Reference result on the iPad Pro 13-inch (M5), with the fix pre-seeded before
its first boot: the daemon never ran. QEMU averaged 13.3 cores during first boot
(other indexing work, see below), 7.2 during the Xcode build, **1.8 with a
Flutter app running** and 1.2 afterwards. CPU stayed at or below 71.5 °C and
GPU junction at or below 62 °C.

## Undo

Booted device: `launchctl enable` in place of `disable` in the loop above, then
restart the device. Shut-down device: set both keys to `false`, or restore the
`.bak-<date>` copy.

## Limits

- Per device. Apply it to every device you boot, and again after
  `simctl erase`, deleting and recreating a device, a new simulator runtime,
  or anything that cleans `/private/var/tmp`.
- Verified on the iOS 26.5 runtime (23F77) with Xcode 26.6. Other runtimes may
  use different labels; confirm with `launchctl list` in a booted device first.
- Simulator features that rely on media analysis (for example Photos search and
  Visual Look Up) may stop working; this was not tested. Flutter app development
  was unaffected.
- This removes the sustained CPU load, not every spike. A device's first boot
  still does a minute or so of other indexing work. While the Mac sits at its
  lock screen, `VTDecoderXPCService` can use 180–285% CPU decoding the Aerial
  wallpaper in software; unlock the Mac or use a static wallpaper. Short
  97–99% GPU bursts while the Simulator starts were seen on the original
  single-display stack too, and their cause is not established.
