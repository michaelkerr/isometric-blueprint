#!/usr/bin/env python3
"""render_blueprint.py -- isometric system map on a vintage engineering sheet.

    python3 render_blueprint.py spec.json -o sheet.svg [--skin sepia] [--pdf sheet.pdf]

Reads a system spec (see references/spec-schema.md), lays the components out on
an isometric ground grid, routes the dependency conduits, and emits one
self-contained SVG drawing sheet: drawing area, legend, explainer panel and
title block, aged and reproduced in the chosen skin.

Deterministic: the same spec always produces byte-identical output, because the
paper aging is driven by a hash of the title rather than the clock. That matters
for review -- you want to see what your edit changed, not what the RNG changed.
"""

import argparse
import hashlib
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import geometry as G  # noqa: E402
import profiles as PR  # noqa: E402
import router as R  # noqa: E402
import skins as SK  # noqa: E402

SHEET_W, SHEET_H = 1980.0, 1400.0
TRIM = 22.0
FRAME_IN = 16.0
PAD = 30.0
PANEL_W = 520.0
GUTTER = 22.0

SANS = "'Arial Narrow','Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "'Courier New',Courier,monospace"

REFS = "ABCDEFGHJKLMNPRSTUVWXYZ"  # I, O and Q omitted -- drafting convention

EDGE_STYLES = {
    "data": {"color": "ink", "w": 1.7, "dash": None,
             "note": "Data path -- synchronous request/response"},
    "control": {"color": "ink_soft", "w": 1.3, "dash": "8 3 1.8 3",
                "note": "Control path -- command, config, orchestration"},
    "event": {"color": "ink_soft", "w": 1.5, "dash": "7 5",
              "note": "Event path -- asynchronous notification"},
    "bulk": {"color": "ink", "w": 3.4, "dash": None, "double": True,
             "note": "Bulk transfer -- batch, replication, ETL"},
    "telemetry": {"color": "ink_faint", "w": 1.1, "dash": "1.8 3.4",
                  "note": "Telemetry -- metrics, logs, traces"},
    "secure": {"color": "accent2", "w": 1.8, "dash": None, "ticks": True,
               "note": "Protected channel -- mutual auth / encrypted"},
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def txt(x, y, s, size=11, fill="#000", family=MONO, anchor="start",
        weight="normal", ls=0.0, opacity=None):
    op = "" if opacity is None else ' opacity="%.2f"' % opacity
    lsa = "" if not ls else ' letter-spacing="%.2f"' % ls
    return ('<text x="%.2f" y="%.2f" font-family="%s" font-size="%.1f" '
            'fill="%s" text-anchor="%s" font-weight="%s"%s%s>%s</text>'
            % (x, y, family, size, fill, anchor, weight, lsa, op, esc(s)))


def clip(s, n):
    """Shorten to n characters at a word boundary, marking the elision.

    Hard slicing produces mid-word breaks like "Derived -- never authoritat",
    which reads as a broken document rather than an abbreviated one -- and it is
    worse than useless because it stays inside the frame and so looks fine to any
    check that only tests for overflow."""
    s = str(s)
    if len(s) <= n:
        return s
    cut = s[:n - 1]
    if " " in cut[max(0, n - 12):]:
        cut = cut[:cut.rstrip().rfind(" ")]
    return cut.rstrip(" ,;:-") + "…"


def wrap(s, width_px, size, cw=0.60):
    """Greedy wrap for monospace text. cw is the advance width as a fraction of
    the font size -- 0.60 is right for Courier and safe for fallbacks."""
    n = max(8, int(width_px / (size * cw)))
    words, lines, cur = str(s).split(), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= n:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def poly_pts(pts):
    return " ".join("%.2f,%.2f" % p for p in pts)


# ---------------------------------------------------------------------------
# spec normalisation and layout
# ---------------------------------------------------------------------------

def normalise(spec):
    nodes = spec.get("nodes") or []
    if not nodes:
        raise SystemExit("spec has no nodes")
    out = []
    for i, n in enumerate(nodes):
        d = {
            "id": n.get("id") or ("n%d" % i),
            "label": n.get("label") or n.get("id") or ("ITEM %d" % i),
            "ref": n.get("ref"),
            "form": n.get("form") or "slab",
            "tier": n.get("tier") or "_",
            "spec": list(n.get("spec") or [])[:4],
            "accent": bool(n.get("accent")),
            "h": float(n.get("height", 2.0)),
            # Keep the author's explicit choices distinct from the defaults, so
            # the profile can tell "the author insisted on this" apart from
            # "nobody said, so it fell back". Only the former is a departure.
            "kind": n.get("kind"),
            "criticality": n.get("criticality"),
            "scale": n.get("scale"),
            "_form_explicit": n.get("form"),
            "_height_explicit": n.get("height"),
            "_footprint_explicit": n.get("footprint"),
        }
        fp = n.get("footprint") or [2, 2]
        d["w"], d["d"] = float(fp[0]), float(fp[1])
        cell = n.get("cell")
        if cell:
            d["x"], d["y"] = float(cell[0]), float(cell[1])
        else:
            d["x"] = d["y"] = None
        out.append(d)

    # Reference letters must exist before the profile runs, because departures
    # are cited by ref and an uncitable departure is not much use to a reader.
    for i, n in enumerate(out):
        if not n["ref"]:
            n["ref"] = REFS[i % len(REFS)] + ("" if i < len(REFS)
                                              else str(i // len(REFS) + 1))

    mode = str(spec.get("profile_enforcement") or "record").lower()
    prof = PR.load(spec.get("profile") if spec.get("profile") is not None
                   else ("off" if mode == "off" else "software"))
    departures = PR.apply(prof, out, mode)
    for n in out:
        n["deviates"] = False
    if departures:
        cited = set()
        for msg in departures:
            for n in out:
                if ("(%s)" % n["ref"]) in msg:
                    cited.add(n["ref"])
        for n in out:
            n["deviates"] = n["ref"] in cited
    if departures and mode == "strict":
        raise SystemExit("profile %s violated in strict mode:\n  - %s"
                         % (prof.version, "\n  - ".join(departures)))
    if departures and mode == "warn":
        sys.stderr.write("profile departures:\n  - %s\n"
                         % "\n  - ".join(departures))

    if any(n["x"] is None for n in out):
        autolayout(out)
    return out, prof, (departures if mode == "record" else [])


def autolayout(nodes):
    """Place components in diagonal bands, one band per tier, in the order the
    tiers first appear in the spec. Flow therefore reads along +x (down-right on
    the sheet) and members of a tier stack along +y (down-left).

    Bands are centred on a common axis rather than top-aligned. Top-aligning
    makes the plot a ragged wedge with a large empty quarter, which wastes the
    sheet and makes the arrangement look accidental; centring produces the
    balanced rhombus you see on real general-arrangement drawings."""
    tiers, seen = [], set()
    for n in nodes:
        if n["tier"] not in seen:
            seen.add(n["tier"])
            tiers.append(n["tier"])
    bands = [[n for n in nodes if n["tier"] == t] for t in tiers]
    spans = []
    for band in bands:
        spans.append(sum(n["d"] for n in band) + 1.0 * (len(band) - 1))
    widest = max(spans) if spans else 0.0
    xc = 0.0
    for band, span in zip(bands, spans):
        yc = round(((widest - span) / 2.0) * 2) / 2.0
        for n in band:
            n["x"], n["y"] = xc, yc
            yc += n["d"] + 1.0
        xc += max(n["w"] for n in band) + 1.5


def extents(nodes):
    cols = max(n["x"] + n["w"] for n in nodes)
    rows = max(n["y"] + n["d"] for n in nodes)
    return math.ceil(cols), math.ceil(rows)


def fit(nodes, cols, rows, region):
    """Choose tile size and origin so the whole model plus headroom for callout
    bubbles lands inside `region` = (x0, y0, x1, y1)."""
    rx0, ry0, rx1, ry1 = region
    probe = G.Iso(tile=1.0, unit_height=1.0 * 30.0 / 54.0)
    xs, ys = [], []
    for n in nodes:
        for (px, py) in ((n["x"], n["y"]), (n["x"] + n["w"], n["y"]),
                         (n["x"] + n["w"], n["y"] + n["d"]), (n["x"], n["y"] + n["d"])):
            for z in (0.0, n["h"] * 1.35):
                X, Y = probe.pt(px, py, z)
                xs.append(X)
                ys.append(Y)
    # include a one-unit routing margin all round
    for (px, py) in ((-1, -1), (cols + 1, -1), (cols + 1, rows + 1), (-1, rows + 1)):
        X, Y = probe.pt(px, py, 0)
        xs.append(X)
        ys.append(Y)
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    head = 62.0  # sheet-space room above the tallest apex for bubbles
    tile = min((rx1 - rx0) / bw, (ry1 - ry0 - head) / bh)
    tile = max(16.0, min(tile, 92.0))
    P = G.Iso(tile=tile, unit_height=tile * 30.0 / 54.0)
    xs2, ys2 = [], []
    for n in nodes:
        for (px, py) in ((n["x"], n["y"]), (n["x"] + n["w"], n["y"]),
                         (n["x"] + n["w"], n["y"] + n["d"]), (n["x"], n["y"] + n["d"])):
            for z in (0.0, n["h"] * 1.35):
                X, Y = P.pt(px, py, z)
                xs2.append(X)
                ys2.append(Y)
    for (px, py) in ((-1, -1), (cols + 1, -1), (cols + 1, rows + 1), (-1, rows + 1)):
        X, Y = P.pt(px, py, 0)
        xs2.append(X)
        ys2.append(Y)
    P.ox = rx0 + ((rx1 - rx0) - (max(xs2) - min(xs2))) / 2.0 - min(xs2)
    P.oy = ry0 + head + ((ry1 - ry0 - head) - (max(ys2) - min(ys2))) / 2.0 - min(ys2)
    return P


# ---------------------------------------------------------------------------
# defs: patterns, filters, markers
# ---------------------------------------------------------------------------

def build_defs(S):
    d = ['<defs>']
    d.append(
        '<pattern id="hatch" width="7" height="7" patternTransform="rotate(45)" '
        'patternUnits="userSpaceOnUse">'
        '<line x1="0" y1="0" x2="0" y2="7" stroke="%s" stroke-width="0.7" '
        'opacity="0.55"/></pattern>' % S["ink_faint"])
    d.append(
        '<pattern id="xhatch" width="6" height="6" patternUnits="userSpaceOnUse">'
        '<path d="M0 0 L6 6 M6 0 L0 6" stroke="%s" stroke-width="0.5" '
        'opacity="0.45" fill="none"/></pattern>' % S["ink_faint"])
    d.append(
        '<linearGradient id="cylg" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="%s"/><stop offset="0.55" stop-color="%s"/>'
        '<stop offset="1" stop-color="%s"/></linearGradient>'
        % (S["face_left"], S["face_right"], S["face_top"]))
    d.append(
        '<radialGradient id="vign" cx="0.5" cy="0.5" r="0.78">'
        '<stop offset="0.45" stop-color="%s" stop-opacity="0"/>'
        '<stop offset="1" stop-color="%s" stop-opacity="0.95"/></radialGradient>'
        % (S["paper_edge"], S["paper_edge"]))
    if S.get("glow"):
        d.append(
            '<radialGradient id="glowg" cx="0.5" cy="0.5" r="0.5">'
            '<stop offset="0" stop-color="%s" stop-opacity="0.72"/>'
            '<stop offset="0.45" stop-color="%s" stop-opacity="0.26"/>'
            '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>'
            % (S["glow"], S["glow"], S["glow"]))
    d.append(
        '<filter id="grain" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="4" '
        'seed="7" result="n"/>'
        '<feColorMatrix in="n" type="saturate" values="0"/></filter>')
    d.append(
        '<filter id="mottle" x="-10%" y="-10%" width="120%" height="120%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="3" '
        'seed="19" result="n"/>'
        '<feColorMatrix in="n" type="saturate" values="0"/>'
        '<feComponentTransfer><feFuncA type="table" tableValues="0 0.9"/>'
        '</feComponentTransfer></filter>')
    d.append('<filter id="bleed" x="-20%" y="-20%" width="140%" height="140%">'
             '<feGaussianBlur stdDeviation="1.9"/></filter>')
    d.append('<filter id="soft" x="-40%" y="-40%" width="180%" height="180%">'
             '<feGaussianBlur stdDeviation="6"/></filter>')
    for key in ("ink", "ink_soft", "ink_faint", "accent", "accent2"):
        d.append(
            '<marker id="ar-%s" viewBox="0 0 10 8" refX="9" refY="4" '
            'markerWidth="7" markerHeight="6" orient="auto">'
            '<path d="M0 0 L10 4 L0 8 L2.6 4 Z" fill="%s"/></marker>'
            % (key, S[key]))
    d.append('</defs>')
    return "".join(d)


# ---------------------------------------------------------------------------
# ground plane
# ---------------------------------------------------------------------------

def draw_ground(P, cols, rows, S):
    o = []
    m = 1
    o.append('<g stroke="%s" fill="none" stroke-width="0.6" opacity="0.5">'
             % S["ink_faint"])
    for i in range(-m, cols + m + 1):
        a, b = P.pt(i, -m, 0), P.pt(i, rows + m, 0)
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>' % (a + b))
    for j in range(-m, rows + m + 1):
        a, b = P.pt(-m, j, 0), P.pt(cols + m, j, 0)
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>' % (a + b))
    o.append('</g>')
    # datum boundary, heavier, with corner ticks every unit
    corners = [P.pt(-m, -m), P.pt(cols + m, -m), P.pt(cols + m, rows + m),
               P.pt(-m, rows + m)]
    o.append('<polygon points="%s" fill="none" stroke="%s" stroke-width="1.5" '
             'opacity="0.85"/>' % (poly_pts(corners), S["ink_soft"]))
    o.append('<g stroke="%s" stroke-width="1.1" opacity="0.8">' % S["ink_soft"])
    for i in range(-m, cols + m + 1):
        a = P.pt(i, -m, 0)
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
                 % (a[0], a[1], a[0] + 4.5, a[1] - 7.8))
        b = P.pt(i, rows + m, 0)
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
                 % (b[0], b[1], b[0] - 4.5, b[1] + 7.8))
    for j in range(-m, rows + m + 1):
        a = P.pt(-m, j, 0)
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
                 % (a[0], a[1], a[0] - 4.5, a[1] - 7.8))
    o.append('</g>')
    return "".join(o)


