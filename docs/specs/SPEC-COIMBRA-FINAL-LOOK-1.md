# SPEC-COIMBRA-FINAL-LOOK-1 — Polo II final still treatment

> **Status:** photo-only final-look experiment

015 makes no geometry, material or lighting changes to the accepted 014 scene.

## Render

Use the selected lower 55 mm composition from the Polo II photo stack.

Render one master at exactly 3200×2000, which is 2× the delivery resolution in
both dimensions.

Do not save or upload a Blender artifact.

## Anti-alias / cleanup

Downsample the master to 1600×1000 with Pillow LANCZOS. This is the only
edge-cleanup operation; do not blur geometry or repaint objects.

## Grades

Generate exactly three deterministic grades from the same downsampled master:

- neutral — low-contrast, restrained saturation;
- warm — subtle warmer highlights and almost neutral shadows;
- soft cinematic — slightly lifted shadows, compressed highlights, mild
  cool-shadow/warm-highlight split tone and a very small vignette.

All three outputs must use the same rendered camera and scene.
