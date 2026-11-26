"""Polygon-based concept geometry and layout checks. Install Shapely only for this module."""
from collections import defaultdict, deque
from itertools import combinations
import math

from shapely import constrained_delaunay_triangles, is_valid_reason, union_all
from shapely.errors import GEOSException
from shapely.geometry import LineString, Point, shape, mapping
from shapely.geometry.polygon import orient

from design_input import keyed, number, position


def polygon(value, label):
    if not isinstance(value, dict) or value.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"{label}: expected a GeoJSON Polygon or MultiPolygon")
    raw = value.get("coordinates")
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(f"{label}: missing coordinate rings")
    for component in raw if value["type"] == "MultiPolygon" else [raw]:
        if not isinstance(component, (list, tuple)) or not component:
            raise ValueError(f"{label}: polygon has no rings")
        for ring in component:
            if not isinstance(ring, (list, tuple)) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError(f"{label}: each polygon ring requires at least four coordinates and must close")
            for point in ring:
                position(point, 2, label)
    try:
        geom = shape(value)
    except (GEOSException, ValueError, TypeError) as exc:
        raise ValueError(f"{label}: malformed polygon: {exc}") from exc
    if geom.is_empty or geom.area <= 0 or not geom.is_valid:
        raise ValueError(f"{label}: nonpositive or invalid polygon ({is_valid_reason(geom)})")
    return geom


def parts(geom):
    if geom.geom_type == "Polygon" and not geom.is_empty:
        yield geom
    elif hasattr(geom, "geoms"):
        for component in geom.geoms:
            yield from parts(component)


def read_shell(data):
    """Resolve the buildable domain and usable plates without reading any rooms."""
    if data.get("schema") != 1 or data.get("units") != "m":
        raise ValueError("Expected schema 1 and project-local metre coordinates (units: m)")
    site = polygon(data["site"], "site") if "site" in data else None
    buildable = polygon(data["buildable"], "buildable") if "buildable" in data else site
    if site is not None and not site.covers(buildable):
        raise ValueError("buildable polygon extends outside the site")
    raw_levels = keyed(data["levels"], "level")
    if not raw_levels:
        raise ValueError("Provide at least one level plate")
    cuts = defaultdict(list)
    for name, cut in keyed(data.get("voids", []), "void").items():
        footprint = polygon(cut["polygon"], name)
        if not cut["levels"] or any(level not in raw_levels for level in cut["levels"]):
            raise ValueError(f"Void {name}: specify affected level ids")
        for level in cut["levels"]:
            cuts[level].append(footprint)
    levels = {}
    for key, level in raw_levels.items():
        plate = polygon(level["polygon"], key)
        if buildable is not None and not buildable.covers(plate):
            raise ValueError(f"{key}: level plate extends outside the buildable domain")
        if any(not plate.intersects(cut) or plate.intersection(cut).area == 0 for cut in cuts[key]):
            raise ValueError(f"{key}: one or more declared voids do not cut the plate")
        floor = plate.difference(union_all(cuts[key]))
        if floor.is_empty or floor.area <= 0:
            raise ValueError(f"{key}: cuts remove the complete plate")
        if level.get("location") not in {"above", "below"}:
            raise ValueError(f"{key}: declare area accounting location as above or below")
        levels[key] = (floor, number(level["z_m"], f"{key}.z_m"), level["location"])
    return levels


def adapt_candidate(candidate, plate, assigned=()):
    """Return the allowable portion and area lost. Keep the original available for review."""
    available = candidate.intersection(plate).difference(union_all(list(assigned)))
    return available, candidate.area - available.area


def mesh_prism(footprint, z, thickness, plane=(0, 0, 0)):
    """Create a closed, triangulated slab or facet. Plane is dz/dx, dz/dy, offset."""
    dx, dy, offset = plane
    elements = []
    for piece in parts(footprint):
        vertices, faces, keys = [], [], {}

        def vertex(point, top):
            x, y = point[:2]
            key = x, y, top
            if key not in keys:
                keys[key] = len(vertices)
                vertices.append([x, y, z + dx*x + dy*y + offset - (0 if top else thickness)])
            return keys[key]

        piece = orient(piece, sign=1)
        for tri in constrained_delaunay_triangles(piece).geoms:
            ring = list(orient(tri, sign=1).exterior.coords)[:-1]
            faces.append([vertex(p, True) for p in ring])
            faces.append([vertex(p, False) for p in reversed(ring)])
        for boundary in (piece.exterior, *piece.interiors):
            ring = list(boundary.coords)
            for a, b in zip(ring, ring[1:]):
                faces.append([vertex(a, False), vertex(b, False), vertex(b, True), vertex(a, True)])
        elements.append({"vertices_m": vertices, "faces": faces})
    return elements