def draw_dimensions(P, cols, rows, S, spec):
    """Two datum dimension lines along the near edges of the plot. They carry no
    real measurement -- their job is to say 'this is a surveyed arrangement'."""
    o = []
    m = 1
    a = P.pt(cols + m, rows + m, 0)
    b = P.pt(cols + m, -m, 0)
    c = P.pt(-m, rows + m, 0)

    def dim(p, q, label, out):
        nx = (q[1] - p[1])
        ny = -(q[0] - p[0])
        L = math.hypot(nx, ny) or 1.0
        nx, ny = nx / L * out, ny / L * out
        p2, q2 = (p[0] + nx, p[1] + ny), (q[0] + nx, q[1] + ny)
        mid = ((p2[0] + q2[0]) / 2.0, (p2[1] + q2[1]) / 2.0)
        s = ['<g stroke="%s" stroke-width="0.9" opacity="0.8" fill="none">'
             % S["ink_soft"]]
        s.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
                 'marker-start="url(#ar-ink_soft)" marker-end="url(#ar-ink_soft)"/>'
                 % (p2 + q2))
        s.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" opacity="0.5"/>'
                 % (p + (p2[0] + nx * 0.35, p2[1] + ny * 0.35)))
        s.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" opacity="0.5"/>'
                 % (q + (q2[0] + nx * 0.35, q2[1] + ny * 0.35)))
        s.append('</g>')
        s.append('<rect x="%.2f" y="%.2f" width="%.2f" height="13" fill="%s"/>'
                 % (mid[0] - len(label) * 3.1, mid[1] - 10,
                    len(label) * 6.2, S["paper"]))
        s.append(txt(mid[0], mid[1], label, 9, S["ink_soft"], MONO, "middle"))
        return "".join(s)

    o.append(dim(a, b, spec.get("dim_x") or ("%d GRID UNITS" % (cols + 2)), 30))
    o.append(dim(c, a, spec.get("dim_y") or ("%d GRID UNITS" % (rows + 2)), -30))
    return "".join(o)


# ---------------------------------------------------------------------------
# solids
# ---------------------------------------------------------------------------

ROLE_FILL = {"top": "face_top", "right": "face_right", "left": "face_left"}


def emit_prims(prims, S, accent=False):
    ink = S["accent"] if accent else S["ink"]
    o, open_groups = [], 0
    for p in prims:
        t = p["type"]
        if t == "group_open":
            o.append("<g %s>" % p["attrs"])
            open_groups += 1
            continue
        if t == "group_close":
            o.append("</g>")
            open_groups -= 1
            continue
        if t == "glow":
            if S.get("glow"):
                o.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="url(#glowg)"/>'
                         % (p["cx"], p["cy"], p["r"]))
            continue
        if t == "poly":
            fill = S.get(ROLE_FILL.get(p["role"], ""), "none")
            if p["role"] == "detail":
                fill = S["face_left"]
            o.append('<polygon points="%s" fill="%s" stroke="%s" '
                     'stroke-width="%.2f"/>'
                     % (poly_pts(p["pts"]), fill, ink,
                        1.5 if p["role"] in ROLE_FILL else 0.7))
            if p.get("hatch"):
                o.append('<polygon points="%s" fill="url(#hatch)" stroke="none"/>'
                         % poly_pts(p["pts"]))
            continue
        if t == "path":
            fill = "url(#cylg)" if p["role"] == "cyl" else S.get(
                ROLE_FILL.get(p["role"], ""), "none")
            o.append('<path d="%s" fill="%s" stroke="%s" stroke-width="1.5"/>'
                     % (p["d"], fill, ink))
            continue
        if t == "ellipse":
            fill = "none"
            if p["role"] == "top":
                fill = S["face_top"]
            elif p["role"] == "glow" and S.get("glow"):
                fill = S["glow"]
            o.append('<ellipse cx="%.2f" cy="%.2f" rx="%.2f" ry="%.2f" fill="%s" '
                     'stroke="%s" stroke-width="%.2f" %s/>'
                     % (p["cx"], p["cy"], p["rx"], p["ry"], fill, ink,
                        1.4 if p["role"] == "top" else 0.7,
                        'opacity="0.85"' if p["role"] == "glow" else ""))
            continue
        if t == "circle":
            o.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="none" stroke="%s" '
                     'stroke-width="1.1"/>' % (p["cx"], p["cy"], p["r"], ink))
            continue
        if t == "line":
            col = ink if p["role"] == "frame" else S["ink_soft"]
            o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                     'stroke-width="%.2f" opacity="%.2f"/>'
                     % (tuple(p["p1"]) + tuple(p["p2"]) + (
                         col,
                         p.get("weight") or (1.2 if p["role"] == "frame" else 0.65),
                         1.0 if p["role"] == "frame" else 0.8)))
    while open_groups > 0:
        o.append("</g>")
        open_groups -= 1
    return "".join(o)


def shadow(P, n, S):
    pts = [P.pt(n["x"], n["y"], 0), P.pt(n["x"] + n["w"], n["y"], 0),
           P.pt(n["x"] + n["w"], n["y"] + n["d"], 0), P.pt(n["x"], n["y"] + n["d"], 0)]
    off = P.tile * 0.16
    pts = [(x - off * 0.6, y + off * 0.35) for (x, y) in pts]
    return ('<polygon points="%s" fill="%s" opacity="0.22"/>'
            % (poly_pts(pts), S["ink_faint"]))


# ---------------------------------------------------------------------------
# conduits
# ---------------------------------------------------------------------------

