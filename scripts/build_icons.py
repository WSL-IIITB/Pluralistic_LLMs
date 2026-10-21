"""Draw the favicon set from the six Karnataka region polygons (public/geo/karnataka-regions.geojson).

Writes public/favicon.svg, favicon.ico, favicon-32.png and apple-touch-icon.png.
Run: python3 scripts/build_icons.py
"""
import json, math
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
BG = (13, 14, 18)
geo = json.loads((PUB / "geo/karnataka-regions.geojson").read_text())

rings = []  # (color, [(lon, lat), ...]) -- Polygon/MultiPolygon outer rings
for f in geo["features"]:
    g = f["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for p in polys:
        rings.append((tuple(f["properties"]["color"]), p[0]))

lons = [x for _, r in rings for x, _ in r]
lats = [y for _, r in rings for _, y in r]
x0, x1, y0, y1 = min(lons), max(lons), min(lats), max(lats)
kx = math.cos(math.radians((y0 + y1) / 2))  # flatten longitude so the shape isn't stretched


def project(size, pad):
    scale = (size - 2 * pad) / max((x1 - x0) * kx, y1 - y0)
    ox = (size - (x1 - x0) * kx * scale) / 2
    oy = (size - (y1 - y0) * scale) / 2
    return lambda x, y: (ox + (x - x0) * kx * scale, oy + (y1 - y) * scale)


def raster(size):
    big = size * 4
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * 0.22), fill=BG + (255,))
    pt = project(big, big * 0.12)
    for color, ring in rings:
        d.polygon([pt(x, y) for x, y in ring], fill=color + (255,), outline=BG + (255,), width=max(2, big // 90))
    return img.resize((size, size), Image.LANCZOS)


def svg(size=64):
    pt = project(size, size * 0.12)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">',
             f'<rect width="{size}" height="{size}" rx="{size * 0.22:.1f}" fill="rgb{BG}"/>']
    for color, ring in rings:
        pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in (pt(x, y) for x, y in ring))
        parts.append(f'<polygon points="{pts}" fill="rgb{color}" stroke="rgb{BG}" stroke-width="0.7" stroke-linejoin="round"/>')
    parts.append("</svg>")
    return "".join(parts)


(PUB / "favicon.svg").write_text(svg())
raster(180).save(PUB / "apple-touch-icon.png")
raster(32).save(PUB / "favicon-32.png")
raster(64).save(PUB / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
print("icons written")
