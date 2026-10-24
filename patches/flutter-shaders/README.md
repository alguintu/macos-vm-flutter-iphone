# Flutter shader patch provenance

`metal2vulkan.patch` contains the two local fixes used by the reference machine:
LLVM debug-info module flags and dynamically indexed device-reference buffers.
It includes the memory-planner regression test. The exact public source pins
and patch SHA256 are in `manifest.json`; instructions and the continuation
guide are in [docs/flutter-shaders.md](../../docs/flutter-shaders.md).

The patch is byte-identical to the combined patch exported on 2026-10-23 from
the local working source. It applies to public metal2vulkan commit
`62cad6be548f7ebe8d901fdc754edf20acaae1b9`. A local snapshot commit added only
Cargo's empty `.cargo-ok` marker; that marker and local commit are not needed
or included. The Reims and QEMU pins describe the tested integration, not
changes to those upstream projects. This recipe is independent of the
dual-display patches; a combined build has not been validated here.

The source retains metal2vulkan's license:
`GPL-2.0-or-later OR LGPL-3.0-or-later`, at the recipient's choice. Full texts
are in [../licenses/](../licenses/), and per-file notices remain in the
pinned upstream source. No binaries, extracted shaders, private app data or
VM images are included. This is a reproducibility package, not an upstream
submission or a claim that upstream has accepted either fix.