def shell_output(data):
    levels = read_shell(data)
    meshes = {}
    for level in data["levels"]:
        key = level["id"]
        if "thickness_m" in level:
            thickness = number(level["thickness_m"], key, 0)
            if thickness == 0:
                raise ValueError(f"{key}: slab thickness must be positive")
            meshes[f"level/{key}"] = mesh_prism(levels[key][0], levels[key][1], thickness)
    for body in keyed(data.get("masses", []), "mass").values():
        key = body["id"]
        bottom, top = position(body["z_range_m"], 2, f"{key}.z_range_m")
        if top <= bottom:
            raise ValueError(f"{key}: top of mass must be above its base")
        outline = polygon(body["polygon"], key)
        cuts = [polygon(cut, f"{key}.cut") for cut in body.get("cuts", [])]
        footprint = outline.difference(union_all(cuts))
        if not footprint.area > 0:
            raise ValueError(f"{key}: no mass remains after cuts")
        meshes[f"mass/{key}"] = mesh_prism(footprint, top, top - bottom)
    for roof in keyed(data.get("roofs", []), "roof").values():
        key = roof["id"]
        thickness = number(roof["thickness_m"], key, 0)
        if thickness == 0:
            raise ValueError(f"{key}: roof thickness must be positive")
        plane = position(roof["plane"], 3, f"{key}.plane")
        footprint = polygon(roof["polygon"], key)
        cuts = [polygon(cut, f"{key}.cut") for cut in roof.get("cuts", [])]
        if any(not footprint.intersection(cut).area > 0 for cut in cuts):
            raise ValueError(f"{key}: roof cut misses its facet")
        remaining = footprint.difference(union_all(cuts))
        if remaining.area <= 0:
            raise ValueError(f"{key}: cuts remove the roof facet")
        meshes[f"roof/{key}"] = mesh_prism(remaining, 0, thickness, plane)
    return {
        "units": "m",
        "levels": {k: {"polygon": mapping(p), "gross_m2": p.area, "z_m": z, "location": zone}
                   for k, (p, z, zone) in levels.items()},
        "meshes": meshes,
    }


def area_limits(value, limits, label, issue, tolerance=0):
    names = ("min", "target", "max")
    finite = {k: number(limits[k], f"{label}.{k}", 0) for k in names if k in limits}
    sequence = [finite[k] for k in names if k in finite]
    if sequence != sorted(sequence):
        raise ValueError(f"{label}: require min <= target <= max")
    if value < finite.get("min", -math.inf) - tolerance or value > finite.get("max", math.inf) + tolerance:
        issue("budget", label, f"{value:.3f} m² outside {finite}")
    target = finite.get("target")
    if "deviation" in limits:
        delta = number(limits["deviation"], f"{label}.deviation", 0)
        if target is None:
            raise ValueError(f"{label}: deviation requires a target")
        if abs(value - target) > delta + tolerance:
            issue("target_deviation", label, f"{value:.3f} m² differs from target {target} by more than {delta}")
    return None if target is None else value - target


def room_size(key, net, requirement, issue, length_tol):
    width = number(requirement.get("min_width_m", 0), key, 0)
    depth = number(requirement.get("min_depth_m", 0), key, 0)
    if not width and not depth:
        return
    outline = net.minimum_rotated_rectangle
    points = list(outline.exterior.coords)
    short, long = sorted(math.dist(points[j], points[j+1]) for j in range(2))
    if short + length_tol < width or long + length_tol < depth:
        issue("size", key, f"Oriented bounding extents {short:.3f} x {long:.3f} m")
    if width > 0:
        usable_core = net.buffer(-max(0, (width - length_tol)/2))
        if usable_core.is_empty:
            issue("narrow", key, f"No continuous interior can contain the width probe of {width:g} m")
        elif usable_core.geom_type == "MultiPolygon":
            issue("width_bottleneck", key, f"The width probe of {width:g} m divides the usable interior")