def build_conduits(spec, nodes, P, cols, rows, S):
    by_id = {n["id"]: n for n in nodes}
    rt = R.Router(cols, rows, [(n["id"], n["x"], n["y"], n["w"], n["d"])
                              for n in nodes])
    drawables, labels = [], []
    for e in (spec.get("edges") or []):
        a, b = by_id.get(e.get("from")), by_id.get(e.get("to"))
        if not a or not b:
            continue
        from_id, to_id = a["id"], b["id"]
        kind = (e.get("kind") or "data").lower()
        st = EDGE_STYLES.get(kind, EDGE_STYLES["data"])
        accent = bool(e.get("accent"))
        ckey = "accent" if accent else st["color"]
        col = S[ckey]
        wgt = st["w"] + (0.5 if accent else 0.0)

        sa_side, sa, se = rt.anchor(a, (b["x"] + b["w"] / 2.0, b["y"] + b["d"] / 2.0))
        ta_side, ta, te = rt.anchor(b, (a["x"] + a["w"] / 2.0, a["y"] + a["d"] / 2.0))
        mid = rt.route(se, te)
        path = [sa] + mid + [ta]

        for p, q in zip(path, path[1:]):
            mx, my = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0
            sp, sq = P.pt(p[0], p[1], 0), P.pt(q[0], q[1], 0)
            seg = []
            if st.get("double"):
                seg.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
                           'stroke="%s" stroke-width="%.2f" stroke-linecap="round"/>'
                           % (sp + sq + (col, wgt)))
                seg.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
                           'stroke="%s" stroke-width="%.2f"/>'
                           % (sp + sq + (S["paper"], max(0.7, wgt - 2.4))))
            else:
                dash = ' stroke-dasharray="%s"' % st["dash"] if st.get("dash") else ""
                seg.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
                           'stroke="%s" stroke-width="%.2f"%s '
                           'stroke-linecap="round"/>' % (sp + sq + (col, wgt, dash)))
            if st.get("ticks"):
                n_t = 3
                for k in range(1, n_t + 1):
                    t = k / float(n_t + 1)
                    px = sp[0] + (sq[0] - sp[0]) * t
                    py = sp[1] + (sq[1] - sp[1]) * t
                    seg.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
                               'stroke="%s" stroke-width="1.2"/>'
                               % (px, py - 4, px, py + 4, col))
            drawables.append((mx + my,
                              '<g class="bp-edge" data-from="%s" data-to="%s">%s</g>'
                              % (esc(from_id), esc(to_id), "".join(seg))))

        # riser + port at each end, but only where the wall actually faces us
        for (side, anchor, node) in ((sa_side, sa, a), (ta_side, ta, b)):
            gp = P.pt(anchor[0], anchor[1], 0)
            if side in ("+x", "+y"):
                zp = min(node["h"] * 0.55, node["h"] - 0.15)
                pp = P.pt(anchor[0], anchor[1], zp)
                riser = ('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                         'stroke-width="%.2f" stroke-linecap="round"/>'
                         % (gp + pp + (col, max(1.1, wgt * 0.8))))
                riser += ('<rect x="%.2f" y="%.2f" width="7" height="7" fill="%s" '
                          'stroke="%s" stroke-width="1"/>'
                          % (pp[0] - 3.5, pp[1] - 3.5, S["paper"], col))
                drawables.append((anchor[0] + anchor[1] + 0.01,
                                  '<g class="bp-edge" data-from="%s" data-to="%s">%s</g>'
                                  % (esc(from_id), esc(to_id), riser)))
            else:
                drawables.append((anchor[0] + anchor[1] + 0.01,
                                  '<g class="bp-edge" data-from="%s" data-to="%s">'
                                  '<circle cx="%.2f" cy="%.2f" r="2.6" fill="%s"/></g>'
                                  % (esc(from_id), esc(to_id), gp[0], gp[1], col)))

        # arrowhead at the target entry, pointing along the last leg
        if len(path) >= 2:
            p, q = path[-2], path[-1]
            sp, sq = P.pt(p[0], p[1], 0), P.pt(q[0], q[1], 0)
            ux, uy = sq[0] - sp[0], sq[1] - sp[1]
            L = math.hypot(ux, uy) or 1.0
            back = 11.0
            hx, hy = sq[0] - ux / L * back, sq[1] - uy / L * back
            drawables.append((q[0] + q[1] + 0.02,
                              '<g class="bp-edge" data-from="%s" data-to="%s">'
                              '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
                              'stroke="%s" stroke-width="%.2f" '
                              'marker-end="url(#ar-%s)"/></g>'
                              % (esc(from_id), esc(to_id),
                                 hx, hy, sq[0], sq[1], col, wgt, ckey)))

        if e.get("payload"):
            best = max(zip(path, path[1:]),
                       key=lambda pr: abs(pr[0][0] - pr[1][0]) + abs(pr[0][1] - pr[1][1]))
            mp = ((best[0][0] + best[1][0]) / 2.0, (best[0][1] + best[1][1]) / 2.0)
            sx, sy = P.pt(mp[0], mp[1], 0)
            labels.append((sx, sy, str(e["payload"]), col, from_id, to_id))
    return drawables, labels


class Obstacles:
    """Keep-out register for annotation.

    Annotation is what usually ruins a generated technical drawing: the geometry
    comes out fine and then the labels land on top of each other and on top of
    the components, and the sheet stops being readable. So every label asks this
    register for the first candidate position that is clear, and once granted it
    reserves that space. Component silhouettes are seeded in first, which is why
    labels drift outward from the massing instead of sitting on it."""

    def __init__(self):
        self.rects = []

    def overlap(self, r):
        ax0, ay0, ax1, ay1 = r
        total = 0.0
        for (bx0, by0, bx1, by1) in self.rects:
            ox = min(ax1, bx1) - max(ax0, bx0)
            oy = min(ay1, by1) - max(ay0, by0)
            if ox > 0 and oy > 0:
                total += ox * oy
        return total

    def hit(self, r):
        return self.overlap(r) > 0.0

    def add(self, r):
        self.rects.append(r)

    def place(self, candidates):
        """candidates: list of (payload, rect), best-first. Returns the first
        clear one.

        When everything collides -- which happens on genuinely dense sheets --
        fall back to the candidate with the *smallest* overlap rather than the
        last one tried. Taking the last candidate is what produces the classic
        failure where one label flies off to an absurd position while a nearly
        clear slot sat unused two candidates earlier."""
        best = None
        for payload, rect in candidates:
            ov = self.overlap(rect)
            if ov == 0.0:
                self.add(rect)
                return payload, rect
            if best is None or ov < best[0]:
                best = (ov, payload, rect)
        self.add(best[2])
        return best[1], best[2]


def seed_obstacles(P, nodes, region):
    """Reserve the on-sheet silhouette of every component, plus everything
    outside the drawing region, so annotation cannot wander into the legend
    column or off the sheet."""
    obs = Obstacles()
    for n in nodes:
        xs, ys = [], []
        for (px, py) in ((n["x"], n["y"]), (n["x"] + n["w"], n["y"]),
                         (n["x"] + n["w"], n["y"] + n["d"]), (n["x"], n["y"] + n["d"])):
            for z in (0.0, n["h"] * 1.1):
                X, Y = P.pt(px, py, z)
                xs.append(X)
                ys.append(Y)
        obs.add((min(xs) + 6, min(ys) + 6, max(xs) - 6, max(ys) - 6))
    rx0, ry0, rx1, ry1 = region
    big = 4000.0
    obs.add((-big, -big, rx0, big))
    obs.add((rx1, -big, big, big))
    obs.add((-big, -big, big, ry0))
    obs.add((-big, ry1, big, big))
    return obs


def emit_payload_labels(labels, S, obs):
    o = []
    for entry in labels:
        x, y, s, col = entry[0], entry[1], entry[2], entry[3]
        edge_from = entry[4] if len(entry) > 4 else None
        edge_to = entry[5] if len(entry) > 5 else None
        w = len(s) * 5.6 + 12
        # Generous candidate set. A payload tag can sit anywhere near its
        # conduit as long as a leader connects the two, so trying many positions
        # costs nothing and is the difference between a readable sheet and a pile.
        cands = []
        for dy in (-14, -30, -46, 16, 32, -62, 48, -80, 64, -98):
            for dx in (0, 30, -30, 62, -62, 96, -96, 134, -134):
                cx, cy = x + dx, y + dy
                cands.append(((cx, cy), (cx - w / 2.0 - 3, cy - 12,
                                         cx + w / 2.0 + 3, cy + 5)))
        (cx, cy), _r = obs.place(cands)
        col = col if col != S["ink_faint"] else S["ink_soft"]
        if edge_from and edge_to:
            o.append('<g class="bp-edge" data-from="%s" data-to="%s">'
                     % (esc(edge_from), esc(edge_to)))
        if (cx, cy) != (x, y - 14):
            o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                     'stroke-width="0.7" opacity="0.7" stroke-dasharray="2 2"/>'
                     % (x, y, cx, cy + 2, col))
        o.append('<circle cx="%.2f" cy="%.2f" r="2.2" fill="%s"/>' % (x, y, col))
        o.append('<rect x="%.2f" y="%.2f" width="%.2f" height="14" rx="1.5" '
                 'fill="%s" stroke="%s" stroke-width="0.6" opacity="0.96"/>'
                 % (cx - w / 2.0, cy - 10.5, w, S["paper"], S["ink_faint"]))
        o.append(txt(cx, cy, s, 9, col, MONO, "middle"))
        if edge_from and edge_to:
            o.append('</g>')
    return "".join(o)


# ---------------------------------------------------------------------------
# callouts
# ---------------------------------------------------------------------------

