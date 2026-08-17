"""Isometric projection and the component form library.

Projection
----------
True isometric, 30 degrees. A grid point (x, y) on the ground plane and a height
z map to the sheet as:

    X = (x - y) * cos(30) * S
    Y = (x + y) * sin(30) * S - z * H

Consequences worth remembering, because they drive every layout decision:

* +x runs down-and-right, +y runs down-and-left. The near corner of any
  footprint is (x_max, y_max).
* The two vertical faces you can see are the plane x = x_max (which lands on the
  RIGHT of the silhouette) and the plane y = y_max (which lands on the LEFT).
  The left face is conventionally the darkest because the light comes from the
  upper right.
* A circle on the ground plane projects to an axis-aligned ellipse with
  rx = r * cos(30) * S * sqrt(2) and ry = r * sin(30) * S * sqrt(2). No rotation
  needed, which makes drums and dishes cheap to draw.
* Painter's algorithm: sort solids by (x + y) of their far corner ascending and
  draw in that order. Nearer solids are drawn later and occlude correctly, as
  long as footprints do not overlap.

Every form function returns a list of primitive dicts in painter order. The
renderer maps the `role` of each primitive onto the active skin, so forms carry
no colour information at all.

Roles: "top" | "right" | "left" | "frame" | "detail" | "glow" | "cyl"
"""

import math

COS30 = math.cos(math.radians(30.0))
SIN30 = 0.5
ROOT2 = math.sqrt(2.0)


class Iso:
    """Ground-grid to sheet-coordinate projector."""

    def __init__(self, tile=54.0, unit_height=30.0, ox=0.0, oy=0.0):
        self.tile = float(tile)
        self.uh = float(unit_height)
        self.ox = float(ox)
        self.oy = float(oy)

    def pt(self, x, y, z=0.0):
        X = (x - y) * COS30 * self.tile + self.ox
        Y = (x + y) * SIN30 * self.tile - z * self.uh + self.oy
        return (X, Y)

    def ellipse_radii(self, r):
        """Sheet-space radii of a ground-plane circle of grid radius r."""
        return (r * COS30 * self.tile * ROOT2, r * SIN30 * self.tile * ROOT2)


# --------------------------------------------------------------------------
# primitive constructors
# --------------------------------------------------------------------------

def _poly(pts, role, hatch=False):
    return {"type": "poly", "pts": list(pts), "role": role, "hatch": hatch}


def _line(p1, p2, role="detail", weight=None):
    return {"type": "line", "p1": p1, "p2": p2, "role": role, "weight": weight}


def _path(d, role):
    return {"type": "path", "d": d, "role": role}


def _ellipse(cx, cy, rx, ry, role, hatch=False):
    return {
        "type": "ellipse", "cx": cx, "cy": cy, "rx": rx, "ry": ry,
        "role": role, "hatch": hatch,
    }


# --------------------------------------------------------------------------
# building blocks
# --------------------------------------------------------------------------

def _box(P, x, y, w, d, z0, z1, floors=0):
    """A rectangular prism from z0 to z1. Returns primitives in painter order."""
    x1, y1 = x + w, y + d
    top = [P.pt(x, y, z1), P.pt(x1, y, z1), P.pt(x1, y1, z1), P.pt(x, y1, z1)]
    right = [P.pt(x1, y, z1), P.pt(x1, y1, z1), P.pt(x1, y1, z0), P.pt(x1, y, z0)]
    left = [P.pt(x, y1, z1), P.pt(x1, y1, z1), P.pt(x1, y1, z0), P.pt(x, y1, z0)]

    out = [_poly(right, "right"), _poly(left, "left", hatch=True), _poly(top, "top")]

    # Horizontal course lines across both visible faces. This is what separates a
    # drawing that looks like a technical document from a stack of flat boxes --
    # real elevations are dense with storey lines, seams and panel joints.
    if floors and z1 > z0:
        for i in range(1, floors):
            z = z0 + (z1 - z0) * i / float(floors)
            out.append(_line(P.pt(x1, y, z), P.pt(x1, y1, z), "detail"))
            out.append(_line(P.pt(x, y1, z), P.pt(x1, y1, z), "detail"))
    return out


