"""One-time builder for site/assets/ca-counties.json, the outlines on the public Market Map preview.

Source: U.S. Census Bureau cartographic boundary file cb_2023_us_county_20m (KML), public domain.
Keeps California's 58 counties, projects them to flat map coordinates, simplifies the outlines and writes
SVG path data. Rerun only if the outlines need changing:

    python3 -I tools/build_county_shapes.py /path/to/cb_2023_us_county_20m.kml
"""
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"k": "http://www.opengis.net/kml/2.2"}
OUT = Path(__file__).resolve().parent.parent / "site" / "assets" / "ca-counties.json"
LAT0 = 37.25                      # California's middle, for an even east-west scale
SCALE = 100                       # map units per degree of latitude
TOLERANCE = 0.9                   # simplification, in map units (about 1 km)


def project(lon, lat):
    return ((lon + 124.5) * math.cos(math.radians(LAT0)) * SCALE, (42.1 - lat) * SCALE)


def simplify(points, tol):
    """Douglas-Peucker."""
    if len(points) < 4:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        best, idx = 0.0, None
        for i in range(a + 1, b):
            x, y = points[i]
            # A closed ring starts and ends on the same point: measure from that point instead.
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm if norm else math.hypot(x - x1, y - y1)
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, keep) if k]


def main(path):
    root = ET.parse(path).getroot()
    counties = []
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        data = {d.get("name"): d.text for d in pm.iter("{http://www.opengis.net/kml/2.2}SimpleData")}
        if data.get("STATEFP") != "06":
            continue
        rings = []
        for c in pm.iter("{http://www.opengis.net/kml/2.2}coordinates"):
            pts = [project(*map(float, t.split(",")[:2])) for t in c.text.split()]
            pts = simplify(pts, TOLERANCE)
            if len(pts) >= 4:
                rings.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        counties.append({"fips": data["GEOID"], "name": data["NAME"].upper(), "d": "".join(rings)})
    counties.sort(key=lambda c: c["fips"])
    assert len(counties) == 58, len(counties)
    xs = [float(v) for c in counties for v in re.findall(r"[ML]([\d.]+),", c["d"])]
    ys = [float(v) for c in counties for v in re.findall(r",([\d.]+)", c["d"])]
    box = [math.floor(min(xs)) - 2, math.floor(min(ys)) - 2, math.ceil(max(xs) - min(xs)) + 4, math.ceil(max(ys) - min(ys)) + 4]
    OUT.write_text(json.dumps({"source": "U.S. Census Bureau, cartographic boundary file cb_2023_us_county_20m (public domain)",
                               "viewBox": box, "counties": counties}, separators=(",", ":")))
    print(f"{len(counties)} counties, {OUT.stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