def emit_callouts(P, nodes, S, mid_x, obs):
    """Ref bubble + designation + first spec line, on a leader from the apex."""
    o = []
    # Annotate far components first: they are the ones boxed in by everything
    # else, so they get first claim on the clear space above the massing.
    for n in sorted(nodes, key=lambda q: (q["x"] + q["y"])):
        top = n["h"] * (1.34 if n["form"] == "tower" else 1.02)
        apex = P.pt(n["x"] + n["w"] / 2.0, n["y"] + n["d"] / 2.0, top)
        label = clip(n["label"].upper(), 28)
        sub = clip(n["spec"][0] if n["spec"] else G.FORM_NOTES.get(n["form"], ""), 34)
        lw = max(len(label) * 6.8, len(sub) * 5.3) + 20
        prefer_right = apex[0] >= mid_x

        # Leaders in hand drafting are angled, not strictly vertical, so the
        # bubble is allowed to slide sideways as well as up. Sorting candidates
        # by lift first keeps annotation tight to the massing when there is room.
        cands = []
        for lift in (36, 52, 70, 90, 112, 136, 162, 192, 224, 258, -34, -66):
            for dx in (0, -38, 38, -80, 80, -126, 126, -176, 176):
                for right in ((True, False) if prefer_right else (False, True)):
                    bx, by = apex[0] + dx, apex[1] - lift
                    if right:
                        rect = (bx - 13, by - 15, bx + 16 + lw, by + 17)
                    else:
                        rect = (bx - 16 - lw, by - 15, bx + 13, by + 17)
                    cands.append(((bx, by, right), rect))
        (bx, by, right), _r = obs.place(cands)

        col = S["accent"] if n["accent"] else S["ink"]
        o.append('<g class="bp-callout" data-id="%s">' % esc(n["id"]))
        # Land the leader on the rim of the bubble facing the apex, so it reads as
        # a leader rather than a line that stops short of or stabs through it.
        vx, vy = apex[0] - bx, apex[1] - by
        vl = math.hypot(vx, vy) or 1.0
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                 'stroke-width="0.9" opacity="0.9" stroke-dasharray="3 2"/>'
                 % (apex[0], apex[1], bx + vx / vl * 11.5, by + vy / vl * 11.5, col))
        o.append('<circle cx="%.2f" cy="%.2f" r="11" fill="%s" stroke="%s" '
                 'stroke-width="1.3"/>' % (bx, by, S["paper"], col))
        o.append(txt(bx, by + 4, n["ref"], 12, col, SANS, "middle", "bold"))
        lx = bx + (16 if right else -16)
        anchor = "start" if right else "end"
        o.append(txt(lx, by - 1, label, 11.5, S["ink"], SANS, anchor, "bold", 0.6))
        if sub:
            o.append(txt(lx, by + 11, sub, 8.8, S["ink_soft"], MONO, anchor))
        o.append('</g>')
    return "".join(o)


# ---------------------------------------------------------------------------
# panels
# ---------------------------------------------------------------------------

def panel_frame(x, y, w, h, title, S, num=None):
    o = ['<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="none" '
         'stroke="%s" stroke-width="1.3"/>' % (x, y, w, h, S["ink"])]
    o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
             'stroke-width="1.3"/>' % (x, y + 26, x + w, y + 26, S["ink"]))
    o.append('<rect x="%.2f" y="%.2f" width="%.2f" height="26" fill="%s" '
             'opacity="0.45"/>' % (x, y, w, S["face_top"]))
    o.append(txt(x + 10, y + 18, title, 12.5, S["ink"], SANS, "start", "bold", 1.5))
    if num:
        o.append(txt(x + w - 10, y + 18, num, 10.5, S["ink_soft"], MONO, "end"))
    return "".join(o)


def thumb(form, x, y, size, S):
    """Tiny isometric pictogram of a form, for the legend."""
    P = G.Iso(tile=size, unit_height=size * 30.0 / 54.0, ox=x, oy=y)
    prims = G.build(form, P, -0.5, -0.5, 1.0, 1.0, 1.15)
    return '<g>%s</g>' % emit_prims(prims, S)


def draw_legend(x, y, w, S, nodes, used_kinds, spec, prof=None):
    form_kind = {}
    for n in nodes:
        if n.get("kind") and n["form"] not in form_kind:
            form_kind[n["form"]] = n["kind"]
    forms = []
    for n in nodes:
        if n["form"] not in forms:
            forms.append(n["form"])
    rows_f = (len(forms) + 1) // 2
    h = 34 + rows_f * 46 + 16 + len(used_kinds) * 22 + 16
    o = [panel_frame(x, y, w, h, "LEGEND", S,
                     prof.version if prof else "SH 1 OF 1")]
    cy = y + 34
    colw = (w - 24) / 2.0
    for i, f in enumerate(forms):
        cx = x + 12 + (i % 2) * colw
        ry = cy + (i // 2) * 46
        o.append(thumb(f, cx + 26, ry + 34, 17, S))
        title = (form_kind.get(f) or f).upper().replace("-", " ")
        o.append(txt(cx + 56, ry + 22, title, 10.5, S["ink"], SANS, "start",
                     "bold", 0.5))
        sub = (prof.note_for(form_kind[f]) if (prof and f in form_kind)
               else G.FORM_NOTES.get(f, ""))
        o.append(txt(cx + 56, ry + 34, sub or G.FORM_NOTES.get(f, ""), 8.4,
                     S["ink_soft"], MONO))
    ky = cy + rows_f * 46 + 8
    o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
             'stroke-width="0.8" opacity="0.6"/>' % (x + 10, ky, x + w - 10, ky,
                                                     S["ink_soft"]))
    ky += 18
    for kind in used_kinds:
        st = EDGE_STYLES[kind]
        col = S[st["color"]]
        dash = ' stroke-dasharray="%s"' % st["dash"] if st.get("dash") else ""
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                 'stroke-width="%.2f"%s marker-end="url(#ar-%s)"/>'
                 % (x + 12, ky, x + 74, ky, col, st["w"], dash, st["color"]))
        if st.get("double"):
            o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                     'stroke-width="%.2f"/>' % (x + 12, ky, x + 70, ky, S["paper"],
                                                max(0.7, st["w"] - 2.4)))
        o.append(txt(x + 84, ky + 3.5, st["note"], 9, S["ink"], MONO))
        ky += 22
    return "".join(o), h


def draw_index(x, y, w, S, nodes):
    anydev = any(n.get("deviates") for n in nodes)
    h = 26 + 16 + 6 + 14 + len(nodes) * 19 + 6 + (16 if anydev else 0)
    o = [panel_frame(x, y, w, h, "COMPONENT SCHEDULE", S, "REF / SPEC")]
    ry = y + 42
    o.append(txt(x + 12, ry, "REF", 8.6, S["ink_soft"], MONO, "start", "bold"))
    o.append(txt(x + 44, ry, "DESIGNATION", 8.6, S["ink_soft"], MONO, "start", "bold"))
    o.append(txt(x + w - 12, ry, "RATING / NOTE", 8.6, S["ink_soft"], MONO, "end",
                 "bold"))
    ry += 6
    o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
             'stroke-width="0.7" opacity="0.6"/>' % (x + 10, ry, x + w - 10, ry,
                                                     S["ink_soft"]))
    ry += 14
    for n in nodes:
        col = S["accent"] if n["accent"] else S["ink"]
        mark = "*" if n.get("deviates") else " "
        o.append(txt(x + 12, ry, n["ref"], 10, col, MONO, "start", "bold"))
        if mark.strip():
            o.append(txt(x + 27, ry, mark, 11, S["accent"], MONO, "start", "bold"))
        o.append(txt(x + 44, ry, clip(n["label"].upper(), 26), 9.6, S["ink"], MONO))
        note = n["spec"][1] if len(n["spec"]) > 1 else (
            n["spec"][0] if n["spec"] else G.FORM_NOTES.get(n["form"], ""))
        o.append(txt(x + w - 12, ry, clip(note, 26), 8.8, S["ink_soft"], MONO, "end"))
        ry += 19
    if anydev:
        o.append(txt(x + 12, ry + 4, "*  DEPARTURE FROM STANDARD -- SEE NOTES",
                     8.2, S["accent"], MONO, "start", "bold", 0.5))
    return "".join(o), h


def draw_explainer(x, y, w, S, spec, max_h=None, departures=None):
    ex = spec.get("explainer") or {}
    head = ex.get("heading") or "DESCRIPTION OF OPERATION"
    paras = ex.get("paragraphs") or []
    notes = list(ex.get("notes") or [])
    # Departures go at the head of the numbered notes, not the tail. Notes are
    # trimmed from the end when the panel would overflow, and a concession that
    # silently falls off the sheet defeats the entire point of recording it.
    if departures:
        notes = ["DEPARTURE FROM STANDARD -- " + d for d in departures] + notes
    inner = w - 24
    lines = []
    for p in paras:
        lines.extend(wrap(p, inner, 9.6))
        lines.append("")
    if lines and not lines[-1]:
        lines.pop()
    # Wrap the numbered notes up front too. Guessing their height and hoping is
    # how panels end up with text spilling through the frame.
    note_lines = [wrap(n, inner - 24, 9.2) for n in notes]
    n_note_lines = sum(len(g) for g in note_lines)
    def total(nl, nn):
        return 26 + 18 + 18 + nl * 13 + (18 + nn * 13 if notes else 0) + 12

    h = total(len(lines), n_note_lines)
    if max_h and h > max_h:
        # Trim the prose rather than let it burst the frame or run off the sheet.
        # Notes are numbered obligations and survive; narrative gets cut.
        while lines and total(len(lines), n_note_lines) > max_h:
            lines.pop()
        while note_lines and total(len(lines), sum(len(g) for g in note_lines)) > max_h:
            note_lines.pop()
        n_note_lines = sum(len(g) for g in note_lines)
        h = total(len(lines), n_note_lines)
    o = [panel_frame(x, y, w, h, "NOTES", S, "GA-01")]
    ry = y + 44
    o.append(txt(x + 12, ry, head.upper(), 11, S["ink"], SANS, "start", "bold", 0.8))
    ry += 18
    for ln in lines:
        if ln:
            o.append(txt(x + 12, ry, ln, 9.6, S["ink"], MONO))
        ry += 13
    if notes:
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                 'stroke-width="0.7" opacity="0.6"/>'
                 % (x + 10, ry + 2, x + w - 10, ry + 2, S["ink_soft"]))
        ry += 18
        for i, group in enumerate(note_lines, 1):
            for j, ln in enumerate(group):
                if j == 0:
                    o.append(txt(x + 12, ry, "%d." % i, 9.2, S["accent"], MONO,
                                 "start", "bold"))
                o.append(txt(x + 36, ry, ln, 9.2, S["ink"], MONO))
                ry += 13
    return "".join(o), h


