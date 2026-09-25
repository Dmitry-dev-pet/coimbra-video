# Coimbra shot in Google Earth Studio

## Goal

Create one clean source animation first. Do not try to create the tilt-shift effect inside Earth Studio; the repository applies it afterwards.

## Recommended first shot

1. Open Google Earth Studio.
2. Create a new **Custom** project.
3. Search for **Universidade de Coimbra**.
4. Use a 16:9 project.
5. Duration: **10–12 seconds**.
6. Frame rate: **30 fps**.
7. Output: **1920×1080** for the first test. Move to 4K only after the look works.
8. Disable map labels / roads / POIs unless you intentionally want them.
9. Keep the camera oblique, not straight down. The miniature effect reads better when roofs, terrain and the Mondego valley are visible.
10. Use a Camera Target near the University / historic centre and make a slow lateral/orbiting move.
11. Avoid a fast zoom. Motion should be slow enough that the eye can read the city as a miniature.

A useful first composition is:

- University / Alta in the upper-middle area,
- Baixa through the centre,
- Mondego visible across the lower part,
- enough surrounding city to make the scale obvious.

## Render

Earth Studio renders animations as an image sequence. Render at the full project frame range and keep the automatically generated attribution visible.

For the first test:
- 1920×1080
- 30 fps
- High texture quality
- image sequence ZIP
- attribution enabled

The ZIP can be passed directly to:

```bash
python scripts/earth_studio_post.py \
  --input ~/Downloads/earth-studio-render.zip \
  --output output/coimbra_earthstudio_tiltshift.mp4
```

## Attribution

Do not crop, cover or remove Google Earth / imagery-provider attribution.

The post-processing script deliberately restores the lower strip from the original frame so the attribution remains readable even when the lower part of the image is out of focus.
