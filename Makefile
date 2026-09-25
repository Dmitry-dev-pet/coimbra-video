PY=.venv/bin/python

.PHONY: ortho mds prepare mesh render tiltshift

ortho:
	$(PY) scripts/fetch_ortho.py

mds:
	$(PY) scripts/fetch_mds.py

prepare:
	$(PY) scripts/prepare_mds.py

mesh:
	$(PY) scripts/build_mesh.py --mesh-resolution 2.0

render:
	blender -b -P blender/render_scene.py

tiltshift:
	$(PY) scripts/tiltshift.py
