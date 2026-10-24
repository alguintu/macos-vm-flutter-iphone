# Flutter Impeller shaders on Reims: fixes and investigation guide

Flutter can build and launch successfully in the iOS Simulator while rendering
fails in Reims's host-side Metal-to-Vulkan translator. On the reference setup,
two separate metal2vulkan defects first prevented pipelines from compiling,
then rendered gradients black. The combined patch fixes those observed cases.
It is not a claim of complete Flutter, Impeller or Metal compatibility.

## Symptoms and fixes

| Symptom | Diagnosis | Fix |
| --- | --- | --- |
| Black screen or app exit; `Metal refused a render pipeline`, `Abi(UnknownKey)`, `llvm.module.flags`, then `exec faulted` in the QEMU log | Flutter's Impeller AIR carries LLVM `Dwarf Version` and `Debug Info Version` flags. The AIR parser's closed allowlist rejected them. | `crates/metal2vulkan-air/src/abi/module.rs`: skip these debug-info flags like the existing `wchar_size` flag; continue rejecting other unknown flags. |
| Pipelines compile and flat colors work, but gradients are black | Impeller's linear-gradient shader reads stops from a device reference with a trailing `ColorPoint colors[1]`. The planner used its nominal `air.buffer_size` (32 bytes) as the dynamic-access bound. Later stops read zero under containment. | `crates/metal2vulkan/src/memory/plan.rs`: use `air.buffer_size` to bound dynamic references only in `AddrSpace::Constant`. Device references use their binding's extent. `memory/window.rs` documents the distinction; the planner test covers device/constant × sized/unsized. |

The buffer fix is based on address space and access structure, not a Flutter
shader name. `const device T&` is still in **Device** address space: C++ `const`
does not make it a Metal `constant T&`. Do not remove containment globally or
change the constant-buffer rule to make one image look right.

## Evidence and limits

The original 2026-10-23 run used Reims `2ce32093`, QEMU `bd95509`,
metal2vulkan `62cad6b`, Flutter 3.47.2, and an iOS 26.5 iPad Pro 13-inch (M5)
simulator inside the Intel macOS VM described in the main runbook.

- After the flag fix, the observed pipeline faults stopped and the app
  rendered, but its gradients remained black.
- The subsequent gradient harness compared constant and dynamic stop indexing.
  Before the buffer fix its sampled pixels were `(0,0,0,0)`; after it, the
  sampled RGB ramp ran from `(229,46,69)` to `(141,13,38)`, at both buffer
  offsets 0 and 256. App captures then showed the expected gradients.
- The original broad translator unit run recorded 2,948 passes and 547
  failures attributed to unavailable `spirv-val`, `spirv-dis` and `llvm-as`.
  **That was not a passing full suite.** Full upstream CI, other GPUs,
  other Flutter versions, and the dual-display combination remain unverified.
- Publication rechecks the patch against the exact public base and the
  repository's offline packaging checks. It does not restart or modify a VM.
  The installed reference QEMU binary matches the saved combined-fix build
  byte-for-byte; this is build provenance, not a new visual acceptance run.
- The publication-time `memory::` selection passed 112 tests initially; its
  three SPIR-V serialization tests passed on rerun after supplying SPIR-V
  Tools 2026.1 locally (115 passes combined). One explicitly ignored
  release-performance test was not run. This includes the four-way
  address-space/size regression, but is not the full upstream suite.

The runtime observations above are retained from the original investigation,
not repeated at publication. Extracted AIR/metallibs and private captures are
deliberately absent; create an authored minimal shader for shared repros.

## Reproduce the source and build