def draw_title_block(x, y, w, h, S, spec, prof=None):
    o = ['<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="none" '
         'stroke="%s" stroke-width="2"/>' % (x, y, w, h, S["ink"])]
    org = spec.get("organisation") or spec.get("organization") or "ENGINEERING DIVISION"
    o.append('<rect x="%.2f" y="%.2f" width="%.2f" height="30" fill="%s" '
             'opacity="0.5"/>' % (x, y, w, S["face_top"]))
    o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
             'stroke-width="1.4"/>' % (x, y + 30, x + w, y + 30, S["ink"]))
    o.append(txt(x + 12, y + 21, org.upper(), 12, S["ink"], SANS, "start", "bold", 2.2))
    o.append(txt(x + w - 12, y + 21, spec.get("classification") or "FOR INTERNAL USE",
                 9, S["ink_soft"], MONO, "end", "bold", 1.0))

    ty = y + 30
    o.append(txt(x + 12, ty + 30, (spec.get("title") or "SYSTEM GENERAL ARRANGEMENT")
                 .upper(), 20, S["ink"], SANS, "start", "bold", 1.4))
    o.append(txt(x + 12, ty + 50, (spec.get("subtitle") or
                                   "ISOMETRIC ARRANGEMENT AND DEPENDENCY DIAGRAM")
                 .upper(), 10.5, S["ink_soft"], SANS, "start", "normal", 1.6))
    gy = ty + 62
    o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
             'stroke-width="1.2"/>' % (x, gy, x + w, gy, S["ink"]))

    cells = [
        ("DRAWING NO.", spec.get("drawing_no") or "GA-0001-01"),
        ("REV", str(spec.get("revision") or "A")),
        ("SCALE", spec.get("scale") or "N.T.S."),
        ("SHEET", spec.get("sheet") or "1 / 1"),
        ("DRAWN", spec.get("drawn_by") or "--"),
        ("CHECKED", spec.get("checked_by") or "--"),
        ("DATE", spec.get("date") or "--"),
        ("STANDARD", prof.version if prof else "NONE"),
    ]
    ncol = 4
    cw = w / float(ncol)
    ch = (y + h - gy) / 2.0
    for i, (k, v) in enumerate(cells):
        cx = x + (i % ncol) * cw
        cy = gy + (i // ncol) * ch
        o.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="none" '
                 'stroke="%s" stroke-width="0.7" opacity="0.75"/>'
                 % (cx, cy, cw, ch, S["ink_soft"]))
        o.append(txt(cx + 8, cy + 13, k, 7.6, S["ink_soft"], MONO, "start", "bold",
                     0.7))
        o.append(txt(cx + 8, cy + ch - 9, clip(str(v).upper(), 15), 11.5, S["ink"], MONO,
                     "start", "bold"))
    return "".join(o)


def draw_matrix(x, y, S, nodes, spec):
    """Dependency matrix: rows are sources, columns are targets, a mark means a
    path exists. An isometric plot is always about 1.73:1, so a squarer drawing
    region always leaves a band of sheet unused at the bottom -- and the honest
    way to use it is with the adjacency the pictorial view cannot state exactly.
    Where two components look adjacent on the model but are not connected, this
    table is what settles it."""
    refs = [n["ref"] for n in nodes]
    idx = {n["id"]: n["ref"] for n in nodes}
    cell = 19.0
    n = len(refs)
    if n == 0 or n > 20:
        return "", 0.0, 0.0
    marks = {}
    for e in (spec.get("edges") or []):
        a, b = idx.get(e.get("from")), idx.get(e.get("to"))
        if a and b:
            marks[(a, b)] = (e.get("kind") or "data")[0].upper()
    w = 34 + n * cell + 12
    h = 26 + 22 + n * cell + 12
    # With few components the panel is narrow, and a right-aligned caption then
    # collides with the panel title. Drop the caption rather than overlap.
    o = [panel_frame(x, y, w, h, "DEPENDENCY MATRIX", S,
                     "FROM / TO" if w >= 250 else None)]
    gx, gy = x + 34, y + 48
    for j, r in enumerate(refs):
        o.append(txt(gx + j * cell + cell / 2.0, gy - 6, r, 8.6, S["ink_soft"],
                     MONO, "middle", "bold"))
    for i, r in enumerate(refs):
        o.append(txt(gx - 7, gy + i * cell + cell / 2.0 + 3.5, r, 8.6,
                     S["ink_soft"], MONO, "end", "bold"))
    o.append('<g stroke="%s" stroke-width="0.6" opacity="0.7" fill="none">'
             % S["ink_faint"])
    for i in range(n + 1):
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                 % (gx, gy + i * cell, gx + n * cell, gy + i * cell))
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                 % (gx + i * cell, gy, gx + i * cell, gy + n * cell))
    o.append('</g>')
    for i, a in enumerate(refs):
        for j, b in enumerate(refs):
            cx = gx + j * cell + cell / 2.0
            cy = gy + i * cell + cell / 2.0
            if i == j:
                o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                         'stroke="%s" stroke-width="0.7" opacity="0.6"/>'
                         % (cx - cell / 2.0, cy + cell / 2.0, cx + cell / 2.0,
                            cy - cell / 2.0, S["ink_faint"]))
            elif (a, b) in marks:
                o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                         'fill="%s" opacity="0.20"/>'
                         % (cx - cell / 2.0, cy - cell / 2.0, cell, cell,
                            S["accent"]))
                o.append(txt(cx, cy + 3.5, marks[(a, b)], 9, S["ink"], MONO,
                             "middle", "bold"))
    return "".join(o), w, h


def draw_revisions(x, y, w, S, spec):
    rows = spec.get("revisions") or [
        {"rev": str(spec.get("revision") or "A"),
         "date": spec.get("date") or "--",
         "description": "Issued for review",
         "by": spec.get("drawn_by") or "--"},
    ]
    rows = rows[:8]
    h = 26 + 20 + len(rows) * 17 + 10
    o = [panel_frame(x, y, w, h, "REVISION HISTORY", S, "LATEST AT TOP")]
    cols = [(x + 12, "REV", "start"), (x + 52, "DATE", "start"),
            (x + 148, "DESCRIPTION", "start"), (x + w - 12, "BY", "end")]
    ry = y + 42
    for (cx, lab, an) in cols:
        o.append(txt(cx, ry, lab, 8.2, S["ink_soft"], MONO, an, "bold"))
    ry += 5
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
             'stroke-width="0.7" opacity="0.6"/>' % (x + 10, ry, x + w - 10, ry,
                                                    S["ink_soft"]))
    ry += 14
    for r in rows:
        o.append(txt(x + 12, ry, str(r.get("rev", "")).upper(), 9.6, S["ink"], MONO,
                     "start", "bold"))
        o.append(txt(x + 52, ry, str(r.get("date", "")), 9.2, S["ink_soft"], MONO))
        o.append(txt(x + 148, ry, clip(r.get("description", ""), 38), 9.2, S["ink"],
                     MONO))
        o.append(txt(x + w - 12, ry, clip(r.get("by", ""), 10), 9.2, S["ink_soft"],
                     MONO, "end"))
        ry += 17
    return "".join(o), h


def draw_datum_rose(x, y, S, skin_label):
    """Axis rose plus skin caption -- the orientation key for the projection."""
    P = G.Iso(tile=42, unit_height=42 * 30.0 / 54.0, ox=x, oy=y)
    o = ['<g stroke="%s" fill="none" stroke-width="1.4">' % S["ink"]]
    for (lx, ly, lz) in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        a = P.pt(0, 0, 0)
        b = P.pt(lx, ly, lz)
        o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
                 'marker-end="url(#ar-ink)"/>' % (a + b))
    o.append('</g>')
    for (lx, ly, lz, lab) in ((1.24, 0, 0, "X"), (0, 1.24, 0, "Y"), (0, 0, 1.3, "Z")):
        p = P.pt(lx, ly, lz)
        o.append(txt(p[0], p[1] + 4, lab, 11, S["ink"], SANS, "middle", "bold"))
    o.append(txt(x - 46, y + 40, "PROJECTION DATUM", 8.4, S["ink_soft"], MONO,
                 "start", "bold", 0.8))
    o.append(txt(x - 46, y + 52, "ISO 30 DEG  /  " + skin_label, 8.4,
                 S["ink_faint"], MONO))
    return "".join(o)


def draw_scale_bar(x, y, w, S):
    o = [txt(x, y - 8, "GRID SCALE (UNITS)", 8.4, S["ink_soft"], MONO, "start",
             "bold", 0.8)]
    seg = w / 8.0
    for i in range(8):
        o.append('<rect x="%.2f" y="%.2f" width="%.2f" height="7" fill="%s" '
                 'stroke="%s" stroke-width="0.7"/>'
                 % (x + i * seg, y, seg, S["ink"] if i % 2 == 0 else S["paper"],
                    S["ink"]))
    for i in (0, 4, 8):
        o.append(txt(x + i * seg, y + 19, str(i), 8.2, S["ink_soft"], MONO, "middle"))
    return "".join(o)


# ---------------------------------------------------------------------------
# aging
# ---------------------------------------------------------------------------