def _cylinder(P, cx, cy, r, z0, z1, ribs=5, role_top="top"):
    """Vertical cylinder. Side wall gets a gradient so it reads as curved."""
    rx, ry = P.ellipse_radii(r)
    tx, ty = P.pt(cx, cy, z1)
    bx, by = P.pt(cx, cy, z0)
    side = (
        "M %.2f %.2f L %.2f %.2f A %.2f %.2f 0 0 0 %.2f %.2f "
        "L %.2f %.2f A %.2f %.2f 0 0 1 %.2f %.2f Z"
    ) % (
        tx - rx, ty, bx - rx, by, rx, ry, bx + rx, by,
        tx + rx, ty, rx, ry, tx - rx, ty,
    )
    out = [_path(side, "cyl")]
    for i in range(ribs):
        f = -1.0 + 2.0 * (i + 1) / float(ribs + 1)
        ox = f * rx * 0.92
        dy = ry * math.sqrt(max(0.0, 1.0 - (ox / rx) ** 2)) * 0.999
        out.append(_line((tx + ox, ty + dy * 0.0), (bx + ox, by + dy), "detail"))
    out.append(_ellipse(tx, ty, rx, ry, role_top))
    return out


def _cone(P, cx, cy, r, z0, z1):
    rx, ry = P.ellipse_radii(r)
    bx, by = P.pt(cx, cy, z0)
    ax, ay = P.pt(cx, cy, z1)
    d = (
        "M %.2f %.2f L %.2f %.2f L %.2f %.2f A %.2f %.2f 0 0 1 %.2f %.2f Z"
    ) % (bx - rx, by, ax, ay, bx + rx, by, rx, ry, bx - rx, by)
    return [_path(d, "cyl"), _line((ax, ay), (bx, by - ry), "detail")]


# --------------------------------------------------------------------------
# form library -- each entry is form(P, x, y, w, d, h) -> [primitives]
# --------------------------------------------------------------------------

def f_slab(P, x, y, w, d, h):
    """Low-to-mid rectangular block. The default when nothing else fits."""
    return _box(P, x, y, w, d, 0, h, floors=max(2, int(round(h))))


def f_tower(P, x, y, w, d, h):
    """Tall block with a setback crown and a mast -- reads as the tall thing."""
    out = _box(P, x, y, w, d, 0, h, floors=max(3, int(round(h * 1.5))))
    ins = min(w, d) * 0.22
    out += _box(P, x + ins, y + ins, w - 2 * ins, d - 2 * ins, h, h + h * 0.30, floors=1)
    mx, my = P.pt(x + w / 2.0, y + d / 2.0, h + h * 0.30)
    out.append(_line((mx, my), (mx, my - P.uh * 0.9), "frame"))
    out.append({"type": "circle", "cx": mx, "cy": my - P.uh * 0.9, "r": 2.6,
                "role": "frame"})
    return out


def f_stack(P, x, y, w, d, h):
    """Stepped ziggurat. Good for anything tiered or sharded."""
    out = []
    steps = 3
    for i in range(steps):
        f = i / float(steps)
        ins_w = w * 0.16 * i
        ins_d = d * 0.16 * i
        out += _box(P, x + ins_w, y + ins_d, w - 2 * ins_w, d - 2 * ins_d,
                    h * f, h * (i + 1) / float(steps), floors=1)
    return out


def f_drum(P, x, y, w, d, h):
    """Cylinder inscribed in the footprint. Tanks, stores, buffers."""
    r = min(w, d) / 2.0
    cx, cy = x + w / 2.0, y + d / 2.0
    out = _cylinder(P, cx, cy, r, 0, h)
    rx, ry = P.ellipse_radii(r * 0.62)
    tx, ty = P.pt(cx, cy, h)
    out.append(_ellipse(tx, ty, rx, ry, "detail"))
    return out