def openings(data, rooms, levels, length_tol, issue, manual):
    graph = defaultdict(set)
    roots = set()
    for name, connection in keyed(data.get("connections", []), "connection").items():
        a, b = connection["from"], connection.get("to")
        if a not in rooms or (b is not None and b not in rooms) or a == b:
            issue("connection_reference", name, "Unknown, invalid, or identical room endpoints")
            continue
        ra, pa, _ = rooms[a]
        la = ra["level"]
        mode = connection["kind"]
        if mode in {"door", "entry"}:
            if (mode == "entry") != (b is None) or (b is not None and rooms[b][0]["level"] != la):
                issue("door_level", name, "Use entry for exterior access and door for same-level room pairs")
                continue
            points = [position(p, 2, name) for p in connection["segment"]]
            if len(points) != 2:
                raise ValueError(f"{name}: door segment requires two points")
            gap = LineString(points)
            width = number(connection.get("min_width_m", 0), name, 0)
            shared = (levels[la][0].boundary if b is None else rooms[b][1].boundary)
            if (gap.length == 0 or gap.length + length_tol < width
                or not pa.boundary.buffer(length_tol).covers(gap)
                or not shared.buffer(length_tol).covers(gap)):
                issue("door_opening", name, "Door segment is undersized or does not lie within both boundaries")
                continue
        elif mode == "vertical":
            if b is None:
                issue("vertical_connection", name, "A vertical connection requires two room endpoints")
                continue
            rb, pb, _ = rooms[b]
            lb = rb["level"]
            x, y, za = position(connection["from_xyz"], 3, name)
            X, Y, zb = position(connection["to_xyz"], 3, name)
            source_z = ra.get("z_m", levels[la][1])
            target_z = rb.get("z_m", levels[lb][1])
            if (
                la == lb or abs(za-zb) <= length_tol
                or abs(source_z-za) > length_tol or abs(target_z-zb) > length_tol
                or not pa.buffer(length_tol).covers(Point(x, y))
                or not pb.buffer(length_tol).covers(Point(X, Y))
                or (connection.get("aligned", False) and math.dist((x, y), (X, Y)) > length_tol)
            ):
                issue("vertical_connection", name, "The landings, floor elevations or required XY alignment disagree")
                continue
            manual.append(f"{name}: verify continuous steps/shaft, headroom and openings in model section")
        else:
            raise ValueError(f"{name}: connection kind must be door, entry or vertical")
        if b is None:
            roots.add(a)
        else:
            graph[a].add(b)
            graph[b].add(a)
    for a, (room, _, _) in rooms.items():
        for b in room.get("adjacent", []):
            if (b not in rooms or room["level"] != rooms[b][0]["level"]
                or rooms[a][1].boundary.intersection(rooms[b][1].boundary).length <= length_tol):
                issue("adjacency", a, f"No shared boundary with {b}")
        for b in room.get("connected", []):
            if b not in graph[a]:
                issue("required_opening", a, f"No verified connection to {b}")
    if data.get("check_reachability", False):
        pending = deque(roots)
        while pending:
            for neighbor in graph[pending.popleft()] - roots:
                roots.add(neighbor)
                pending.append(neighbor)
        for key in rooms.keys() - roots:
            issue("unreachable", key, "No path from a declared exterior entry")