def draw_aging(S, seed):
    rnd = random.Random(seed)
    o = []
    if S["grain"] > 0:
        o.append('<rect x="0" y="0" width="%.0f" height="%.0f" filter="url(#grain)" '
                 'opacity="%.3f"/>' % (SHEET_W, SHEET_H, S["grain"] * 0.55))
        o.append('<rect x="0" y="0" width="%.0f" height="%.0f" filter="url(#mottle)" '
                 'opacity="%.3f"/>' % (SHEET_W, SHEET_H, S["grain"] * 0.6))
    # fold creases -- a sheet this size was folded to fit a flat file
    for fx in (SHEET_W / 3.0, SHEET_W * 2.0 / 3.0):
        o.append('<line x1="%.1f" y1="0" x2="%.1f" y2="%.0f" stroke="%s" '
                 'stroke-width="1.1" opacity="0.13"/>' % (fx, fx, SHEET_H,
                                                          S["ink_faint"]))
    o.append('<line x1="0" y1="%.1f" x2="%.0f" y2="%.1f" stroke="%s" '
             'stroke-width="1.1" opacity="0.11"/>'
             % (SHEET_H / 2.0, SHEET_W, SHEET_H / 2.0, S["ink_faint"]))
    # foxing / stains
    for _ in range(5):
        cx = rnd.uniform(60, SHEET_W - 60)
        cy = rnd.uniform(60, SHEET_H - 60)
        r = rnd.uniform(26, 96)
        o.append('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" '
                 'opacity="%.3f" filter="url(#soft)"/>'
                 % (cx, cy, r, r * rnd.uniform(0.55, 1.0), S["ink_faint"],
                    0.05 + 0.05 * S["grain"] * 3))
    o.append('<rect x="0" y="0" width="%.0f" height="%.0f" fill="url(#vign)"/>'
             % (SHEET_W, SHEET_H))
    return "".join(o)


def draw_frame(S, spec):
    o = ['<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
         'stroke="%s" stroke-width="2.6"/>'
         % (TRIM, TRIM, SHEET_W - 2 * TRIM, SHEET_H - 2 * TRIM, S["ink"])]
    i = TRIM + FRAME_IN
    o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
             'stroke="%s" stroke-width="1.1"/>'
             % (i, i, SHEET_W - 2 * i, SHEET_H - 2 * i, S["ink"]))
    # zone markings, as on any drawing sheet, so callers can cite "detail at C4"
    nx, ny = 12, 8
    iw, ih = SHEET_W - 2 * i, SHEET_H - 2 * i
    for k in range(nx):
        cx = i + iw * (k + 0.5) / nx
        for yy in (TRIM + FRAME_IN / 2.0 + 1, SHEET_H - TRIM - FRAME_IN / 2.0 + 4):
            o.append(txt(cx, yy, str(k + 1), 8.6, S["ink_soft"], MONO, "middle",
                         "bold"))
        if k:
            xx = i + iw * k / nx
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="0.8"/>' % (xx, TRIM, xx, i, S["ink_soft"]))
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="0.8"/>' % (xx, SHEET_H - i, xx, SHEET_H - TRIM,
                                               S["ink_soft"]))
    for k in range(ny):
        cy = i + ih * (k + 0.5) / ny + 3
        for xx in (TRIM + FRAME_IN / 2.0, SHEET_W - TRIM - FRAME_IN / 2.0):
            o.append(txt(xx, cy, REFS[k], 8.6, S["ink_soft"], MONO, "middle", "bold"))
        if k:
            yy = i + ih * k / ny
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="0.8"/>' % (TRIM, yy, i, yy, S["ink_soft"]))
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="0.8"/>' % (SHEET_W - i, yy, SHEET_W - TRIM, yy,
                                               S["ink_soft"]))
    return "".join(o)


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def render(spec):
    S = SK.get(spec.get("skin"))
    nodes, prof, departures = normalise(spec)
    cols, rows = extents(nodes)

    x0 = TRIM + FRAME_IN + PAD
    y0 = TRIM + FRAME_IN + PAD
    x1 = SHEET_W - TRIM - FRAME_IN - PAD
    y1 = SHEET_H - TRIM - FRAME_IN - PAD
    px = x1 - PANEL_W
    # The drawing region excludes the panel column and the lower strip. The strip
    # exists because of the projection: a rectangular plot in 30-degree isometric
    # always lands on the sheet at about 1.73:1, so fitting it into a squarer
    # region leaves roughly a third of the height unused. Rather than inflate the
    # model to hide that, give the band over to schedules.
    strip_h = 268.0
    draw_region = (x0, y0 + 38, px - GUTTER, y1 - strip_h - 18)

    P = fit(nodes, cols, rows, draw_region)
    mid_x = (draw_region[0] + draw_region[2]) / 2.0

    used_kinds = []
    for e in (spec.get("edges") or []):
        k = (e.get("kind") or "data").lower()
        if k in EDGE_STYLES and k not in used_kinds:
            used_kinds.append(k)

    conduits, payloads = build_conduits(spec, nodes, P, cols, rows, S)

    # depth-sorted model: conduit segments and solids interleaved so a nearer
    # building occludes a conduit behind it and vice versa
    items = list(conduits)
    for n in nodes:
        near = (n["x"] + n["w"]) + (n["y"] + n["d"])
        node_svg = '<g class="bp-node" data-id="%s">' % esc(n["id"])
        node_svg += shadow(P, n, S)
        node_svg += emit_prims(
            G.build(n["form"], P, n["x"], n["y"], n["w"], n["d"], n["h"]),
            S, n["accent"])
        node_svg += '</g>'
        items.append((near, node_svg))
    items.sort(key=lambda t: t[0])

    obs = seed_obstacles(P, nodes, draw_region)
    model = [draw_ground(P, cols, rows, S)]
    model.append("".join(s for (_k, s) in items))
    model.append(draw_dimensions(P, cols, rows, S, spec))
    # Callouts claim space before payload tags: a component's designation is the
    # more important of the two, so it gets the clear air above the massing and
    # the payload tags route around it.
    callouts = emit_callouts(P, nodes, S, mid_x, obs)
    model.append(emit_payload_labels(payloads, S, obs))
    model.append(callouts)
    model_svg = "".join(model)

    # panels
    panels = []
    py = y0
    leg, hh = draw_legend(px, py, PANEL_W, S, nodes, used_kinds, spec, prof)
    panels.append(leg)
    py += hh + 14
    idx, hh = draw_index(px, py, PANEL_W, S, nodes)
    panels.append(idx)
    py += hh + 14
    tb_h = 168.0
    exp, hh = draw_explainer(px, py, PANEL_W, S, spec,
                             max_h=max(90.0, (y1 - tb_h - 16) - py),
                             departures=departures)
    panels.append(exp)

    tb_w = PANEL_W
    panels.append(draw_title_block(x1 - tb_w, y1 - tb_h, tb_w, tb_h, S, spec, prof))

    # lower strip: dependency matrix, revision history, projection datum, scale
    sy = y1 - strip_h
    mtx, mw, mh = draw_matrix(x0, sy, S, nodes, spec)
    panels.append(mtx)
    rx = x0 + (mw + 20 if mw else 0)
    rev_w = min(470.0, max(320.0, px - GUTTER - rx - 250.0))
    rev, _rh = draw_revisions(rx, sy, rev_w, S, spec)
    panels.append(rev)
    dr_x = rx + rev_w + 92
    panels.append(draw_datum_rose(dr_x, sy + 74, S, S["label"]))
    panels.append(draw_scale_bar(dr_x - 46, sy + 170, 200, S))
    panels.append(txt(x0, y0 + 8, (spec.get("sheet_heading") or
                                   "ISOMETRIC GENERAL ARRANGEMENT").upper(),
                      15, S["ink"], SANS, "start", "bold", 3.0))
    panels.append(txt(x0, y0 + 24, (spec.get("sheet_subheading") or
                                    "DEPENDENCY AND PAYLOAD ROUTING -- ALL TIERS")
                      .upper(), 9.4, S["ink_soft"], MONO, "start", "normal", 1.2))

    seed = int(hashlib.md5((spec.get("title") or "x").encode()).hexdigest()[:8], 16)

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<svg xmlns="http://www.w3.org/2000/svg" '
               'xmlns:xlink="http://www.w3.org/1999/xlink" '
               'viewBox="0 0 %.0f %.0f" width="%.0f" height="%.0f">'
               % (SHEET_W, SHEET_H, SHEET_W, SHEET_H))
    out.append('<title>%s</title>' % esc(spec.get("title") or "System arrangement"))
    out.append(build_defs(S))
    out.append('<rect x="0" y="0" width="%.0f" height="%.0f" fill="%s"'
               ' pointer-events="none"/>' % (SHEET_W, SHEET_H, S["paper"]))
    out.append('<g id="ink" stroke-linejoin="round">%s%s</g>'
               % (model_svg, "".join(panels)))
    if S["bleed"] > 0:
        # a blurred copy of the linework under the crisp copy: ink soaking into
        # paper. Cheap, and it is most of what separates a print from a plot.
        out.append('<use xlink:href="#ink" filter="url(#bleed)" opacity="%.2f"'
                   ' pointer-events="none"/>' % (S["bleed"] * 0.42))
        out.append('<use xlink:href="#ink" pointer-events="none"/>')
    out.append('<g pointer-events="none">%s</g>' % draw_frame(S, spec))
    out.append('<g pointer-events="none">%s</g>' % draw_aging(S, seed))
    out.append('</svg>')
    return "".join(out)


