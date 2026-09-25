from pyproj import Transformer
from common import load_config

cfg = load_config()
b = cfg["bbox_wgs84"]
t = Transformer.from_crs(4326, 3763, always_xy=True)
print("WGS84:", b)
print("SW in EPSG:3763:", t.transform(b[0], b[1]))
print("NE in EPSG:3763:", t.transform(b[2], b[3]))
print("Expected EPSG:3763:", cfg["bbox_epsg3763"])