def evaluate(data, mode):
    """Evaluate drawn room polygons against independently resolved floor plates."""
    if mode not in {"explore", "accept"}:
        raise ValueError("Mode must be explore or accept")
    levels = read_shell(data)
    tol = data.get("tolerances", {})
    area_tol = number(tol["area_m2"], "tolerances.area_m2", 0)
    length_tol = number(tol["length_m"], "tolerances.length_m", 1e-9)
    issues, rooms, door_manual = [], {}, []
    metric = defaultdict(float, {"gross/above": 0.0, "gross/below": 0.0})
    report = {"rooms": {}, "levels": {}, "checks": {},
              "mode": mode, "issues": issues, "manual": door_manual}

    def issue(name, subject, message):
        severity = "error" if mode == "accept" or name in {"invalid_geometry", "invalid_reference"} else "warning"
        issues.append({"code": name, "id": subject, "severity": severity, "message": message})

    program = keyed(data.get("room_requirements", []), "room requirement")
    drawings = keyed(data.get("rooms", []), "room")
    outdoor = keyed(data.get("outdoor_areas", []), "outdoor area")
    categories = data.get("categories", [])
    if not isinstance(categories, list) or not all(isinstance(c, str) and c.strip() for c in categories):
        raise ValueError("categories must be a list of nonempty accounting labels")
    declared = set(categories)
    allowed_metrics = {"gross", "gross/above", "gross/below", "net_total", "outline_total",
                       "estimated_room_enclosure", "outdoor_total"}
    for room in (*program.values(), *drawings.values()):
        label = room.get("category")
        if isinstance(label, str) and label.strip():
            declared.add(label)
    for category in declared:
        allowed_metrics.update({f"net/{category}", f"outline/{category}"})
    allowed_metrics.update(f"outdoor/{name}" for name in outdoor)
    for key, requirement in program.items():
        if requirement.get("required", True) and key not in drawings:
            issue("missing_room", key, "Required program room has no drawn footprint")
    for key, room in drawings.items():
        requirement = program.get(key, {})
        budget = dict(requirement.get("budget", {}))
        for setting, value in room.get("budget", {}).items():
            if setting in budget and value != budget[setting]:
                raise ValueError(f"{key}: inline budget conflicts with room requirements for {setting}")
            budget[setting] = value
        for field in ("category", "level", "adjacent", "connected"):
            if field not in requirement:
                continue
            if field in room and room[field] != requirement[field]:
                raise ValueError(f"{key}: drawn room conflicts with room requirements for {field}")
            room = {**room, field: requirement[field]}
        access = room.get("z_m")
        if access is not None:
            number(access, key)
        level = room["level"]
        if level not in levels:
            issue("invalid_reference", key, f"Unknown level {level}")
            continue
        try:
            footprint = polygon(room["polygon"], key)
            if ("net_polygon" in room) == ("net_inset_m" in room):
                raise ValueError(f"{key}: choose exactly one net method, net_polygon or net_inset_m")
            definition = "supplied_polygon" if "net_polygon" in room else "uniform_inward_offset"
            net = (polygon(room["net_polygon"], f"{key}.net_polygon") if "net_polygon" in room else
                   footprint.buffer(-number(room["net_inset_m"], f"{key}.net_inset_m", 0), join_style="mitre"))
            if net.difference(footprint).area > area_tol or net.area <= 0 or not net.is_valid:
                raise ValueError(f"{key}: net footprint must be valid, positive and inside room")
        except ValueError as exc:
            issue("invalid_geometry", key, str(exc))
            continue
        if not isinstance(room.get("category"), str) or not room["category"].strip():
            raise ValueError(f"{key}: supply an accounting category")
        goal_delta = area_limits(net.area, budget, key, issue, area_tol)
        if net.geom_type == "MultiPolygon":
            issue("disconnected_room", key, "Net footprint has multiple disconnected parts")
        if "candidate_polygon" in room:
            before = polygon(room["candidate_polygon"], f"{key}.candidate_polygon")
            lost = before.difference(footprint).area
            if lost > area_tol:
                door_manual.append(f"{key}: {lost:.3f} m² removed from the candidate footprint; verify useful area")
            if "max_loss_m2" in budget and lost > number(budget["max_loss_m2"], key, 0) + area_tol:
                issue("clipped_room", key, f"{lost:.3f} m² of candidate exceeds permitted loss")
        room_size(key, net, budget, issue, length_tol)
        partition = room["category"]
        rooms[key] = room, footprint, net
        metric[f"net/{partition}"] += net.area
        metric[f"outline/{partition}"] += footprint.area
        report["rooms"][key] = {"level": level, "category": partition, "net_m2": net.area,
                                "outline_m2": footprint.area, "net_method": definition,
                                "priority": budget.get("priority"), "delta_to_net_target_m2": goal_delta}

    for key, (plate, _, zone) in levels.items():
        entries = {k: v for k, (r, v, _) in rooms.items() if r["level"] == key}
        for room_id, footprint in entries.items():
            outside = footprint.difference(plate).area
            if outside > area_tol:
                if footprint.difference(plate.buffer(length_tol)).area > area_tol:
                    issue("outside_plate", room_id, f"{outside:.4f} m² extends beyond the plate boundary")
                else:
                    door_manual.append(f"{room_id}: {outside:.4f} m² crosses the exact plate edge within declared length tolerance")
        for (a, pa), (b, pb) in combinations(entries.items(), 2):
            if pa.intersection(pb).area > area_tol:
                issue("overlap", f"{a}/{b}", "Room footprints overlap")
        occupied = union_all(list(entries.values()))
        explanations = []
        for patch in data.get("explained_areas", []):
            if patch["level"] != key:
                continue
            if not isinstance(patch.get("reason"), str) or not patch["reason"].strip():
                raise ValueError(f"{key}: explained area requires a written reason")
            poly = polygon(patch["polygon"], f"{key}.explained_area")
            if poly.difference(plate).area > area_tol or poly.intersection(occupied).area > area_tol:
                issue("explained_area_overlap", key, "Explained area overlaps rooms or extends beyond its plate")
            if any(poly.intersection(other).area > area_tol for other in explanations):
                issue("explained_area_overlap", key, "Explained areas overlap")
            explanations.append(poly)
            category = patch.get("category", "other")
            if not isinstance(category, str) or not category.strip():
                raise ValueError(f"{key}: explained area category must be a nonempty string")
            label = f"explained/{category}"
            allowed_metrics.add(label)
            metric[label] += poly.intersection(plate).area
        uncovered = plate.difference(occupied.union(union_all(explanations)))
        max_gap = data.get("max_unexplained_m2")
        if max_gap is not None and uncovered.area > number(max_gap, "max_unexplained_m2", 0) + area_tol:
            issue("unexplained_area", key, f"{uncovered.area:.3f} m² not allocated or explained")
        elif max_gap is None and uncovered.area > area_tol:
            door_manual.append(f"{key}: review {uncovered.area:.3f} m² unallocated plate area")
        metric["gross"] += plate.area
        metric[f"gross/{zone}"] += plate.area
        report["levels"][key] = {
            "gross_m2": plate.area, "occupied_outline_m2": occupied.intersection(plate).area,
            "explained_m2": union_all(explanations).intersection(plate).area,
            "unexplained_m2": uncovered.area, "unexplained_geometry": mapping(uncovered),
        }
    if any(p["level"] not in levels for p in data.get("explained_areas", [])):
        raise ValueError("Explained area refers to an unknown level")
    metric["net_total"] = sum(v[2].area for v in rooms.values())
    metric["outline_total"] = sum(v[1].area for v in rooms.values())
    metric["estimated_room_enclosure"] = metric["outline_total"] - metric["net_total"]
    open_polys = {}
    site = polygon(data["site"], "site") if outdoor and "site" in data else None
    for name, patch in outdoor.items():
        poly = polygon(patch["polygon"], name)
        if site is not None and poly.difference(site).area > area_tol:
            issue("outdoor_boundary", name, "Outdoor area lies outside the declared site")
        for other, previous in open_polys.items():
            if poly.intersection(previous).area > area_tol:
                issue("outdoor_overlap", f"{name}/{other}", "Outdoor area partitions overlap")
        open_polys[name] = poly
        metric[f"outdoor/{name}"] = poly.area
    metric["outdoor_total"] = union_all(list(open_polys.values())).area
    for key, limits in data.get("area_limits_m2", {}).items():
        if key not in allowed_metrics:
            raise ValueError(f"Unknown area metric {key}; declare the corresponding category or area")
        report["checks"][key] = {
            "measured_m2": metric[key],
            "delta_to_target_m2": area_limits(metric[key], limits, key, issue, area_tol),
        }
    if data.get("connections") or data.get("check_reachability") or any(
        room.get("adjacent") or room.get("connected") for room, _, _ in rooms.values()
    ):
        openings(data, rooms, levels, length_tol, issue, door_manual)
    else:
        door_manual.append("Door and route geometry was not requested for this layout")
    report["area_m2"] = dict(metric)
    report["manual"].append("Review useful clear dimensions, structure, operation, egress and applicable requirements")
    report["declared_checks_clear"] = not issues
    report["passed"] = not any(item["severity"] == "error" for item in issues)
    return report
