"""Concept cut/fill and route analysis on metre-based data, without GIS dependencies."""
from collections import defaultdict, deque
from math import dist, fsum, hypot

from design_input import keyed, number, position


def positive_volume(area, values):
    """Integrate max(0, delta) over a triangle with linear vertex heights."""
    lo, mid, hi = sorted(values)
    if hi <= 0:
        return 0.0
    signed = area * fsum(values) / 3
    if lo >= 0:
        return signed
    if mid <= 0:
        return area * hi * (hi / (hi - lo)) * (hi / (hi - mid)) / 3
    return max(0.0, signed - area * lo * (lo / (lo - mid)) * (lo / (lo - hi)) / 3)


def earthwork(data):
    """Both elevations use the same XY vertices and triangle indices."""
    nodes = [position(p, 4, "TIN vertex (x,y,original z,design z)") for p in data["vertices"]]
    if len({p[:2] for p in nodes}) != len(nodes):
        raise ValueError("TIN contains duplicate XY vertices; use one index per position")
    cut, fill, area = [], [], []
    seen = set()
    for face in data["triangles"]:
        if (len(face) != 3 or any(type(i) is not int or not 0 <= i < len(nodes) for i in face)
            or len(set(face)) != 3):
            raise ValueError("Invalid TIN triangle vertex indices")
        key = tuple(sorted(face))
        if key in seen:
            raise ValueError("Duplicate TIN triangle")
        seen.add(key)
        a, b, c = (nodes[i] for i in face)
        horizontal = abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])) / 2
        if horizontal <= 0:
            raise ValueError("Degenerate TIN triangle in plan")
        dz = [p[3]-p[2] for p in (a, b, c)]
        cut.append(positive_volume(horizontal, [-z for z in dz]))
        fill.append(positive_volume(horizontal, dz))
        area.append(horizontal)
    if not area:
        raise ValueError("Supply at least one TIN triangle")
    excavation, embankment = fsum(cut), fsum(fill)
    roof = number(data.get("cover_m3_compacted", 0), "cover_m3_compacted", 0)
    sensitivities = {}
    for name, item in keyed(data.get("material_cases", []), "material case").items():
        reuse = number(item["suitable_fraction"], name, 0)
        factor = number(item["compacted_per_bank"], name, 1e-9)
        if reuse > 1:
            raise ValueError(f"{name}: suitable fraction must be in [0, 1]")
        suitable = excavation * reuse
        compacted = suitable * factor
        sensitivities[name] = {
            "suitable_fraction": reuse, "compacted_per_bank": factor,
            "suitable_cut_m3_bank": suitable, "unsuitable_cut_m3_bank": excavation - suitable,
            "available_m3_compacted": compacted,
            "balance_m3_compacted": compacted - (embankment + roof),
            "basis": item.get("basis", "unverified assumption"),
        }
    return {
        "plan_area_m2": fsum(area), "cut_m3_bank": excavation,
        "geometric_fill_m3": embankment, "terrain_fill_need_m3_compacted": embankment,
        "cover_m3_compacted": roof, "total_fill_need_m3_compacted": embankment + roof,
        "material_cases": sensitivities,
        "manual": [
            "Verify TIN faces cover the same domain without partial overlaps and use a common datum",
            "Review survey uncertainty, foundations, stripping, unsuitable soil, groundwater and material assumptions",
        ],
    }


def routes(data):
    tol = number(data["join_tolerance_m"], "join_tolerance_m", 0)
    nodes = {k: position(row["xyz"], 3, k) for k, row in keyed(data["nodes"], "path node").items()}
    reports, issues = {}, []
    graph = defaultdict(set)

    for key, row in keyed(data["routes"], "route").items():
        kind = row.get("kind")
        if kind not in {"walk", "ramp", "stairs", "lift"}:
            raise ValueError(f"{key}: route kind must be walk, ramp, stairs or lift")
        points = row["nodes"]
        if len(points) < 2 or any(p not in nodes for p in points):
            raise ValueError(f"{key}: routes need at least two known nodes")
        direction = row.get("direction", "both")
        if direction not in {"both", "forward"}:
            raise ValueError(f"{key}: direction must be both or forward")
        limit = row.get("max_grade_pct")
        if limit is not None:
            limit = number(limit, f"{key}.max_grade_pct", 0)
        parts = []
        for a, b in zip(points, points[1:]):
            start, end = nodes[a], nodes[b]
            run = hypot(end[0]-start[0], end[1]-start[1])
            rise = end[2]-start[2]
            grade = 100 * rise / run if run > 0 else None
            if (run == 0 and rise == 0) or (run == 0 and kind != "lift") or (kind == "lift" and run > tol):
                issues.append({"id": key, "code": "discontinuity", "edge": [a, b]})
                usable = False
            else:
                usable = True
            if limit is not None and grade is not None and abs(grade) > limit + 1e-9:
                issues.append({"id": key, "code": "grade", "edge": [a, b], "limit_pct": limit})
                usable = False
            if usable:
                graph[a].add(b)
                if direction == "both":
                    graph[b].add(a)
            parts.append({"from": a, "to": b, "start_z_m": start[2], "end_z_m": end[2],
                          "horizontal_m": run, "rise_m": rise, "grade_pct": grade})
        reports[key] = {
            "kind": kind, "segments": parts, "length_m": fsum(dist(nodes[a], nodes[b]) for a, b in zip(points, points[1:])),
            "peak_absolute_grade_pct": max((abs(p["grade_pct"]) for p in parts if p["grade_pct"] is not None), default=None),
        }
    for a, b in data.get("joins", []):
        if a not in nodes or b not in nodes:
            raise ValueError(f"Unknown join node: {a}, {b}")
        gap = dist(nodes[a], nodes[b])
        if gap > tol:
            issues.append({"id": f"{a}/{b}", "code": "join_gap", "gap_m": gap})
        else:
            graph[a].add(b)
            graph[b].add(a)
    for pair in data.get("return_paths", []):
        end, home = pair
        if end not in nodes or home not in nodes:
            raise ValueError(f"Unknown return path node: {end}, {home}")
        visited = {end}
        waiting = deque([end])
        while waiting:
            for next_node in graph[waiting.popleft()] - visited:
                visited.add(next_node)
                waiting.append(next_node)
        if home not in visited:
            issues.append({"id": f"{end}/{home}", "code": "return_missing"})
    return {
        "routes": reports, "issues": issues, "passed": not issues,
        "manual": ["Verify model continuity, widths, crossfall, headroom, landings and accessible/egress route rules"],
    }