def build_manifest(spec):
    nodes, prof, _ = normalise(spec)
    by_id = {n["id"]: n for n in nodes}
    edges = spec.get("edges") or []
    explainer = spec.get("explainer") or {}
    mn = []
    for n in nodes:
        incoming = [e for e in edges if e.get("to") == n["id"] and e.get("from") in by_id]
        outgoing = [e for e in edges if e.get("from") == n["id"] and e.get("to") in by_id]
        mn.append({
            "id": n["id"], "ref": n["ref"], "label": n["label"],
            "kind": n.get("kind") or n["form"], "form": n["form"],
            "tier": n["tier"], "spec": n["spec"],
            "criticality": n.get("criticality"),
            "scale": n.get("scale", 2),
            "height": round(n["h"], 2),
            "footprint": [n["w"], n["d"]],
            "accent": n["accent"],
            "incoming": [{"from": e["from"],
                          "from_ref": by_id[e["from"]]["ref"],
                          "from_label": by_id[e["from"]]["label"],
                          "kind": e.get("kind", "data"),
                          "payload": e.get("payload", "")}
                         for e in incoming],
            "outgoing": [{"to": e["to"],
                          "to_ref": by_id[e["to"]]["ref"],
                          "to_label": by_id[e["to"]]["label"],
                          "kind": e.get("kind", "data"),
                          "payload": e.get("payload", "")}
                         for e in outgoing],
        })
    me = []
    for e in edges:
        if e.get("from") in by_id and e.get("to") in by_id:
            me.append({
                "from": e["from"], "to": e["to"],
                "from_ref": by_id[e["from"]]["ref"],
                "to_ref": by_id[e["to"]]["ref"],
                "from_label": by_id[e["from"]]["label"],
                "to_label": by_id[e["to"]]["label"],
                "kind": e.get("kind", "data"),
                "payload": e.get("payload", ""),
                "accent": bool(e.get("accent")),
            })
    return {
        "title": spec.get("title", "System Arrangement"),
        "skin": spec.get("skin", "diazo"),
        "nodes": mn, "edges": me,
        "explainer": explainer,
    }


EDGE_KIND_LABELS = {
    "data": "Data path",
    "control": "Control path",
    "event": "Event path",
    "bulk": "Bulk transfer",
    "telemetry": "Telemetry",
    "secure": "Protected channel",
}


def render_html(svg_string, manifest):
    import re as _re
    S = SK.get(manifest["skin"])
    svg_body = svg_string
    if svg_body.startswith("<?xml"):
        svg_body = svg_body[svg_body.index("?>") + 2:].lstrip()
    svg_body = _re.sub(r'(<svg\b[^>]*?)\s+width="[^"]*"', r'\1', svg_body)
    svg_body = _re.sub(r'(<svg\b[^>]*?)\s+height="[^"]*"', r'\1', svg_body)
    manifest_json = json.dumps(manifest, indent=None, ensure_ascii=True)
    skin_json = json.dumps(S, indent=None, ensure_ascii=True)
    title = esc(manifest.get("title", "System Arrangement"))

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --paper:%(paper)s; --paper-edge:%(paper_edge)s;
  --ink:%(ink)s; --ink-soft:%(ink_soft)s; --ink-faint:%(ink_faint)s;
  --accent:%(accent)s; --accent2:%(accent2)s;
  --face-top:%(face_top)s; --face-right:%(face_right)s; --face-left:%(face_left)s;
}
html,body{height:100%%;overflow:hidden;font-family:'Courier New',Courier,monospace}
body{display:flex;background:var(--paper-edge);color:var(--ink)}
.bp-container{flex:1;overflow:auto;display:flex;align-items:center;justify-content:center;
  position:relative;min-width:0;height:100vh}
.bp-container svg{width:100%%;height:100%%;display:block}
.bp-node,.bp-callout{cursor:pointer}
.bp-edge{cursor:pointer}
.bp-node:hover,.bp-callout:hover{filter:brightness(1.15)}
.bp-edge:hover{filter:brightness(1.2)}
.bp-node.selected,.bp-callout.selected{filter:drop-shadow(0 0 8px var(--accent))}
.bp-edge.selected{filter:drop-shadow(0 0 6px var(--accent))}
.detail-panel{
  width:380px;min-width:380px;max-width:380px;
  background:var(--paper);border-left:2px solid var(--ink);
  overflow-y:auto;display:flex;flex-direction:column;
  transition:width 0.2s;
}
.panel-header{
  background:var(--face-top);border-bottom:2px solid var(--ink);
  padding:12px 16px;font-size:13px;font-weight:bold;letter-spacing:2px;
  color:var(--ink);display:flex;align-items:center;justify-content:space-between;
}
.panel-empty{
  flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:40px 24px;text-align:center;opacity:0.7;
}
.panel-empty h3{font-size:13px;letter-spacing:2px;margin-bottom:16px;color:var(--ink-soft)}
.panel-empty p{font-size:10px;color:var(--ink-faint);line-height:1.6;max-width:260px}
.panel-content{display:none;flex:1;overflow-y:auto;padding:0}
.detail-ref{
  display:flex;align-items:center;gap:14px;
  padding:18px 16px 14px;border-bottom:1px solid var(--ink-faint);
}
.ref-badge{
  width:36px;height:36px;border-radius:50%%;border:2px solid var(--ink);
  display:flex;align-items:center;justify-content:center;
  font-size:16px;font-weight:bold;flex-shrink:0;
}
.ref-badge.accent{border-color:var(--accent);color:var(--accent)}
.ref-label{font-size:14px;font-weight:bold;letter-spacing:0.8px;text-transform:uppercase}
.ref-sub{font-size:9px;color:var(--ink-soft);margin-top:3px}
.detail-section{padding:14px 16px;border-bottom:1px solid var(--ink-faint)}
.detail-section:last-child{border-bottom:none}
.section-title{
  font-size:9px;font-weight:bold;letter-spacing:1.5px;
  color:var(--ink-soft);margin-bottom:10px;
}
.field-row{display:flex;justify-content:space-between;margin-bottom:6px;font-size:10px}
.field-key{color:var(--ink-soft)}
.field-val{color:var(--ink);font-weight:bold;text-align:right}
.spec-line{font-size:10px;color:var(--ink);margin-bottom:5px;padding-left:18px;
  position:relative}
.spec-line::before{content:attr(data-num) ".";position:absolute;left:0;
  color:var(--accent);font-weight:bold}
