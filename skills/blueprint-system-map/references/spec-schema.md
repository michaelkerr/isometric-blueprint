# Spec schema

The renderer takes one JSON object. Everything except `nodes` has a sensible
default, so a spec with nodes and edges alone produces a complete sheet — the
optional fields exist to make the drawing specific rather than to make it work.

## Contents

- [Sheet metadata](#sheet-metadata)
- [Nodes](#nodes)
- [Edges](#edges)
- [Explainer](#explainer)
- [Revisions](#revisions)
- [Worked example: non-software](#worked-example-non-software)
- [Sizing guidance](#sizing-guidance)

## Sheet metadata

All optional. These populate the title block, the sheet headings and the panels.

| Field | Default | Notes |
|---|---|---|
| `title` | `SYSTEM GENERAL ARRANGEMENT` | Large text in the title block. Also seeds the paper-aging pattern, so the same title always ages identically. |
| `subtitle` | `ISOMETRIC ARRANGEMENT AND DEPENDENCY DIAGRAM` | Second line of the title block. |
| `organisation` | `ENGINEERING DIVISION` | Top band of the title block. `organization` also accepted. |
| `classification` | `FOR INTERNAL USE` | Small stamp, top right of the title block. |
| `drawing_no` | `GA-0001-01` | |
| `revision` | `A` | |
| `sheet` | `1 / 1` | |
| `scale` | `N.T.S.` | |
| `drawn_by`, `checked_by`, `date` | `--` | |
| `skin` | `diazo` | `diazo`, `sepia`, `cyanotype`, `stark`. `--skin` on the command line wins. |
| `sheet_heading` | `ISOMETRIC GENERAL ARRANGEMENT` | Top-left of the drawing area. |
| `sheet_subheading` | `DEPENDENCY AND PAYLOAD ROUTING -- ALL TIERS` | |
| `dim_x`, `dim_y` | grid unit counts | Text on the two datum dimension lines. Use these if the plot represents a real span — `"420 m"`, `"3 RACK ROWS"`. |

## Nodes

`nodes` is required and is a list. Order matters: it sets tier ordering, reference
letters and schedule row order.

| Field | Required | Default | Notes |
|---|---|---|---|
| `kind` | **preferred** | inferred from `form` | The controlled vocabulary term. Resolved through the active profile, including its aliases — `postgres`, `db`, `store` and `cache` all reach `datastore`. This is what you should set; the profile then chooses the shape. |
| `criticality` | no | inferred from `height` | `1` peripheral, `2` working, `3` load-bearing. Sets the height band. Prefer this over a raw `height`. |
| `scale` | no | `2` | `1`–`3`. Sets the footprint. Carries fan-out or physical extent. |
| `id` | yes | — | Referenced by edges. Not displayed. |
| `label` | yes | — | Shown on the drawing and in the schedule. Truncated at 28 characters on the drawing, 26 in the schedule, so keep it short. |
| `form` | no | from profile | One of the eleven forms. Setting this **overrides the profile and is recorded as a departure** on the sheet. Use it when you mean it. |
| `tier` | no | `_` | Groups nodes into layout bands, in order of first appearance. Also the main lever you have over the arrangement. |
| `footprint` | no | `[2, 2]` | `[width, depth]` in grid units. `[3, 3]` for the most significant component; `[3, 2]` for something wide and shallow. |
| `height` | no | from `criticality` | Grid units, 0.8–3.5. An explicit figure always wins over the band, because height is a quantitative channel and you may have a real number. |
| `spec` | no | `[]` | Up to four short strings. The **first** appears under the label on the drawing; the **second** appears in the schedule's rating column. The rest are unused today and are safe to keep as documentation. Keep each under ~34 characters. |
| `accent` | no | `false` | Draws the component and its callout in the accent colour. Use on at most one or two nodes. |
| `cell` | no | auto | `[x, y]` grid origin. Setting this on *any* node disables auto-layout for *all* nodes, so if you set one, set them all. |
| `ref` | no | auto | Override the reference letter. Auto-assignment uses `A B C D E F G H J K L M N P R S T U V W X Y Z` — I, O and Q are skipped, as in real drafting, because they read as 1 and 0. |

## Edges

| Field | Required | Default | Notes |
|---|---|---|---|
| `from`, `to` | yes | — | Node `id`s. Unknown ids are skipped silently. |
| `kind` | no | `data` | `data`, `control`, `event`, `bulk`, `telemetry`, `secure`. |
| `payload` | no | none | What travels. Under ~22 characters. |
| `accent` | no | `false` | Highlights the critical path. |

Direction matters: the arrowhead lands at `to`, and the dependency matrix reads
rows as sources and columns as targets.

## Symbol profile

| Field | Default | Notes |
|---|---|---|
| `profile` | `software` | `software`, `plant`, a path to a profile JSON, or `off`. |
| `profile_enforcement` | `record` | `record` prints departures on the sheet; `warn` sends them to stderr only; `strict` refuses to render; `off` disables the profile entirely. |

A profile fixes the mapping from `kind` to shape. Shape is nominal and carries
kind; height and footprint are quantitative and carry magnitude. Mixing them costs
you the ability to show importance, which is the drawing's strongest signal.

Specs written before profiles existed stay compliant: when a node declares `form`
but no `kind`, the kind is inferred from the form where that form is the canonical
shape for exactly one kind. Nothing is flagged. A standard that invalidated every
prior drawing on day one would be abandoned on day two.

Two things are recorded as departures, and neither is blocked in the default mode:

- **Substitution** — `form` contradicts what the profile assigns to the `kind`.
- **Identical massing** — two components share kind, height and footprint, so a
  reader cannot tell them apart. Vary `criticality` or `scale`, never shape.

Adding a kind is one entry in the profile's `kinds` map, plus any aliases. Adding a
whole profile is one file in `profiles/`. Give it an `id` and a `version` — the
version is printed in the title block, and a drawing that cannot cite its standard
is not drawn to one.

## Explainer

```json
"explainer": {
  "heading": "Description of operation",
  "paragraphs": ["...", "..."],
  "notes": ["...", "..."]
}
```

Paragraphs are prose, wrapped to the panel. Notes are numbered and marked in the
accent colour. If the panel would overflow the sheet, paragraph lines are dropped
first and notes second — so put anything load-bearing in `notes`.

## Revisions

Optional. Fills the revision history table; if omitted, one row is synthesised
from `revision`, `date` and `drawn_by`. Maximum eight rows, latest first.

```json
"revisions": [
  {"rev": "C", "date": "2026-08-17", "description": "Added telemetry tier", "by": "MK"},
  {"rev": "B", "date": "2026-06-02", "description": "Issued for review", "by": "MK"}
]
```

## Worked example: non-software

The form vocabulary is deliberately domain-agnostic. Same schema, physical plant:

```json
{
  "title": "Riverside Water Treatment Works",
  "organisation": "Municipal Water Authority",
  "drawing_no": "WTW-114-02",
  "skin": "sepia",
  "dim_x": "260 m",
  "dim_y": "180 m",
  "nodes": [
    {"id": "intake", "label": "Raw Water Intake", "form": "lattice",
     "tier": "intake", "height": 1.8, "spec": ["Screened, 2 x 400 L/s"]},
    {"id": "settle", "label": "Settling Basins", "form": "plinth",
     "tier": "primary", "footprint": [3, 2], "height": 0.9,
     "spec": ["4 lanes, 6 h retention"]},
    {"id": "filter", "label": "Rapid Gravity Filters", "form": "stack",
     "tier": "primary", "footprint": [2, 2], "height": 2.2,
     "spec": ["Sand / anthracite"]},
    {"id": "dose", "label": "Chemical Dosing", "form": "silo",
     "tier": "primary", "height": 2.8, "spec": ["Chlorine, lime, coagulant"]},
    {"id": "clear", "label": "Clearwater Reservoir", "form": "drum",
     "tier": "storage", "footprint": [3, 3], "height": 2.4, "accent": true,
     "spec": ["12 Ml, chlorine contact"]},
    {"id": "pump", "label": "High Lift Pumps", "form": "tower",
     "tier": "distribution", "height": 3.0, "spec": ["3 duty, 1 standby"]},
    {"id": "scada", "label": "SCADA / Control Room", "form": "slab",
     "tier": "distribution", "height": 1.6, "spec": ["Manned 24 h"]}
  ],
  "edges": [
    {"from": "intake", "to": "settle", "kind": "bulk", "payload": "raw water"},
    {"from": "dose", "to": "settle", "kind": "control", "payload": "coagulant"},
    {"from": "settle", "to": "filter", "kind": "bulk", "payload": "settled water"},
    {"from": "filter", "to": "clear", "kind": "bulk", "payload": "filtrate", "accent": true},
    {"from": "dose", "to": "clear", "kind": "control", "payload": "final chlorine"},
    {"from": "clear", "to": "pump", "kind": "bulk", "payload": "potable", "accent": true},
    {"from": "scada", "to": "pump", "kind": "control", "payload": "duty select"},
    {"from": "scada", "to": "dose", "kind": "telemetry", "payload": "residual"}
  ],
  "explainer": {
    "heading": "Description of operation",
    "paragraphs": [
      "Raw water is screened at the intake (A) and gravitates to the settling basins (B), where coagulant dosed from the chemical plant (D) precipitates suspended solids."
    ],
    "notes": [
      "Chlorine contact time is achieved in the clearwater reservoir (E), not in the filters. Reservoir level must not fall below 4 Ml during duty pump changeover.",
      "The control room (G) has no automatic authority over dosing rates; residual readings are advisory only."
    ]
  }
}
```

## Sizing guidance

| Components | Result |
|---|---|
| under 6 | Plot looks sparse and floats in the drawing area |
| 6–14 | The sweet spot |
| 15–18 | Workable; expect tighter annotation |
| over 20 | Dependency matrix is suppressed; consolidate into subsystems instead |

Tiers: three to five bands reads best. One tier puts everything in a single line;
more than six makes each band thin and the plot very wide.