def f_silo(P, x, y, w, d, h):
    """Narrow cylinder with a conical cap. Queues, hoppers, funnels."""
    r = min(w, d) / 2.0 * 0.62
    cx, cy = x + w / 2.0, y + d / 2.0
    out = _cylinder(P, cx, cy, r, 0, h * 0.78, ribs=3)
    out += _cone(P, cx, cy, r, h * 0.78, h * 1.06)
    return out


def f_vault(P, x, y, w, d, h):
    """Box with a barrel roof. Halls, archives, cold storage."""
    hb = h * 0.62
    out = _box(P, x, y, w, d, 0, hb, floors=2)
    # Barrel springs along +x, so the arc profile shows on the x = x_max face.
    x1, y1 = x + w, y + d
    a = P.pt(x1, y, hb)
    b = P.pt(x1, y1, hb)
    apex = P.pt(x1, y + d / 2.0, h)
    out.append(_path("M %.2f %.2f Q %.2f %.2f %.2f %.2f L %.2f %.2f Z" % (
        a[0], a[1], apex[0], apex[1] - P.uh * 0.25, b[0], b[1], a[0], a[1]),
        "right"))
    a2 = P.pt(x, y1, hb)
    apex2 = P.pt(x + w / 2.0, y1, h)
    out.append(_path("M %.2f %.2f Q %.2f %.2f %.2f %.2f" % (
        a2[0], a2[1], apex2[0], apex2[1] - P.uh * 0.25, b[0], b[1]), "frame"))
    for i in range(1, 4):
        t = i / 4.0
        p0 = P.pt(x + w * t, y, hb)
        p1 = P.pt(x + w * t, y1, hb)
        out.append(_line(p0, p1, "detail"))
    return out


def f_lattice(P, x, y, w, d, h):
    """Open braced frame -- no solid faces. Use for scaffolding-like elements:
    load balancers, meshes, fabrics, anything that is structure not substance."""
    out = []
    corners = [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]
    for (px, py) in corners:
        out.append(_line(P.pt(px, py, 0), P.pt(px, py, h), "frame"))
    for i in range(4):
        z = h * i / 3.0
        ring = [P.pt(px, py, z) for (px, py) in corners]
        for j in range(4):
            out.append(_line(ring[j], ring[(j + 1) % 4], "frame"))
    for i in range(3):
        z0 = h * i / 3.0
        z1 = h * (i + 1) / 3.0
        out.append(_line(P.pt(x + w, y, z0), P.pt(x + w, y + d, z1), "detail"))
        out.append(_line(P.pt(x + w, y + d, z0), P.pt(x + w, y, z1), "detail"))
        out.append(_line(P.pt(x, y + d, z0), P.pt(x + w, y + d, z1), "detail"))
        out.append(_line(P.pt(x + w, y + d, z0), P.pt(x, y + d, z1), "detail"))
    return out


def f_plinth(P, x, y, w, d, h):
    """Wide low pad with louvre slots. Edge nodes, pools, farms, racks."""
    hh = min(h, 0.85)
    out = _box(P, x, y, w, d, 0, hh, floors=1)
    n = max(3, int(round(w * 2)))
    for i in range(n):
        t0 = 0.12 + 0.76 * i / float(n)
        t1 = t0 + 0.76 / float(n) * 0.55
        p = [P.pt(x + w * t0, y + d * 0.14, hh), P.pt(x + w * t1, y + d * 0.14, hh),
             P.pt(x + w * t1, y + d * 0.86, hh), P.pt(x + w * t0, y + d * 0.86, hh)]
        out.append(_poly(p, "detail"))
    return out


