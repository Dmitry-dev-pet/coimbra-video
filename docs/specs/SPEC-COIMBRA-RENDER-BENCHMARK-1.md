# Coimbra 029 — Mac rendering strategy benchmark

## Goal

Measure the fastest safe execution strategy for the accepted Coimbra scene and
compare it with the already accepted GitHub Actions CPU evidence.

This is performance measurement only. It does not change production imagery or
renderer acceptance.

## Frozen workload

Use the exact accepted 026 packed scene and frames 181 through 210.

All modes must preserve:

- frozen scene SHA and protected-state SHA;
- 1600 × 1000 framing;
- accepted 16-sample Cycles settings;
- denoising and adaptive sampling;
- production camera;
- native integer frames.

## Modes

Measure the same 30-frame workload in these Mac modes:

1. M4 CPU;
2. M4 Metal, one Blender process;
3. M4 Metal + CPU, one Blender process with both devices enabled;
4. M4 Metal, two concurrent Blender processes, split as 181–195 and 196–210.

The two-process metric is wall-clock time from launching both processes until both
have exited successfully.

## GitHub Actions comparison

Do not rerun the expensive accepted 026 workflow just to obtain a CPU number.

Use the immutable accepted evidence from:

- run: `36646652931`;
- job: `109671765388`;
- frames: 181–210;
- Blender render time through frame 210: `24:22.663` = `1462.663 s`;
- one GitHub-hosted CPU runner.

For portfolio-level context, the accepted 026 workflow used 12 render jobs in
parallel. The render phase ran from 23:45:28Z until the slowest shard completed at
00:11:13Z, or approximately `1545 s`. The complete workflow from creation through
final verification took approximately `1748 s`.

## Output

Produce a summary containing:

- wall seconds and seconds/frame for every mode;
- speedup versus one GitHub-hosted CPU runner;
- Metal×2 speedup/slowdown versus Metal×1;
- Metal+CPU speedup/slowdown versus Metal×1;
- M4 CPU versus GitHub-hosted CPU;
- fastest measured Mac mode.

No mode is promoted automatically. The measured fastest stable mode becomes input
to a separate execution-policy decision.
