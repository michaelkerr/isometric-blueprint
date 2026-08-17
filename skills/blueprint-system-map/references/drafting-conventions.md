# Drafting conventions

What each piece of the sheet is for, why it is there, and how to extend the
renderer. Read this when a drawing looks technically fine but does not feel like a
document, or when you need a component form that does not exist yet.

## Contents

- [Why the furniture matters](#why-the-furniture-matters)
- [The sheet, piece by piece](#the-sheet-piece-by-piece)
- [The projection](#the-projection)
- [Adding a component form](#adding-a-component-form)
- [Tuning the router](#tuning-the-router)
- [Annotation placement](#annotation-placement)

## Why the furniture matters

A modern architecture diagram says "here are the parts". An engineering drawing
says "this is a controlled document describing a specific arrangement, and someone
signed it off". The difference is almost entirely the furniture: the frame, the
zone markings, the schedule keyed by reference letter, the revision table, the
title block with its fields filled in.

That is also why the furniture has to carry *real* information. A title block with
placeholder text undermines the whole effect, because the one thing a reader
checks first is whether the document looks like it was actually issued. Fill in
`organisation`, `drawing_no`, `date` and `drawn_by`. If you do not know them, use
something plausible from context rather than leaving the defaults.

## The sheet, piece by piece

**Border and zone markings** — Numbers 1–12 along the top and bottom, letters
A–H down the sides. Their purpose is citation: a reader can say "the dish at J6"
in an email. Keep them even if the drawing is small.

**Sheet heading** — Top left of the drawing area, above the model. States what
view this is and under what conditions. "Steady state", "all tiers", "failover
condition" — the qualifier is worth including because it implies other sheets
exist.

**Ground grid and datum boundary** — The grid gives the isometric a floor;
without it the volumes float. Tick marks on the boundary imply a survey.

**Dimension lines** — Two, along the near edges, with arrowheads and witness
lines. On a fictional subject they are honest decoration unless you set `dim_x`
and `dim_y` — but if the plot represents anything with a real extent, set them.

**Callout bubbles and leaders** — A circled reference letter on a dashed leader
from the component's apex, with the designation and the first spec line beside it.
Bubbles rather than labels-on-boxes is the drafting convention, and it is why the
schedule can be keyed to the drawing.

**Payload tags** — Small boxed monospace text with a knockout background so the
conduit does not run through the lettering, on a short leader back to the path.

**Legend** — Isometric pictograms of every form used, then a line sample for
every path class present. Only what is used appears; a legend listing things not
on the sheet is a tell that the drawing was generated rather than drawn.

**Component schedule** — Reference letter, designation, rating. The bridge
between the picture and the text. In real practice this is the part people
actually read.

**Dependency matrix** — Rows are sources, columns are targets, the letter in each
cell is the first letter of the path class. This exists because the pictorial view
cannot state adjacency exactly: two components that look next to each other may
not be connected, and this table settles it. Suppressed above twenty components,
where it stops being readable.

**Notes panel** — Description of operation plus numbered notes. The only place on
the sheet that can express a constraint, an invariant, or a prohibition. See
SKILL.md for what makes a note load-bearing.

**Revision history** — Latest at top. Implies the document has a history, which
is most of what makes it feel controlled.

**Projection datum and scale bar** — The X/Y/Z axis rose states the projection so
a reader knows how to interpret the geometry. The scale bar is in grid units, not
metres, unless you have set the dimension text.

## The projection

True isometric, 30°:

```
X = (x - y) * cos(30) * S
Y = (x + y) * sin(30) * S - z * H
```

Four consequences that come up constantly:

1. **+x runs down-right, +y runs down-left.** The near corner of any footprint is
   `(x_max, y_max)`.
2. **You see the planes `x = x_max` (lands on the right) and `y = y_max` (lands
   on the left).** The left face is darkest because the light is upper-right.
3. **A ground-plane circle projects to an axis-aligned ellipse** with
   `rx = r·cos30·S·√2`, `ry = r·sin30·S·√2`. No rotation — drums and dishes are
   cheap.
4. **Screen width and height are both proportional to `(x_extent + y_extent)`,**
   so *every* rectangular plot lands at about 1.73:1 regardless of its
   proportions. You cannot make an isometric plot squarer by transposing the
   layout. This is why the sheet reserves a lower strip for schedules instead of
   trying to fill a square drawing area with a wide model.

Depth sorting is a painter's algorithm on `(x + w) + (y + d)` — the near corner —
ascending. It is correct as long as footprints do not overlap, which the layout
guarantees and hand-set `cell` values must respect.

## Adding a component form

In `scripts/geometry.py`:

1. Write `f_yourform(P, x, y, w, d, h)` returning a list of primitives in painter
   order. Compose from the existing `_box`, `_cylinder` and `_cone` helpers where
   you can — they already handle face roles, course lines and the cylinder
   gradient.
2. Register it in `FORMS` and add a one-line description to `FORM_NOTES`. The
   description appears in the legend, so write it as what the form *reads as*, not
   what it is made of.
3. Add a row to the form table in SKILL.md, or nobody will ever choose it.

Primitive roles map onto skin colours in `emit_prims`: `top`, `right`, `left`
(auto-hatched), `frame` (heavy linework, no fill), `detail` (fine linework),
`cyl` (cylinder gradient), `glow`. Use `frame` sparingly — it is the heaviest
weight on the sheet and it is what makes the `lattice` form read as open
structure.

The one rule: **draw the three faces in the order right, left, top.** Any other
order produces subtly wrong overlaps at the silhouette edges on non-convex forms.

## Tuning the router

`scripts/router.py` runs Dijkstra on a half-unit lattice with three costs:

- **distance** — the obvious one
- **`TURN_COST`** (1.35) — charged per direction change, which is what produces
  long straight runs instead of staircases. Raise it for fewer, longer legs.
- **`REUSE_COST`** (2.20) — charged per lattice edge an earlier route already
  used, so parallel paths fan out into separate channels instead of stacking into
  one illegible trunk. Raise it if conduits look bundled; lower it if they take
  silly detours to avoid each other.

Footprints are blocked *including their boundary*, so conduits keep half a unit of
clearance from every wall. A component boxed in on all four sides will therefore
force a long detour — the fix is spacing, not router parameters.

## Annotation placement

`Obstacles` in `render_blueprint.py` is a keep-out register. Component
silhouettes and everything outside the drawing region are seeded first, then each
label asks for the first clear candidate position and reserves it.

Two design decisions worth preserving if you change it:

- **Callouts claim space before payload tags.** A component's designation matters
  more than a path's payload, so it gets the clear air above the massing.
- **The fallback picks least-overlap, not last-tried.** Taking the last candidate
  is what produces the classic failure where one label flies to an absurd
  position while a nearly clear slot sat unused earlier in the list.

When a collision does survive, it means the sheet is over-full. Shorten strings or
cut components. Adding more candidate positions past this point just moves the
problem somewhere less predictable.
