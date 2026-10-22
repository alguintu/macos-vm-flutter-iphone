# Headless iPhone development

Reims supports a guest display without a host window. Keep the macOS desktop
session running for the existing signing workflow; use SSH to start commands and
read logs, and the physical iPhone for the application UI.

## Start and recover the display

With the VM stopped, save its configuration and a disk checkpoint on the VM
drive. Reflink the large disk on that same filesystem; copy small configuration
and firmware files normally when they are on another filesystem.

```sh
reims-ctl set tahoe --env REIMS_VGPU_WINDOW=0
reims-ctl command tahoe
```

The generated command must export `REIMS_VGPU_WINDOW=0`. `-display none` alone
does not suppress Reims's own windows. Start through the existing capped launcher
and installed USB lease. On Aeris, the fixed-purpose installed helper is:

```sh
sudo -n /usr/local/libexec/eris-start-tahoe --single
```

Other hosts should use their configured capped launcher and USB lease as described
in [usb-lifecycle.md](usb-lifecycle.md). Do not install or replace lease services
merely to enable headless mode.

Verify SSH, the logged-in desktop user, and the phone:

```sh
ssh tahoe 'sw_vers; stat -f %Su /dev/console'
ssh tahoe 'xcrun devicectl list devices'
```

Restore visible mode by shutting down macOS normally, removing only this override,
then restarting through the same capped launcher:

```sh
reims-ctl set tahoe --env REIMS_VGPU_WINDOW=
```

QMP screendump and `reims-ctl view tahoe` also provide diagnostic access without
changing the normal host display mode.

## Run and debug

Use the already configured Mac account, developer signing identity, and trusted
phone. Keep the phone unlocked during installation and debugger attachment.
The following examples use launchers already present on the reference guest;
they are not installed by this repository. Reuse an existing idle Mac Terminal
session when available, after checking its foreground job and directory. Use
`open -a Terminal` when a new session is needed:

```sh
ssh tahoe 'open -a Terminal ~/src/eris_usb_counter/scripts/test-on-iphone.command'
ssh tahoe 'tail -n 40 /tmp/eris-counter-test-gui.log'
# After the test exits, launch the ordinary interactive app:
ssh tahoe 'open -a Terminal ~/src/eris_usb_counter/scripts/run-on-iphone.command'
ssh tahoe 'tail -n 40 /tmp/eris-counter-run.log'
```

Run one build/debug owner at a time for this phone and checkout. The Mac terminal
holds the Flutter session even when an agent's SSH command exits. The existing
run launcher fixes the VM service/DDS ports at 55230/55231.

For agent-controlled hot reload, add `--pid-file=/tmp/your-app-flutter.pid` to the
`flutter run` invocation. Flutter creates that file only once its signal handlers
are ready and removes it on exit. Verify the PID still belongs to that app's
Flutter command before sending `kill -USR1 <pid>` over SSH. `SIGUSR1` requests hot
reload; `SIGUSR2` requests hot restart. Do not use a broad `pkill dart`.

The existing StarMiles launcher on the reference guest is
`~/run-starmiles-iphone.command`. It runs code generation, then a debug build with
the staging Dart definitions and the existing local Maps configuration. It uses
VM service/DDS ports 55240/55241. Launch it with `open -a Terminal` over SSH and
read `/tmp/starmiles-iphone-run.log`. Preserve the guest's existing iOS signing
changes; this workflow does not require publishing a release.

A human can use an existing host terminal for guest administration:

```sh
ssh -t tahoe
```

Enter guest `sudo` passwords directly in that terminal. Guest sudo authorization
does not unlock the signing keychain for an SSH process; the GUI-session signing
path remains relevant.

Reuse suitable terminals, debug sessions, and tunnels instead of accumulating
windows and background processes. Open a separate session for active concurrent
work or isolation; never interrupt another session to reuse it. Close completed
task-created sessions and stop unneeded task-owned processes, preserving anything
the user deliberately left running.

## Shut down and verify resource release

Stop the app's Flutter debug session, then request a normal macOS shutdown:

```sh
ssh tahoe 'osascript -e '\''tell application "System Events" to shut down'\'''
```

Terminal can block shutdown with a hidden confirmation to terminate running
processes. Inspect the guest through QMP screendump or a console, check which
processes the dialog names, and confirm termination when they belong to the work
being stopped. A successful AppleScript request does not prove power-off.

Verify the VM manager reports `stopped`, its cgroup has no processes, the temporary
USB lease is inactive with its marker removed, and host usbmuxd lists the iPhone
again. On Aeris, shutdown also returned the VM's `dmem.current` to zero. A remaining
4 GiB `dmem.max` is a ceiling, not reserved VRAM. Other desktop applications can
still use GPU memory after the VM exits.

## Verification

2026-10-22: installed single-display QEMU booted with
`REIMS_VGPU_WINDOW=0`; macOS 26.7 answered SSH, console user `drei` and GUI session
501 were available. The phone reported wired transport, paired status, a connected
debug tunnel, Developer Mode enabled, and available developer disk services. The
existing 4 GiB VRAM cap and temporary USB lease remained active. The physical
counter integration test passed with exit 0: signed build (27.3 seconds), install
and launch (21.8 seconds), and three taps checked against counts 1, 2, and 3.
Normal counter-app hot reload also passed over SSH: `SIGUSR1` reloaded one changed
library in 769 ms. The temporary label change was then restored and the counter
session stopped when switching to StarMiles. An earlier counter session reported
`Lost connection to device` after the user locked/left the app; repeating with the
phone foregrounded succeeded.

StarMiles also ran headlessly using its existing staging launcher: guest commit
`42adc108`, app `2.0.0+24`, signed build 31.8 seconds, installation/launch 27.2
seconds, and a connected Dart debugger. SSH-triggered reload/reassembly completed
in 219 ms with zero changed libraries. Existing guest iOS signing edits were
preserved; no StarMiles source change or release publication was made. Drei
confirmed the app was visible and interactive on the phone. Normal shutdown and
host iPhone rediscovery were subsequently verified after accepting Terminal's
confirmation. Authenticated
business workflows, sleep/reboot behavior, and long-duration stability remain
separate checks.