Use a **new** build directory and the pinned versions first. Read the host
dependency list in [the runbook](../runbook.md#1-host-prerequisites-fedora-44).
Rust/Cargo, cbindgen, CMake, Ninja, pkg-config and the QEMU development
dependencies must be available. These commands prepare source and build;
they do not install, select a QEMU version, or start a VM.

```bash
repo=$HOME/Projects/macos-vm-flutter-iphone
build=$HOME/.cache/reims-flutter-shaders
test ! -e "$build" || exit 1
mkdir -p "$build"
python3 - "$repo" "$build" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
repo, build = map(Path, sys.argv[1:])
patches = repo / 'patches/flutter-shaders'
manifest = json.loads((patches / 'manifest.json').read_text())
entry = manifest['metal2vulkan']
patch = patches / entry['patch']
assert hashlib.sha256(patch.read_bytes()).hexdigest() == entry['patch_sha256']
for name, relative in [('metal2vulkan', 'metal2vulkan'),
                       ('reims_vgpu', 'reims-vgpu'),
                       ('qemu', 'reims-vgpu/vendor/qemu')]:
    entry = manifest[name]
    dest = build / relative
    dest.mkdir(parents=True, exist_ok=True)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(dest), *args], text=True)
    git('init')
    git('remote', 'add', 'origin', entry['url'])
    git('fetch', '--depth=1', 'origin', entry['revision'])
    git('checkout', '--detach', 'FETCH_HEAD')
    assert git('rev-parse', 'HEAD').strip() == entry['revision']
    if name == 'metal2vulkan':
        git('apply', '--check', str(patch))
        git('apply', str(patch))
manifest_path = build / 'reims-vgpu/Cargo.toml'
with manifest_path.open('a') as out:
    out.write('\n[patch."https://github.com/steelbrain/metal2vulkan"]\n')
    for crate in ('metal2vulkan', 'metal2vulkan-runtime'):
        path = str(build / 'metal2vulkan/crates' / crate)
        out.write(f'{crate} = {{ path = {json.dumps(path)} }}\n')
PY

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
  --disable-docs --disable-tests --disable-werror
ninja -j2
ninja install
test -x "$build/qemu-install/bin/qemu-system-x86_64"
```

Keep the generated Cargo.lock in the build evidence. The local path override
intentionally makes Cargo resolve the patched crates; do not accidentally
build the original git dependency. Inspect `cargo tree -p metal2vulkan` from
the Reims tree and its build dep-info for the intended source paths. QEMU
links Reims statically, so rebuilding only the Rust library is insufficient.
`--disable-tests` disables QEMU's build-time tests, not a claim they passed.

Run the focused memory checks from the patched metal2vulkan tree with
`spirv-val` and `spirv-dis` on PATH (the filter also selects serialization tests):

```bash
cd "$build/metal2vulkan"
cargo test -p metal2vulkan --lib memory::
```

For a full translator gate, install LLVM and SPIR-V Tools first and follow
the pinned tree's `AGENTS.md` and `CONTRIBUTING.md`. Reims has its own
`cargo xtask check` and integration gates. The focused checks and this
reproduction package do not replace upstream checks.

## Runtime acceptance and rollback

Use a powered-off disposable copy/snapshot of the guest on the VM drive
(`/mnt/vms` on the reference host), the existing VRAM-capped launcher and USB
lifecycle. Do not switch a running VM's binary or combine a VM boot with
unrelated GPU tests. Record the old QEMU selector and candidate binary hash
before deliberately installing/selecting the complete candidate distribution.
Keep the old distribution intact; do not overwrite its executable.

After a cold boot, verify the actual QEMU process executable, then launch the
same minimal repro and Flutter screen. Check both rejection logs and pixels:
flat colors, first/middle/last gradient stops, and nonzero buffer offsets.
Check redraw and interaction as well as a static screenshot. No errors in a
log alone proves neither correct rendering nor acceptable GPU/CPU load.

Rollback: shut down macOS, confirm QEMU exited, restore the recorded previous
QEMU selector/distribution, and restart through the same capped launcher.
If testing modified the guest, restore only the task's disposable snapshot.
The shader patch needs no OpenCore, guest-driver, app-source or signing change.

## Continuing when another shader fails

1. **Freeze the failing configuration.** Record Flutter/engine revision,
   simulator runtime and device, Reims/QEMU/metal2vulkan commits, local diffs,
   host GPU/driver, QEMU executable hash and build dependency provenance.
   Confirm this patch is actually compiled into the running executable.
2. **Classify the failure before editing.** A pipeline rejection starts at
   `metal2vulkan-air/src/abi/` (metadata) or the diagnostic's parser/lowering
   stage. A compiled pipeline with wrong pixels needs a data/semantics repro:
   inspect `memory/plan.rs`, `memory/window.rs`, binding sizes/offsets and
   address spaces, then lowering/SPIR-V output as evidence warrants. Black
   pixels alone do not identify this particular buffer bug.
3. **Separate the shader from the app.** Reduce the screen to a stock Flutter
   gradient or other failing primitive. Compare flat color versus the failing
   operation; for buffers compare constant versus dynamic indexing, sized
   versus unsized device inputs, and offsets 0 versus a nonzero aligned
   offset. Use distinctive values for every element so zero/first-element
   substitution is visible. Keep app layout and texture issues separate.
4. **Make an authored minimal Metal test.** Compare expected pixels/values
   with the translated path; compare native Metal when available. A native
   comparison was not performed by this publication task. Extracted Flutter
   or guest shaders may help private diagnosis, but do not publish their AIR,
   metallibs, translated dumps or logs containing shader bodies. Shared tests
   should contain source you authored and numeric expected results.
5. **Fix the structural cause and prove the boundary.** Add a regression that
   fails on the pinned baseline and passes with the fix. Preserve constant
   buffer bounds, unknown-input errors and out-of-binding containment. Never
   dispatch behavior on an app name or shader hash, accept every unknown
   metadata flag, or disable validation to turn a fault into silent corruption.
6. **Validate progressively.** Run the affected CPU tests, then the complete
   applicable upstream gate with required tools, then an isolated runtime
   comparison and the original app. Record exactly which passed, missing
   tooling, baseline failures, GPU/CPU load and remaining visual gaps. Keep
   patch/source hashes and build commands together for the next agent.

The [Simulator daemon CPU issue](simulator.md) is separate. A successful
physical-iPhone run also does not validate the simulator translator: the real
phone executes its own Metal path.