def f_pyramid(P, x, y, w, d, h):
    """Truncated pyramid. Aggregators, reducers, funnels of authority."""
    ix, iy = w * 0.30, d * 0.30
    b = [P.pt(x, y, 0), P.pt(x + w, y, 0), P.pt(x + w, y + d, 0), P.pt(x, y + d, 0)]
    t = [P.pt(x + ix, y + iy, h), P.pt(x + w - ix, y + iy, h),
         P.pt(x + w - ix, y + d - iy, h), P.pt(x + ix, y + d - iy, h)]
    out = [
        _poly([b[1], b[2], t[2], t[1]], "right"),
        _poly([b[2], b[3], t[3], t[2]], "left", hatch=True),
        _poly(t, "top"),
    ]
    for i in range(1, 3):
        f = i / 3.0
        rb = [(b[k][0] + (t[k][0] - b[k][0]) * f, b[k][1] + (t[k][1] - b[k][1]) * f)
              for k in range(4)]
        out.append(_line(rb[1], rb[2], "detail"))
        out.append(_line(rb[2], rb[3], "detail"))
    return out


def f_dish(P, x, y, w, d, h):
    """Pad, mast and a parabolic dish. Externals, third parties, uplinks."""
    cx, cy = x + w / 2.0, y + d / 2.0
    out = _box(P, x + w * 0.22, y + d * 0.22, w * 0.56, d * 0.56, 0, h * 0.22,
               floors=1)
    out += _cylinder(P, cx, cy, min(w, d) * 0.075, h * 0.22, h * 0.80, ribs=1)
    mx, my = P.pt(cx, cy, h * 0.80)
    rx, ry = P.ellipse_radii(min(w, d) * 0.40)
    g = 'transform="translate(%.2f %.2f) rotate(-28)"' % (mx, my)
    out.append({"type": "group_open", "attrs": g})
    out.append(_ellipse(0, 0, rx, ry * 0.92, "top"))
    for i in (0.72, 0.44, 0.20):
        out.append(_ellipse(0, 0, rx * i, ry * 0.92 * i, "detail"))
    out.append(_line((-rx, 0), (rx, 0), "detail"))
    out.append({"type": "group_close"})
    return out


def f_core(P, x, y, w, d, h):
    """The emissive centrepiece: a drum with concentric ring plate, radial
    spokes and a halo. Exactly one of these per drawing -- it is the thing the
    whole sheet is about, and a second one destroys the hierarchy."""
    r = min(w, d) / 2.0
    cx, cy = x + w / 2.0, y + d / 2.0
    tx, ty = P.pt(cx, cy, h)
    rx, ry = P.ellipse_radii(r)
    out = [{"type": "glow", "cx": tx, "cy": ty, "r": rx * 1.9}]
    out += _cylinder(P, cx, cy, r, 0, h, ribs=8)
    for i in (0.84, 0.66, 0.30):
        out.append(_ellipse(tx, ty, rx * i, ry * i, "detail"))
    out.append(_ellipse(tx, ty, rx * 0.48, ry * 0.48, "glow"))
    for k in range(8):
        a = math.radians(k * 45.0)
        out.append(_line(
            (tx + math.cos(a) * rx * 0.30, ty + math.sin(a) * ry * 0.30),
            (tx + math.cos(a) * rx * 0.84, ty + math.sin(a) * ry * 0.84),
            "frame"))
    return out


FORMS = {
    "slab": f_slab,
    "tower": f_tower,
    "stack": f_stack,
    "drum": f_drum,
    "silo": f_silo,
    "vault": f_vault,
    "lattice": f_lattice,
    "plinth": f_plinth,
    "pyramid": f_pyramid,
    "dish": f_dish,
    "core": f_core,
}

FORM_NOTES = {
    "slab": "General processing block",
    "tower": "Primary service / tall stack",
    "stack": "Tiered or sharded element",
    "drum": "Store, tank or buffer",
    "silo": "Queue / hopper",
    "vault": "Archive or bulk hall",
    "lattice": "Open fabric / balancer",
    "plinth": "Pad, pool or rack farm",
    "pyramid": "Aggregator / reducer",
    "dish": "External uplink / third party",
    "core": "Primary energy or control core",
}


def build(form, P, x, y, w, d, h):
    fn = FORMS.get(str(form or "slab").lower())
    if fn is None:
        raise SystemExit("unknown form %r -- choose from: %s"
                         % (form, ", ".join(sorted(FORMS))))
    return fn(P, x, y, w, d, max(0.35, float(h)))
