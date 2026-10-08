# Project-owned Mac workloads

This directory owns Coimbra's render orchestration, source/artifact selections,
encoding, geometry, camera implementation and project acceptance checks. It is
not a runner service, an authorization mechanism or a general command executor.

## Execution boundary

The reviewed Mac control plane retains owner admission, runner selection,
permissions, resource ceilings and an immutable `uses: ...@<full commit SHA>`
reference. The composite Actions here run within that caller's already-approved
job. They add no public self-hosted workflow trigger, credentials, repository
selector, shell input or new Mac registration.

Changing this repository's default branch does not update the installed runtime.
Adoption requires a reviewed revision change in the owning control plane. Project
algorithms and settings must not be copied back into infrastructure to make that
adoption easier.

## Layout

- `coimbra_027` through `coimbra_037`, and `coimbra_v2_001`: the eleven fixed
  historical workflow lanes, each with a sanitized `result` output.
- `lanes.json`: the exact frozen project inputs previously held in job environments.
- The nine `run_*` / `render_*` helper files: render, encode and verification code.
- `manifest.json`: Git-blob identities of those helpers. Eight were moved byte for
  byte. The WebGPU helper changes only how it locates the execution workspace;
  its test reconstructs and hashes the original file.
- `materialize.py` and `prepare.py`: prepare the fixed compatibility file locations
  and the selected checked-in lane environment. They do not execute render code,
  fetch URLs, inspect credentials or accept user-selected paths.
- `recover_036`: the existing fixed preserved-workspace artifact recovery, with
  no checkout or rerender.
- The root `action.yml`: a CI-only package preparation/syntax preflight, with no
  rendering, GUI, Bluetooth, external calls or device I/O.

The source checkout at `coimbra/`, artifact names, source digests, rendering
parameters, attribution and project verifiers are preserved during this move.
The 036 route still runs the 640x480, native 60 fps smooth-camera **preview**;
it does not promote the quality64 production variant. Review-only, preview and
human-acceptance distinctions remain unchanged for every lane.

## Verification

```sh
python -m pip install 'PyYAML==6.0.3'
python -m unittest discover -s tests -p 'test_mac_*.py' -v
```

These tests check hashes, shell/Python syntax, fixed action definitions and real
preparation into temporary workspaces, including symlink/traversal/conflict
rejection. They do not import Blender or render a frame.

The infrastructure migration must additionally compare each moved action's steps
and environment to the previous reviewed workflow, retain its authority envelope,
and run the pinned preparation preflight before adopting the new package.
A green code or preparation check is not evidence of a new successful video render.