.conn-item{margin-bottom:10px}
.conn-header{font-size:10px;display:flex;align-items:center;gap:6px}
.conn-arrow{color:var(--accent);font-weight:bold;font-size:12px}
.conn-ref{font-weight:bold;min-width:16px}
.conn-label{color:var(--ink)}
.conn-detail{font-size:9px;color:var(--ink-soft);padding-left:22px;margin-top:2px}
.conn-kind{
  display:inline-block;padding:1px 5px;font-size:8px;letter-spacing:0.5px;
  border:1px solid var(--ink-faint);border-radius:2px;margin-right:4px;
  color:var(--ink-soft);
}
.edge-detail-header{
  padding:18px 16px 14px;border-bottom:1px solid var(--ink-faint);
}
.edge-endpoints{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.edge-ep{text-align:center}
.edge-ep .ref-badge{width:30px;height:30px;font-size:13px;margin:0 auto 4px}
.edge-ep-label{font-size:9px;color:var(--ink-soft);max-width:100px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.edge-arrow-line{flex:1;height:2px;background:var(--ink-soft);position:relative;
  min-width:30px}
.edge-arrow-line::after{content:"";position:absolute;right:-1px;top:-4px;
  border:5px solid transparent;border-left:7px solid var(--ink-soft)}
.edge-payload-tag{
  text-align:center;margin-top:8px;font-size:11px;font-weight:bold;
  color:var(--ink);letter-spacing:0.5px;
}
@media(max-width:900px){
  .detail-panel{position:absolute;right:0;top:0;bottom:0;z-index:10;
    box-shadow:-4px 0 20px rgba(0,0,0,0.3)}
  .detail-panel.collapsed{width:0;min-width:0;border:none;overflow:hidden}
}
</style>
</head>
<body>
<div class="bp-container" id="bp-container">
%(svg)s
</div>
<div class="detail-panel" id="detail-panel">
  <div class="panel-header">
    <span>COMPONENT INSPECTOR</span>
    <span id="panel-close" style="cursor:pointer;font-size:16px;opacity:0.6"
      title="Clear selection">&times;</span>
  </div>
  <div class="panel-empty" id="panel-empty">
    <h3>SELECT A COMPONENT</h3>
    <p>Click any building or conduit on the drawing to inspect its specification,
    classification and connections.</p>
  </div>
  <div class="panel-content" id="panel-content"></div>
</div>
<script>
(function(){
var M = %(manifest)s;
var S = %(skin)s;
var byId = {};
M.nodes.forEach(function(n){ byId[n.id] = n; });

var EKIND = %(edge_kinds)s;

function clearSel(){
  document.querySelectorAll('.selected').forEach(function(el){
    el.classList.remove('selected');
  });
}

function selectNode(id){
  clearSel();
  document.querySelectorAll('.bp-node[data-id="'+id+'"]').forEach(function(el){
    el.classList.add('selected');
  });
  document.querySelectorAll('.bp-callout[data-id="'+id+'"]').forEach(function(el){
    el.classList.add('selected');
  });
  showNodeDetail(byId[id]);
}

function selectEdge(from, to){
  clearSel();
  document.querySelectorAll('.bp-edge[data-from="'+from+'"][data-to="'+to+'"]')
    .forEach(function(el){ el.classList.add('selected'); });
  var edge = M.edges.find(function(e){ return e.from===from && e.to===to; });
  if(edge) showEdgeDetail(edge);
}

function showNodeDetail(n){
  var pc = document.getElementById('panel-content');
  var pe = document.getElementById('panel-empty');
  pe.style.display = 'none';
  pc.style.display = 'block';
  var h = '';
  h += '<div class="detail-ref">';
  h += '<div class="ref-badge'+(n.accent?' accent':'')+'">'+esc(n.ref)+'</div>';
  h += '<div><div class="ref-label">'+esc(n.label)+'</div>';
  h += '<div class="ref-sub">'+esc(n.form.toUpperCase())+' \\u00b7 '+esc(n.tier.toUpperCase())+'</div>';
  h += '</div></div>';
  h += '<div class="detail-section"><div class="section-title">CLASSIFICATION</div>';
  h += field('Kind', n.kind);
  h += field('Form', n.form);
  h += field('Tier', n.tier);
  h += field('Height', n.height+' units');
  h += field('Footprint', n.footprint[0]+' \\u00d7 '+n.footprint[1]);
  if(n.criticality) h += field('Criticality', n.criticality+' / 3');
  h += field('Scale', (n.scale||2)+' / 3');
  if(n.accent) h += field('Accent', 'Critical path');
  h += '</div>';
  if(n.spec && n.spec.length){
    h += '<div class="detail-section"><div class="section-title">SPECIFICATION</div>';
    n.spec.forEach(function(s,i){
      h += '<div class="spec-line" data-num="'+(i+1)+'">'+esc(s)+'</div>';
    });
    h += '</div>';
  }
  var conns = n.outgoing.concat(n.incoming.map(function(c){
    return {dir:'in', from:c.from, from_ref:c.from_ref, from_label:c.from_label,
            kind:c.kind, payload:c.payload};
  }));
  if(n.outgoing.length || n.incoming.length){
    h += '<div class="detail-section"><div class="section-title">CONNECTIONS</div>';
    n.outgoing.forEach(function(c){
      h += connRow('\\u25b6', c.to_ref || '?', c.to_label || c.to, c.kind, c.payload,
                    n.id, c.to);
    });
    n.incoming.forEach(function(c){
      h += connRow('\\u25c0', c.from_ref || '?', c.from_label || c.from, c.kind, c.payload,
                    c.from, n.id);
    });
    h += '</div>';
  }
  pc.innerHTML = h;
  pc.querySelectorAll('.conn-item[data-from][data-to]').forEach(function(el){
    el.style.cursor = 'pointer';
    el.addEventListener('click', function(ev){
      ev.stopPropagation();
      selectEdge(el.getAttribute('data-from'), el.getAttribute('data-to'));
    });
  });
}

function showEdgeDetail(e){
  var pc = document.getElementById('panel-content');
  var pe = document.getElementById('panel-empty');
  pe.style.display = 'none';
  pc.style.display = 'block';
  var h = '<div class="edge-detail-header">';
  h += '<div class="edge-endpoints">';
  h += '<div class="edge-ep"><div class="ref-badge">'+esc(e.from_ref)+'</div>';
  h += '<div class="edge-ep-label">'+esc(e.from_label)+'</div></div>';
  h += '<div class="edge-arrow-line"></div>';
  h += '<div class="edge-ep"><div class="ref-badge">'+esc(e.to_ref)+'</div>';
  h += '<div class="edge-ep-label">'+esc(e.to_label)+'</div></div>';
  h += '</div>';
  if(e.payload) h += '<div class="edge-payload-tag">'+esc(e.payload)+'</div>';
  h += '</div>';
  h += '<div class="detail-section"><div class="section-title">PATH CLASSIFICATION</div>';
  h += field('Kind', e.kind);
  h += field('Description', EKIND[e.kind] || e.kind);
  if(e.payload) h += field('Payload', e.payload);
  if(e.accent) h += field('Critical path', 'Yes');
  h += '</div>';
  // source node summary
  var src = byId[e.from], tgt = byId[e.to];
  if(src){
    h += '<div class="detail-section"><div class="section-title">SOURCE ('+esc(src.ref)+')</div>';
    h += '<div class="node-link" data-goto="'+esc(src.id)+'" style="font-size:11px;font-weight:bold;margin-bottom:6px;cursor:pointer">'+esc(src.label)+'</div>';
    h += field('Kind', src.kind); h += field('Tier', src.tier);
    h += '</div>';
  }
  if(tgt){
    h += '<div class="detail-section"><div class="section-title">TARGET ('+esc(tgt.ref)+')</div>';
    h += '<div class="node-link" data-goto="'+esc(tgt.id)+'" style="font-size:11px;font-weight:bold;margin-bottom:6px;cursor:pointer">'+esc(tgt.label)+'</div>';
    h += field('Kind', tgt.kind); h += field('Tier', tgt.tier);
    h += '</div>';
  }
  pc.innerHTML = h;
  pc.querySelectorAll('.node-link[data-goto]').forEach(function(el){
    el.addEventListener('click', function(ev){
      ev.stopPropagation();
      selectNode(el.getAttribute('data-goto'));
    });
  });
}

function field(k, v){
  return '<div class="field-row"><span class="field-key">'+esc(k)
    +'</span><span class="field-val">'+esc(String(v))+'</span></div>';
}
function connRow(arrow, ref, label, kind, payload, fromId, toId){
  var h = '<div class="conn-item" data-from="'+esc(fromId)+'" data-to="'+esc(toId)+'">';
  h += '<div class="conn-header"><span class="conn-arrow">'+arrow+'</span>';
  h += '<span class="conn-ref">'+esc(ref)+'</span>';
  h += '<span class="conn-label">'+esc(label)+'</span></div>';
  h += '<div class="conn-detail"><span class="conn-kind">'+esc(kind.toUpperCase())+'</span>';
  if(payload) h += esc(payload);
  h += '</div></div>';
  return h;
}
function esc(s){
  var d = document.createElement('span');
  d.textContent = s; return d.innerHTML;
}

// event delegation — handles both original SVG groups and hit-overlay elements
document.addEventListener('click', function(ev){
  var t = ev.target;
  var node = t.closest('.bp-node, .bp-callout, .bp-hit-node');
  if(node){
    var id = node.getAttribute('data-id');
    if(id && byId[id]){ selectNode(id); return; }
  }
  var edge = t.closest('.bp-edge');
  if(!edge && (t.classList.contains('bp-hit-edge') || t.closest('.bp-hit-edge'))) edge = t.classList.contains('bp-hit-edge') ? t : t.closest('.bp-hit-edge');
  if(edge){
    var f = edge.getAttribute('data-from'), t2 = edge.getAttribute('data-to');
    if(f && t2){ selectEdge(f, t2); return; }
  }
  if(!ev.target.closest('.detail-panel')){
    clearSel();
    document.getElementById('panel-empty').style.display = '';
    document.getElementById('panel-content').style.display = 'none';
  }
});
document.getElementById('panel-close').addEventListener('click', function(){
  clearSel();
  document.getElementById('panel-empty').style.display = '';
  document.getElementById('panel-content').style.display = 'none';
});
// build a transparent hit-target overlay on top of all SVG layers
(function(){
  var svg = document.querySelector('.bp-container svg');
  if(!svg) return;
  var ns = 'http://www.w3.org/2000/svg';
  var overlay = document.createElementNS(ns, 'g');
  overlay.setAttribute('id', 'bp-hit-overlay');
  // edge hit areas first (underneath) — wider invisible strokes
  document.querySelectorAll('.bp-edge').forEach(function(g){
    g.querySelectorAll('line, path').forEach(function(el){
      var cl = el.cloneNode(false);
      cl.setAttribute('stroke', 'transparent');
      cl.setAttribute('stroke-width', '14');
      cl.setAttribute('pointer-events', 'stroke');
      cl.removeAttribute('stroke-dasharray');
      cl.removeAttribute('opacity');
      cl.removeAttribute('filter');
      cl.setAttribute('class', 'bp-hit bp-hit-edge');
      cl.setAttribute('data-from', g.getAttribute('data-from'));
      cl.setAttribute('data-to', g.getAttribute('data-to'));
      cl.style.cursor = 'pointer';
      overlay.appendChild(cl);
    });
  });
  // node hit areas on top — clone actual geometry for pixel-accurate targets
  document.querySelectorAll('.bp-node').forEach(function(g){
    var id = g.getAttribute('data-id');
    var wrap = document.createElementNS(ns, 'g');
    wrap.setAttribute('class', 'bp-hit bp-hit-node');
    wrap.setAttribute('data-id', id);
    wrap.style.cursor = 'pointer';
    g.querySelectorAll('polygon, path, ellipse').forEach(function(el){
      var cl = el.cloneNode(false);
      cl.setAttribute('fill', 'transparent');
      cl.setAttribute('stroke', 'transparent');
      cl.setAttribute('stroke-width', '4');
      cl.setAttribute('pointer-events', 'all');
      cl.removeAttribute('opacity');
      cl.removeAttribute('filter');
      wrap.appendChild(cl);
    });
    if(wrap.childNodes.length) overlay.appendChild(wrap);
  });
  svg.appendChild(overlay);
})();
})();
</script>
</body>
</html>""" % {
        "title": title,
        "paper": S["paper"], "paper_edge": S["paper_edge"],
        "ink": S["ink"], "ink_soft": S["ink_soft"], "ink_faint": S["ink_faint"],
        "accent": S["accent"], "accent2": S["accent2"],
        "face_top": S["face_top"], "face_right": S["face_right"],
        "face_left": S["face_left"],
        "svg": svg_body,
        "manifest": manifest_json,
        "skin": skin_json,
        "edge_kinds": json.dumps(EDGE_KIND_LABELS),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--skin", default=None,
                    help="override spec skin: " + ", ".join(sorted(SK.SKINS)))
    ap.add_argument("--pdf", default=None, help="also write a PDF at this path")
    ap.add_argument("--html", default=None,
                    help="write an interactive HTML page at this path")
    ap.add_argument("--profile", default=None,
                    help="symbol profile: software, plant, a path, or off")
    ap.add_argument("--enforce", default=None,
                    choices=["record", "warn", "strict", "off"],
                    help="how to treat departures (default: record on the sheet)")
    a = ap.parse_args()

    with open(a.spec) as fh:
        spec = json.load(fh)
    if a.skin:
        spec["skin"] = a.skin
    if a.profile:
        spec["profile"] = a.profile
    if a.enforce:
        spec["profile_enforcement"] = a.enforce
    svg = render(spec)
    out = a.out or os.path.splitext(a.spec)[0] + ".svg"
    with open(out, "w") as fh:
        fh.write(svg)
    print("wrote %s (%.0f KB)" % (out, len(svg) / 1024.0))

    if a.html:
        manifest = build_manifest(spec)
        html = render_html(svg, manifest)
        with open(a.html, "w") as fh:
            fh.write(html)
        print("wrote %s (%.0f KB)" % (a.html, len(html) / 1024.0))

    if a.pdf:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        import svg_to_pdf
        svg_to_pdf.convert(out, a.pdf)
        print("wrote %s" % a.pdf)


if __name__ == "__main__":
    main()
