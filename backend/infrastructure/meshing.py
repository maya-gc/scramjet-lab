"""Parametric mesh generation with Gmsh (Python SDK), 2D and 3D.

2D (``case.dimension = 2``)
---------------------------
- Unstructured Delaunay/Frontal mesh with an anisotropic, boundary-layer
  "BoundaryLayer" mesh field at no-slip walls (body, cowl, strut) to hit
  y+ ~ 1 for k-omega SST, plus box sizing fields over the inlet, isolator
  (shock train), combustor/strut wake and nozzle.
- Exported as a SU2 ASCII ``NDIME= 2`` mesh (TRIANGLE/QUAD volume, LINE
  markers).

3D (``case.dimension = 3``, requires ``geometry.span``)
-------------------------------------------------------
- The 2D channel profile (including the strut hole) is swept along the
  ``z`` axis by ``span`` with Gmsh OCC ``extrude``, producing a single
  extruded-solid volume. Each lateral surface is classified by geometry
  (z-plane caps become the "side" slip markers; the swept loop edges
  become inflow/outflow/cowl/body/strut).
- BoundaryLayer is applied on the wall *surfaces*; box sizes extend through
  the span.
- Exported as a SU2 ASCII ``NDIME= 3`` mesh (TETRAHEDRON/PRISM/PYRAMID/
  HEXAHEDRON volume, TRIANGLE/QUAD markers). Marker faces are re-oriented
  outward relative to the adjacent volume cell so SU2 boundary markers see
  the correct geometric normal.

Both formats use VTK element codes and 0-based node ids exactly as the
SU2 v8.x reader expects for ASCII meshes (point arrays are indexed with
the file node id, sized ``[0, NPOIN-1]``).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import gmsh

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.domain.config import load_case
from backend.domain.geometry import build_geometry, summary

_GMSH_TO_SU2_2D = {1: 3, 2: 5, 3: 9}     # line -> LINE, triangle, quad
_GMSH_TO_SU2_3D = {4: 10, 6: 13, 7: 14, 5: 12}  # tet, prism, pyramid, hexa
_SU2_3D_NPOINTS = {10: 4, 13: 6, 14: 5, 12: 8}
_GMSH_TO_SU2_FACE = {2: 5, 3: 9}         # triangle -> TRIANGLE, quad -> QUAD
_SU2_FACE_NPOINTS = {5: 3, 9: 4}


def _configure(verbose: bool, mp) -> None:
    g = gmsh.option.setNumber
    g("General.Terminal", 1 if verbose else 0)
    g("General.Verbosity", 3 if verbose else 1)
    g("Mesh.SaveAll", 0)
    g("Mesh.Binary", 0)
    g("Mesh.ElementOrder", 1)
    g("Mesh.Algorithm", 2)          # Delaunay: most robust with size fields
    g("Mesh.MeshSizeMin", mp.h_wall_n)
    g("Mesh.MeshSizeMax", mp.h_far * 1.5 * mp.size_scale)
    g("Mesh.MeshSizeFromPoints", 0)
    g("Mesh.MeshSizeFromCurvature", 0)
    g("Mesh.MeshSizeExtendFromBoundary", 0)
    g("Mesh.Optimize", 0)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)  # Gmsh 2.2 ASCII for SU2


# ---------------------------------------------------------------------------
# 2D CAD + fields (unchanged behaviour)
# ---------------------------------------------------------------------------
def _build_cad_2d(geo: dict, gp) -> dict:
    """Create the 2D occ CAD: outer channel loop + strut hole + physical groups."""
    model = gmsh.model
    occ = model.occ
    lower, upper = geo["lower"], geo["upper"]
    strut = geo["strut"]

    def add_point(p, lc=0.0):
        return occ.addPoint(p[0], p[1], 0.0, lc)

    p_in0 = add_point(lower[0])          # (0, 0) ramp leading edge
    p_in1 = add_point(upper[0])          # (0, H) cowl lip
    p_out0 = add_point(upper[1])         # (x_total, H)
    p_out1 = add_point(lower[-1])        # (x_total, y_exit)

    inflow = occ.addLine(p_in0, p_in1)
    cowl = occ.addLine(p_in1, p_out0)
    outflow = occ.addLine(p_out0, p_out1)

    body_pts = [add_point(p) for p in lower]
    body_lines = [occ.addLine(body_pts[i], body_pts[i + 1]) for i in range(len(lower) - 1)]

    outer_loop = occ.addCurveLoop([inflow, cowl, outflow] + list(reversed(body_lines)))

    strut_lines: list[int] = []
    strut_loop = None
    if strut is not None:
        sp = [add_point(p) for p in strut]
        strut_lines = [occ.addLine(sp[i], sp[(i + 1) % len(sp)]) for i in range(len(sp))]
        strut_loop = occ.addCurveLoop(strut_lines)

    loops = [outer_loop] + ([strut_loop] if strut_loop is not None else [])
    surface = occ.addPlaneSurface(loops)
    occ.synchronize()

    model.addPhysicalGroup(1, [inflow], name="inflow")
    model.addPhysicalGroup(1, [outflow], name="outflow")
    model.addPhysicalGroup(1, [cowl], name="cowl")
    model.addPhysicalGroup(1, body_lines, name="body")
    if strut_lines:
        model.addPhysicalGroup(1, strut_lines, name="strut")
    model.addPhysicalGroup(2, [surface], name="fluid")

    return {
        "inflow": [inflow],
        "outflow": [outflow],
        "cowl": [cowl],
        "body": body_lines,
        "strut": strut_lines,
        "wall_edges": body_lines + [cowl] + strut_lines,
        "surface": surface,
        "wall_surfaces": [],
    }


def _apply_fields_2d(geo: dict, tags: dict, mp) -> None:
    d = geo["derived"]
    x_ie = d["x_inlet_end"]
    x_so = d["x_isolator_end"]
    x_co = d["x_combustor_end"]
    x_tot = d["x_total"]
    H = d["H_capture"]
    ymin, ymax = -0.01, H + 0.01

    field = gmsh.model.mesh.field

    # -- 2D boundary layer at no-slip walls (gmsh 4.15 API) ----------------
    # The strut is a sharp closed diamond; the two BL fronts meeting head-on at
    # its leading/trailing tips make gmsh emit degenerate "sliver" triangles
    # that can slowly destabilise the SU2 solver, so the strut never receives
    # a prism layer. body/cowl (single curve chains) are safe.
    if mp.bl_thickness > 0.0:
        bl_edges = tags["body"] + tags["cowl"]
        bl = field.add("BoundaryLayer")
        field.setNumbers(bl, "CurvesList", bl_edges)
        field.setNumber(bl, "Size", mp.h_wall_n)       # first-layer height (y+ ~ 1)
        field.setNumber(bl, "SizeFar", mp.h_far * mp.size_scale)
        field.setNumber(bl, "Thickness", mp.bl_thickness * mp.size_scale)
        field.setNumber(bl, "Ratio", mp.bl_ratio)
        field.setAsBoundaryLayer(bl)

    # -- box sizing: VIn inside the box, VOut outside -----------------------
    boxes: list[int] = []
    for x0, x1, h in (
        (0.0, x_ie + 0.10, mp.h_inlet),
        (x_ie - 0.05, x_so + 0.05, mp.h_isolator),
        (x_so - 0.05, x_co + 0.05, mp.h_combustor),
        (x_co - 0.05, x_tot + 0.05, mp.h_nozzle),
    ):
        b = field.add("Box")
        field.setNumber(b, "VIn", h * mp.size_scale)
        field.setNumber(b, "VOut", mp.h_far * mp.size_scale)
        field.setNumber(b, "Thickness", 0.0)
        field.setNumber(b, "XMin", x0)
        field.setNumber(b, "XMax", x1)
        field.setNumber(b, "YMin", ymin)
        field.setNumber(b, "YMax", ymax)
        boxes.append(b)

    back = field.add("Min")
    field.setNumbers(back, "FieldsList", boxes)
    field.setAsBackgroundMesh(back)


# ---------------------------------------------------------------------------
# 3D CAD + fields (extruded solid)
# ---------------------------------------------------------------------------
def _build_cad_3d(geo: dict, gp) -> dict:
    """Sweep the 2D channel profile (with strut hole) along +z by ``span``.

    The end caps (constant z) become the "side" slip markers; every swept
    loop edge is classified by its (x, y) position against the 2D polylines.
    """
    model = gmsh.model
    occ = model.occ
    lower, upper = geo["lower"], geo["upper"]
    strut = geo["strut"]
    B = gp.span

    def add_point(p, lc=0.0):
        return occ.addPoint(p[0], p[1], 0.0, lc)

    p_in0 = add_point(lower[0])
    p_in1 = add_point(upper[0])
    p_out0 = add_point(upper[1])
    p_out1 = add_point(lower[-1])

    inflow = occ.addLine(p_in0, p_in1)
    cowl = occ.addLine(p_in1, p_out0)
    outflow = occ.addLine(p_out0, p_out1)

    body_pts = [add_point(p) for p in lower]
    body_lines = [occ.addLine(body_pts[i], body_pts[i + 1]) for i in range(len(lower) - 1)]

    outer_loop = occ.addCurveLoop([inflow, cowl, outflow] + list(reversed(body_lines)))

    strut_lines: list[int] = []
    strut_loop = None
    if strut is not None:
        sp = [add_point(p) for p in strut]
        strut_lines = [occ.addLine(sp[i], sp[(i + 1) % len(sp)]) for i in range(len(sp))]
        strut_loop = occ.addCurveLoop(strut_lines)

    loops = [outer_loop] + ([strut_loop] if strut_loop is not None else [])
    surf = occ.addPlaneSurface(loops)
    occ.synchronize()

    extruded = occ.extrude([(2, surf)], 0.0, 0.0, B)
    vol_tags = [e[1] for e in extruded if e[0] == 3]
    if len(vol_tags) != 1:
        raise RuntimeError(f"expected a single extruded volume, got {vol_tags}")
    vol_tag = vol_tags[0]
    occ.synchronize()

    # ---- classify every surface by geometry ------------------------------
    H = gp.capture_height
    H_exit = geo["derived"]["H_nozzle_exit"]
    y_exit = H - H_exit
    x_tot = geo["derived"]["x_total"]
    polylines: dict[str, list] = {
        "inflow": [(0.0, 0.0), (0.0, H)],
        "outflow": [(x_tot, y_exit), (x_tot, H)],
        "cowl": [(0.0, H), (x_tot, H)],
        "body": geo["lower"],
    }
    if strut is not None:
        polylines["strut"] = strut

    marker_tags: dict[str, list[int]] = {k: [] for k in polylines}
    side_tags: list[int] = []
    tol = 1e-6
    tol_z = B * 1e-4 + 1e-9
    for (dim, tag) in occ.getEntities(2):
        # centroid via boundary corners (getBoundingBox can fail on freshly
        # extruded faces; boundary/vertex traversal is always valid)
        verts: list[list[float]] = []
        for (ldim, ltag) in gmsh.model.getBoundary([(dim, tag)], recursive=False):
            for (pdim, ptag) in gmsh.model.getBoundary([(ldim, ltag)], recursive=False):
                verts.append(list(gmsh.model.getValue(0, ptag, [])))
        if not verts:
            continue
        cx = sum(v[0] for v in verts) / len(verts)
        cy = sum(v[1] for v in verts) / len(verts)
        cz = sum(v[2] for v in verts) / len(verts)
        if abs(cz - 0.0) < tol_z or abs(cz - B) < tol_z:
            side_tags.append(tag)
            continue
        best_name, best_d = None, float("inf")
        for name, poly in polylines.items():
            pts = poly if isinstance(poly[0], tuple) else poly
            for i in range(len(pts) - 1):
                (ax, ay), (bx, by) = pts[i], pts[i + 1]
                dx, dy = bx - ax, by - ay
                l2 = dx * dx + dy * dy
                t = min(max(((cx - ax) * dx + (cy - ay) * dy) / max(l2, 1e-30), 0.0), 1.0)
                d2 = (cx - (ax + t * dx)) ** 2 + (cy - (ay + t * dy)) ** 2
                if d2 < best_d:
                    best_d, best_name = d2, name
        marker_tags[best_name].append(tag)

    for name, tags in marker_tags.items():
        if tags:
            gmsh.model.addPhysicalGroup(2, tags, name=name)
    if side_tags:
        gmsh.model.addPhysicalGroup(2, side_tags, name="side")
    gmsh.model.addPhysicalGroup(3, [vol_tag], name="fluid")
    occ.synchronize()

    wall_surfaces = marker_tags["body"] + marker_tags["cowl"] + marker_tags["strut"]
    return {
        "volume": vol_tag,
        "wall_edges": [],
        "wall_surfaces": wall_surfaces,
        "marker_surfaces": {**marker_tags, "side": side_tags},
    }


def _apply_fields_3d(geo: dict, tags: dict, mp) -> None:
    """3D size fields (isotropic box sizing).

    Gmsh 4.15's ``BoundaryLayer`` field is 2D-only (``SurfacesList`` was
    removed), so the 3D path gets an isotropic mesh; near-wall y+ must be
    refined by reducing the box sizes / ``h_wall_n`` floor if required.
    """
    d = geo["derived"]
    x_ie = d["x_inlet_end"]
    x_so = d["x_isolator_end"]
    x_co = d["x_combustor_end"]
    x_tot = d["x_total"]
    H = d["H_capture"]
    B = d["B"]
    ymin, ymax = -0.01, H + 0.01

    field = gmsh.model.mesh.field

    boxes: list[int] = []
    for x0, x1, h in (
        (0.0, x_ie + 0.10, mp.h_inlet),
        (x_ie - 0.05, x_so + 0.05, mp.h_isolator),
        (x_so - 0.05, x_co + 0.05, mp.h_combustor),
        (x_co - 0.05, x_tot + 0.05, mp.h_nozzle),
    ):
        b = field.add("Box")
        field.setNumber(b, "VIn", h * mp.size_scale)
        field.setNumber(b, "VOut", mp.h_far * mp.size_scale)
        field.setNumber(b, "Thickness", 0.0)
        field.setNumber(b, "XMin", x0)
        field.setNumber(b, "XMax", x1)
        field.setNumber(b, "YMin", ymin)
        field.setNumber(b, "YMax", ymax)
        field.setNumber(b, "ZMin", 0.0)
        field.setNumber(b, "ZMax", B)
        boxes.append(b)

    back = field.add("Min")
    field.setNumbers(back, "FieldsList", boxes)
    field.setAsBackgroundMesh(back)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def _collect_stats(dimension: int) -> dict:
    n_nodes = len(gmsh.model.mesh.getNodes()[0])
    elem_types, elem_tags, _ = gmsh.model.mesh.getElements(dimension)
    if dimension == 2:
        names = {2: "triangle", 3: "quad"}
    else:
        names = {4: "tetrahedron", 5: "hexahedron", 6: "prism", 7: "pyramid"}
    counts: dict[str, int] = {}
    total = 0
    for t, tags in zip(elem_types, elem_tags):
        if t in names:
            counts[names[t]] = counts.get(names[t], 0) + len(tags)
            total += len(tags)
    key = "n_surface_elements" if dimension == 2 else "n_volume_elements"
    return {"n_nodes": n_nodes, key: total, **counts}


# ---------------------------------------------------------------------------
# SU2 ASCII exporters
# ---------------------------------------------------------------------------
def _write_su2_mesh_2d(out_su2: Path) -> None:
    """Write the generated 2D model as a SU2 ASCII ``NDIME= 2`` mesh.

    Boundary markers are re-derived FROM the volume triangulation: each
    domain boundary edge (an edge shared by exactly one triangle) is
    assigned to the 1D physical group whose line mesh passes closest to
    its midpoint. This guarantees that every SU2 surface element matches a
    volume face (the gmsh BoundaryLayer field can otherwise leave orphan
    wall nodes that never belong to any triangle).
    """
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    idx = {int(tag): i for i, tag in enumerate(node_tags)}
    coords = node_coords.reshape(-1, 3)

    vol_ids: list[int] = []
    vol_lines: list[str] = []
    triangles: list[list[int]] = []
    etypes, _etags, enodes = gmsh.model.mesh.getElements(2)
    for t, nlist in zip(etypes, enodes):
        su2t = _GMSH_TO_SU2_2D.get(int(t))
        if su2t is None:
            raise ValueError(f"unsupported 2D element type in gmsh: {t}")
        npts = 3 if su2t == 5 else 4
        arr = nlist.reshape(-1, npts)
        for row in arr:
            line = [int(n) for n in row]
            # orient every triangle counter-clockwise (positive signed area)
            if su2t == 5:
                c0 = coords[idx[line[0]]]
                c1 = coords[idx[line[1]]]
                c2 = coords[idx[line[2]]]
                area2 = ((c1[0] - c0[0]) * (c2[1] - c0[1])
                         - (c1[1] - c0[1]) * (c2[0] - c0[0]))
                if area2 < 0.0:
                    line[1], line[2] = line[2], line[1]
            vol_ids.extend(line)
            triangles.append(line)
            vol_lines.append(f"{su2t} " + " ".join(str(n) for n in line))
    vol_ids_set = set(vol_ids)
    if any(len(tri) != 3 for tri in triangles):
        raise ValueError("SU2 export currently supports triangle volume meshes only")
    _neg = 0
    for tri in triangles:
        c0 = coords[idx[tri[0]]]; c1 = coords[idx[tri[1]]]; c2 = coords[idx[tri[2]]]
        a2 = ((c1[0]-c0[0])*(c2[1]-c0[1]) - (c1[1]-c0[1])*(c2[0]-c0[0]))
        if a2 < 0.0:
            _neg += 1
    print(f"[mesh] orientation check: negative={_neg} of {len(triangles)}", file=sys.stderr)

    # --- physical boundary curves (1D groups) as polyline segments --------
    curve_segs: list[tuple[str, list[tuple]]] = []
    for dim, ptag in gmsh.model.getPhysicalGroups():
        if dim != 1:
            continue
        name = gmsh.model.getPhysicalName(dim, ptag) or f"MARKER_{ptag}"
        segs: list[tuple[float, ...]] = []
        for ent in gmsh.model.getEntitiesForPhysicalGroup(dim, ptag):
            mtypes, _mtags, mnodes = gmsh.model.mesh.getElements(dim=dim, tag=ent)
            for t, nlist in zip(mtypes, mnodes):
                if int(t) != 1:
                    continue
                a = nlist.reshape(-1, 2)
                for u, v in a:
                    segs.append((float(coords[idx[int(u)]][0]), float(coords[idx[int(u)]][1]),
                                 float(coords[idx[int(v)]][0]), float(coords[idx[int(v)]][1])))
        if segs:
            curve_segs.append((name, segs))

    def dist_to_segs(p, segs, eps2: float = 1e-12):
        px, py = p
        best = float("inf")
        for (x1, y1, x2, y2) in segs:
            dx, dy = x2 - x1, y2 - y1
            l2 = dx * dx + dy * dy
            if l2 == 0.0:
                d2 = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = min(max(((px - x1) * dx + (py - y1) * dy) / l2, 0.0), 1.0)
                d2 = (px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2
            if d2 < best:
                best = d2
        return best < eps2

    # --- boundary edges of the triangulation ------------------------------
    edge_count: dict[tuple[int, int], int] = {}
    edge_dir: dict[tuple[int, int], tuple[int, int]] = {}
    for tri in triangles:
        for k in range(3):
            u, v = tri[k], tri[(k + 1) % 3]
            e = (min(u, v), max(u, v))
            edge_count[e] = edge_count.get(e, 0) + 1
            edge_dir.setdefault(e, (u, v))
    boundary_edges = [e for e, c in edge_count.items() if c == 1]

    marker_edges: list[tuple[str, list[tuple[int, int]]]] = []
    for name, segs in curve_segs:
        mine: list[tuple[int, int]] = []
        for e in boundary_edges:
            c = coords[idx[e[0]]], coords[idx[e[1]]]
            mid = ((float(c[0][0]) + float(c[1][0])) * 0.5, (float(c[0][1]) + float(c[1][1])) * 0.5)
            if dist_to_segs(mid, segs):
                mine.append(e)
        if mine:
            marker_edges.append((name, mine))

    final_ids = sorted(vol_ids_set)
    remap = {old: new for new, old in enumerate(final_ids)}
    lines = ["NDIME= 2", f"NELEM= {len(vol_lines)}"]
    for line in vol_lines:
        parts = line.split()
        lines.append(parts[0] + " " + " ".join(str(remap[int(n)]) for n in parts[1:]))
    lines.append(f"NPOIN= {len(final_ids)}")
    for nid in final_ids:
        c = coords[idx[nid]]
        lines.append(f"{c[0]:.16e} {c[1]:.16e}")
    lines.append(f"NMARK= {len(marker_edges)}")
    for name, mine in marker_edges:
        lines.append(f"MARKER_TAG= {name}")
        lines.append(f"MARKER_ELEMS= {len(mine)}")
        for a, b in mine:
            lines.append(f"3 {remap[a]} {remap[b]}")
    out_su2.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _face_normal(poly: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Newell's method; normal follows the right-hand rule of the ordering."""
    nx = ny = nz = 0.0
    k = len(poly)
    for i in range(k):
        xi, yi, zi = poly[i]
        xj, yj, zj = poly[(i + 1) % k]
        nx += yi * zj - zi * yj
        ny += zi * xj - xi * zj
        nz += xi * yj - yi * xj
    norm = (nx * nx + ny * ny + nz * nz) ** 0.5
    if norm == 0.0:
        return 0.0, 0.0, 0.0
    return nx / norm, ny / norm, nz / norm


