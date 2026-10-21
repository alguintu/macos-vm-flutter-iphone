# Source patch provenance

The manifest pins the exact public base revisions and SHA256 of each patch.
Apply only to those bases using `scripts/multimonitor/prepare-sources.py`.
See `docs/multimonitor.md` at the repository root for build and acceptance.

- `reims-vgpu.patch`: opt-in early port discovery, relative capture callbacks,
  guest-aware companion/relay and tests, local cursor routing/overlay, and
  Linux SDL renderer support. The Cargo.lock source correction is a clean-build
  prerequisite at the pinned metal2vulkan revision. The patch was exported from
  the isolated experimental tree; unrelated mmio formatting was excluded.
- `qemu.patch`: local socket pointer device and per-head display wiring, tested
  with the paired Reims C API. It is an agent-assisted local experiment, not an
  upstream contribution. QEMU's base-tree `AGENTS.md` and code-provenance policy
  do not permit agent-generated output in upstream contributions. Do not
  forward this patch as an upstream submission.

The patches retain their upstream licensing: Reims is
`GPL-2.0-or-later OR LGPL-3.0-or-later`; QEMU is GPL-2.0, with the new pointer
file's SPDX declaration specifying GPL-2.0-or-later. Full license texts are
in `../licenses/`. Consult the pinned repositories for per-file notices and
third-party licenses when building/distributing binaries. No upstream
endorsement or acceptance is implied.

No Apple binaries or VM images are included. The separate OpenCore patch tool
contains only guarded replacement instructions and requires the user's own
exact original binary. It refuses other versions and verifies the final hash.
