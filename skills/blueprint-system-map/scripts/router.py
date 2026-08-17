"""Orthogonal conduit router for the ground plane.

Why route at all instead of drawing straight lines between components? Because a
straight line from A to B in isometric space reads as a line floating over the
model, not as a path through it. Real plant drawings run services in orthogonal
channels between foundations, and that single convention is most of what makes
an isometric map look surveyed rather than sketched.

The router works on a half-unit lattice over the ground grid. Footprints are
blocked (including their boundary, so conduits keep half a unit of clearance
from every wall), and Dijkstra finds a least-cost path where cost = distance
+ a turn penalty + a congestion penalty on lattice edges already used by
earlier routes. The turn penalty produces long straight runs with few corners.
The congestion penalty makes parallel routes fan out into separate channels
instead of stacking on top of each other, which is what stops the drawing from
turning into one thick illegible trunk.
"""

import heapq

STEP = 0.5           # lattice pitch, in grid units
TURN_COST = 1.35     # charged once per direction change
REUSE_COST = 2.20    # charged per already-used lattice edge
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Router:
    def __init__(self, cols, rows, footprints, margin=1):
        """footprints: list of (node_id, x, y, w, d) in grid units."""
        self.ni = int(round((cols + 2 * margin) / STEP)) + 1
        self.nj = int(round((rows + 2 * margin) / STEP)) + 1
        self.off = margin
        self.blocked = set()
        self.used = {}
        self.side_use = {}
        for (_nid, x, y, w, d) in footprints:
            i0 = self._idx(x)
            i1 = self._idx(x + w)
            j0 = self._idx(y)
            j1 = self._idx(y + d)
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    self.blocked.add((i, j))

    # -- lattice index <-> grid coordinate -------------------------------
    def _idx(self, v):
        return int(round((v + self.off) / STEP))

    def _coord(self, i):
        return i * STEP - self.off

    def _ok(self, i, j):
        return 0 <= i < self.ni and 0 <= j < self.nj

    # -- anchors ---------------------------------------------------------
    def anchor(self, node, toward):
        """Pick the exit point on `node`'s footprint facing `toward`.

        Returns (side, anchor_grid_pt, entry_grid_pt). `side` is one of
        '+x' '-x' '+y' '-y' and tells the renderer whether the wall is visible
        (only +x and +y are), which decides if a riser gets drawn.
        """
        x, y, w, d = node["x"], node["y"], node["w"], node["d"]
        cx, cy = x + w / 2.0, y + d / 2.0
        tx, ty = toward
        dx, dy = tx - cx, ty - cy
        if abs(dx) >= abs(dy):
            side = "+x" if dx >= 0 else "-x"
        else:
            side = "+y" if dy >= 0 else "-y"

        # Spread multiple conduits leaving the same wall along that wall.
        k = self.side_use.get((node["id"], side), 0)
        self.side_use[(node["id"], side)] = k + 1
        shift = ((k + 1) // 2) * STEP * (1 if k % 2 == 0 else -1)

        if side in ("+x", "-x"):
            span = d
            base = cy + shift
            base = min(max(base, y + STEP), y + span - STEP) if span > 2 * STEP else cy
            base = round(base / STEP) * STEP
            ax = x + w if side == "+x" else x
            a = (ax, base)
            e = (ax + STEP, base) if side == "+x" else (ax - STEP, base)
        else:
            span = w
            base = cx + shift
            base = min(max(base, x + STEP), x + span - STEP) if span > 2 * STEP else cx
            base = round(base / STEP) * STEP
            ay = y + d if side == "+y" else y
            a = (base, ay)
            e = (base, ay + STEP) if side == "+y" else (base, ay - STEP)
        return side, a, e

    # -- routing ---------------------------------------------------------
    def route(self, start, goal):
        """Least-cost orthogonal path between two grid points.

        Falls back to a simple L-bend if no path exists, so a crowded drawing
        still renders rather than failing.
        """
        s = (self._idx(start[0]), self._idx(start[1]))
        g = (self._idx(goal[0]), self._idx(goal[1]))
        free = set([s, g])
        if not (self._ok(*s) and self._ok(*g)):
            return self._elbow(start, goal)

        best = {}
        pq = [(0.0, s, None)]
        prev = {}
        found = False
        while pq:
            cost, cur, dirn = heapq.heappop(pq)
            key = (cur, dirn)
            if key in best and best[key] <= cost:
                continue
            best[key] = cost
            if cur == g:
                found = True
                gkey = key
                break
            for nd in DIRS:
                nxt = (cur[0] + nd[0], cur[1] + nd[1])
                if not self._ok(*nxt):
                    continue
                if nxt in self.blocked and nxt not in free:
                    continue
                c = cost + STEP
                if dirn is not None and nd != dirn:
                    c += TURN_COST
                c += REUSE_COST * self.used.get(self._ekey(cur, nxt), 0)
                nkey = (nxt, nd)
                if nkey not in best or best[nkey] > c:
                    prev[nkey] = (cur, dirn)
                    heapq.heappush(pq, (c, nxt, nd))
        if not found:
            return self._elbow(start, goal)

        cells = []
        k = gkey
        while k is not None:
            cells.append(k[0])
            k = prev.get(k)
        cells.reverse()
        for a, b in zip(cells, cells[1:]):
            ek = self._ekey(a, b)
            self.used[ek] = self.used.get(ek, 0) + 1
        pts = [(self._coord(i), self._coord(j)) for (i, j) in cells]
        return _simplify(pts)

    @staticmethod
    def _ekey(a, b):
        return (a, b) if a <= b else (b, a)

    @staticmethod
    def _elbow(a, b):
        return _simplify([a, (b[0], a[1]), b])


def _simplify(pts):
    """Drop collinear interior points so the polyline has only real corners."""
    if len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        if (bx - ax, by - ay) != (cx - bx, cy - by):
            out.append(pts[i])
    out.append(pts[-1])
    return out