def _flip_face(nodes: list[int]) -> list[int]:
    if len(nodes) == 3:
        return [nodes[0], nodes[2], nodes[1]]
    return [nodes[0], nodes[-1], nodes[-2], nodes[1]]  # quad: reverse order


def _write_su2_mesh_3d(out_su2: Path) -> None:
    """Write the 3D extruded model as a SU2 ASCII ``NDIME= 3`` mesh.

    Volume elements are mapped directly (gmsh linear tet/prism/pyramid/hexa
    node order matches VTK). Marker faces come straight from the physical
    surface meshes and are oriented so their normal points away from the
    adjacent volume cell (SU2 uses the marker face normal for inlet/outlet
    and wall directions).
    """
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    idx = {int(tag): i for i, tag in enumerate(node_tags)}
    coords = node_coords.reshape(-1, 3)

    # --- volume elements ---------------------------------------------------
    vol_cells: list[tuple[int, list[int]]] = []
    vol_ids_set: set[int] = set()
    etypes, _etags, enodes = gmsh.model.mesh.getElements(3)
    for t, nlist in zip(etypes, enodes):
        su2t = _GMSH_TO_SU2_3D.get(int(t))
        if su2t is None:
            raise ValueError(f"unsupported 3D element type in gmsh: {t}")
        npts = _SU2_3D_NPOINTS[su2t]
        arr = nlist.reshape(-1, npts)
        for row in arr:
            nodes = [int(n) for n in row]
            vol_cells.append((su2t, nodes))
            vol_ids_set.update(nodes)

    # node -> volume cells, for marker-face orientation
    cell_of_node: dict[int, list[int]] = {}
    for ci, (_, nodes) in enumerate(vol_cells):
        for n in nodes:
            cell_of_node.setdefault(n, []).append(ci)

    # --- marker faces from physical 2D groups -----------------------------
    marker_faces: list[tuple[str, list[tuple[int, list[int]]]]] = []
    for dim, ptag in gmsh.model.getPhysicalGroups():
        if dim != 2:
            continue
        name = gmsh.model.getPhysicalName(dim, ptag) or f"MARKER_{ptag}"
        faces: list[tuple[int, list[int]]] = []
        for ent in gmsh.model.getEntitiesForPhysicalGroup(dim, ptag):
            mtypes, _mtags, mnodes = gmsh.model.mesh.getElements(dim=2, tag=ent)
            for t, nlist in zip(mtypes, mnodes):
                su2t2 = _GMSH_TO_SU2_FACE.get(int(t))
                if su2t2 is None:
                    continue
                npts = _SU2_FACE_NPOINTS[su2t2]
                arr = nlist.reshape(-1, npts)
                for row in arr:
                    nodes = [int(n) for n in row]
                    # orient outward relative to the adjacent volume cell
                    cand = set(cell_of_node.get(nodes[0], []))
                    for n in nodes[1:]:
                        cand &= set(cell_of_node.get(n, []))
                    if not cand:
                        continue
                    cell = next(iter(cand))
                    cc = [coords[idx[n]] for n in vol_cells[cell][1]]
                    fc = [coords[idx[n]] for n in nodes]
                    centroid = tuple(sum(c[i] for c in cc) / len(cc) for i in range(3))
                    fcent = tuple(sum(c[i] for c in fc) / len(fc) for i in range(3))
                    nrm = _face_normal(fc)
                    toward = sum(nrm[i] * (centroid[i] - fcent[i]) for i in range(3))
                    if toward > 0.0:
                        nodes = _flip_face(nodes)
                    faces.append((su2t2, nodes))
        if faces:
            marker_faces.append((name, faces))

    final_ids = sorted(vol_ids_set)
    remap = {old: new for new, old in enumerate(final_ids)}
    lines = ["NDIME= 3", f"NELEM= {len(vol_cells)}"]
    for su2t, nodes in vol_cells:
        lines.append(f"{su2t} " + " ".join(str(remap[n]) for n in nodes))
    lines.append(f"NPOIN= {len(final_ids)}")
    for nid in final_ids:
        c = coords[idx[nid]]
        lines.append(f"{c[0]:.16e} {c[1]:.16e} {c[2]:.16e}")
    lines.append(f"NMARK= {len(marker_faces)}")
    for name, faces in marker_faces:
        lines.append(f"MARKER_TAG= {name}")
        lines.append(f"MARKER_ELEMS= {len(faces)}")
        for su2t2, nodes in faces:
            lines.append(f"{su2t2} " + " ".join(str(remap[n]) for n in nodes))
    out_su2.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def make_mesh(cfg, out_msh: Path, verbose: bool = False) -> dict:
    """Generate the mesh (2D planar or 3D extruded) and return statistics."""
    gp, mp = cfg.geometry, cfg.mesh
    geo = build_geometry(gp)
    out_msh = Path(out_msh)
    out_msh.parent.mkdir(parents=True, exist_ok=True)
    dimension = int(getattr(cfg, "dimension", 2))

    gmsh.initialize()
    try:
        _configure(verbose, mp)
        if dimension == 3:
            tags = _build_cad_3d(geo, gp)
            _apply_fields_3d(geo, tags, mp)
            try:
                gmsh.model.mesh.generate(3)
            except Exception as exc:  # noqa: BLE001
                print(f"[mesh] 3D meshing failed ({exc}); retrying from scratch.",
                      file=sys.stderr)
                gmsh.model.mesh.clear()
                gmsh.model.mesh.generate(3)
            stats = _collect_stats(3)
            _write_su2_mesh_3d(out_msh)
        else:
            tags = _build_cad_2d(geo, gp)
            _apply_fields_2d(geo, tags, mp)
            try:
                gmsh.model.mesh.generate(2)
            except Exception as exc:  # noqa: BLE001
                print(f"[mesh] 2D boundary-layer mesh failed ({exc}); "
                      "falling back to isotropic mesh -- CHECK FIRST-CELL HEIGHT (y+).",
                      file=sys.stderr)
                gmsh.model.mesh.clear()
                gmsh.model.mesh.generate(2)
            stats = _collect_stats(2)
            _write_su2_mesh_2d(out_msh)
        stats["first_cell_h"] = mp.h_wall_n
        return stats
    finally:
        gmsh.finalize()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the scramjet mesh with Gmsh.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow.yaml")
    ap.add_argument("--out", default=None, help="output .su2 path")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_case(args.case)
    geo = build_geometry(cfg.geometry)
    print(summary(cfg.geometry, geo))
    out = Path(args.out) if args.out else Path("runs") / cfg.name / "mesh" / f"{cfg.name}.su2"
    stats = make_mesh(cfg, out, verbose=args.verbose)
    print(f"[mesh] wrote {out}")
    print(f"[mesh] {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())