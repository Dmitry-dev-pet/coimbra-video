# SPEC-COIMBRA-BLENDER-1 — Governed Coimbra slow terrain flight

> **Status:** Draft v1 · **Owner:** repository
> **apatch artifact:** `spec:SPEC-COIMBRA-BLENDER-1`

## 0. Motivation

The Coimbra Blender bridge must not treat a JSON plan as self-authorizing.
The exact plan is executable only inside an APatch SDD session bound to this
requirement, its live content hash, a frozen verifier, and a bounded write/tool
envelope.

## R1 Execute and verify the exact slow-flight plan

`COIMBRA-BRIDGE-003-SLOW` must execute only when APatch admits the exact plan
SHA-256, the declared Blender operations, and the declared output paths.
Protected `City_*` geometry and animation must remain unchanged. The final
480p / 30 fps / 12 second MP4, semantic verification report, and APatch SDD
verification must all pass.

(verify: python3 scripts/verify_apatch_blender_evidence.py --contract contracts/COIMBRA-BRIDGE-003-SLOW.json --report bridge_output_003/slow-verification.json --probe verification/COIMBRA-BRIDGE-003-SLOW.probe)

## Non-goals

- APatch does not govern the upstream construction of the pinned terrain base.
- This requirement does not claim sealed OS-level containment.
- Until APatch exposes a first-class external-mutation recording primitive,
  Blender effects are admitted and SDD-verified but are not represented as
  APatch-native mutation ledger rows.
