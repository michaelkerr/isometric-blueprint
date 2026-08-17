---
name: blueprint-system-map
description: Draw any system as an isometric map on a vintage industrial engineering blueprint - 3D massing on a grid, routed dependency conduits with payload tags, legend, component schedule, dependency matrix, notes and a full title block, as one self-contained SVG. Use this whenever someone wants a system map, architecture or infrastructure diagram, service topology, dependency graph, data-flow map, process or plant layout, or a how-it-all-fits-together picture - especially if they say isometric, 3D, axonometric, blueprint, schematic, technical or engineering drawing, drafting, cyanotype, diazo, arc-reactor, retro-futurist, Soviet or vintage industrial. Also use it to redraw an existing diagram as something presentable, for a poster of an architecture, or a hero image for a design doc or deck. Prefer it over hand-written SVG, Mermaid or Graphviz whenever the request implies a picture of a system, not a plain box-and-arrow chart - those cannot produce isometric massing, drafting furniture or a title block.
---

# Blueprint system map

Turn a description of a system into an isometric general-arrangement drawing on an
aged engineering sheet: varied 3D volumes on a ground grid, dependencies routed as
orthogonal conduits carrying labelled payloads, and the drafting furniture that
makes it read as a surveyed document rather than a poster — legend, component
schedule, dependency matrix, revision history, notes panel, title block, zone
markings, dimension lines, projection datum.

The look blends four real traditions, and knowing which one you are borrowing from
at any moment is what keeps the output from sliding into pastiche:

- **Mid-century industrial engineering drawing** — dense linework, elevation
  course lines, callout bubbles with leaders, dimension lines, a component
  schedule keyed by reference letter.
- **Diazo/blueprint reproduction** — the white-on-Prussian-blue print, not a
  modern CAD plot. Ink bleeds slightly into paper; the sheet has grain.
- **Utilitarian workshop document** — foxed stock, fold creases, monospaced
  annotation, a title block that reads like a form someone had to fill in.
- **Retro-futurist device schematic** — the object is fictional, so real
  technical cues are doing the work of making an advanced thing feel credible.
  Exactly one emissive core, never two.

## Never hand-write the SVG

The geometry is done by `scripts/render_blueprint.py`. Writing isometric SVG by
hand means recomputing `cos(30°)` offsets for every vertex, depth-sorting by eye,
and routing conduits that end up crossing through buildings — and the result
drifts stylistically every time. Your job is the *content*: what the components
are, what depends on what, what flows down each path, and what a reader needs to
be told. The script's job is projection, occlusion, routing, annotation placement
and the sheet.

## Workflow

### 1. Get the system content first

Do not touch the renderer until you know what you are drawing. Depending on where
the information lives:

- **From the conversation** — the user describes the system in prose. Work with
  what they gave you; infer the obvious and ask only about things that would
  change the drawing's meaning, not its decoration.
- **From a repo** — read `docker-compose.yml`, Terraform/Helm/k8s manifests,
  `package.json` workspaces, service directories, CI config, README diagrams.
  Prefer declared topology over inferred: a `depends_on` or a service-to-service
  env var is evidence, an import graph usually is not.
- **From connectors** — architecture pages in Confluence/Notion, service
  catalogues, Compass components, Jira epics that name systems.

Aim for **6–14 components**. Below six the sheet looks empty; above about
eighteen the annotation gets crowded and the dependency matrix stops being
readable, so consolidate into subsystems and say so in the notes.

If the user names fewer than six things but the system is clearly bigger, ask
whether to expand or to draw the subsystem as scoped. That is a question about
meaning and is worth asking; "which shade of blue" is not.

### 2. Write the spec

Author a JSON spec. Full field reference: `references/spec-schema.md`.

Declare each component's **`kind`** and let the symbol profile choose the shape.
Do not pick `form` and `height` by hand unless you have a reason — that is what
the profile is for, and hand-picking is how a drawing set stops being readable.

```json
{
  "title": "Order Fulfilment Platform",
  "skin": "diazo",
  "nodes": [
    {"id": "gw", "label": "API Gateway", "kind": "gateway", "tier": "ingress",
     "criticality": 3, "spec": ["12k req/s", "JWT verify"]},
    {"id": "core", "label": "Order Core", "kind": "authority", "tier": "service",
     "criticality": 3, "scale": 3, "accent": true,
     "spec": ["Authoritative state"]}
  ],
  "edges": [
    {"from": "gw", "to": "core", "kind": "data", "payload": "order cmd",
     "accent": true}
  ],
  "explainer": {"heading": "...", "paragraphs": ["..."], "notes": ["..."]}
}
```

Leave `cell` off every node and let the auto-layout place them in tier bands —
it centres the bands and produces a balanced plot. Only set `cell` coordinates by
hand when you have a spatial reason (a genuine geographic or physical
arrangement, or a specific adjacency you need the reader to see).

### 3. Render

```bash
python3 <skill_dir>/scripts/render_blueprint.py spec.json -o sheet.svg
```

Options: `--skin diazo|sepia|cyanotype|stark` and
`--profile software|plant|off` override the spec; `--enforce
record|warn|strict|off` sets how departures are handled; `--pdf sheet.pdf` also
writes a print-ready sheet. Only produce the PDF if the
user asks for print, a poster, or a PDF — it needs `cairosvg`, `rsvg-convert` or
`inkscape`, and quietly failing to make one is worse than not offering.

### 4. Look at it before you hand it over

Render to PNG and actually read the image. This step catches the failures that
matter and it is cheap:

```bash
python3 -c "import cairosvg; cairosvg.svg2png(url='sheet.svg', write_to='check.png', output_width=1900)"
```

Then Read `check.png` and check: does any label sit on top of geometry or another
label? Does any panel's text run through its frame? Is the massing roughly
centred with the plot filling the drawing area? Does the tallest, most important
component read as the visual centre? Fix the spec — usually by shortening a
label, a `spec` line or a `payload` — and re-render. Long strings are the single
most common cause of a crowded sheet, because they are what the placement engine
cannot shrink.

**The check PNG is for layout, not for the finish.** cairosvg silently ignores SVG
filters, so the paper grain, mottling and ink bleed will be missing from
`check.png` and the sheet will look flatter and more like a modern plot than it
actually is. Fold creases, foxing and the vignette do render. Do not "fix" absent
grain and do not tell the user the aging failed — browsers, Figma and the PDF
export all apply the filters correctly. Only judge composition and legibility
from the raster.

Then present the SVG (and PDF, if asked) with `present_files`.

## The symbol profile — shape is not yours to choose

A profile is a controlled mapping from `kind` to drawn shape. `software` is the
default; `plant` covers process and physical plant. The active profile is cited in
the title block and named in the legend header, so a reader knows which vocabulary
is in force.

Three channels carry three independent facts, and they must not be mixed:

| Channel | Field | Carries |
|---|---|---|
| Shape | `kind` | What sort of thing it is |
| Height | `criticality` — 1, 2 or 3 | How load-bearing it is |
| Footprint | `scale` — 1, 2 or 3 | Fan-out or physical extent |

The reason to keep them separate is that height is a *quantitative* channel: a
reader sees a tall object as **more**, not as **different**. If height denoted
kind, it could no longer denote importance — and importance is the strongest
signal the drawing has. So say `"kind": "database", "criticality": 3`, never
`"form": "tower"` to mean "this one is important".

A kind may render a different silhouette per height band — `service` draws as a
slab at bands 1–2 and a tower at band 3 — but the *kind* does not change. The
shape family stays recognisable while the size still reads as magnitude.

### Deviating

Set `form` or `height` explicitly and it wins. Nothing is blocked. But the sheet
then prints a departure note and marks that row in the schedule with `*`, because
a standard nobody can see being broken is not a standard. Complying is free and
silent; deviating is free and visible. Use it when you mean it, and expect the
note to appear.

`profile_enforcement` controls this: `record` (default, print departures on the
sheet), `warn` (stderr only, sheet stays clean), `strict` (refuse to render), or
`off` (no profile at all, `form` and `height` taken literally).

If you are asked for a purely decorative drawing — a hero image where the shapes
should serve the composition — use `--profile off` rather than accumulating a page
of departure notes.

### The failure mode a fixed vocabulary invites

If a system really is eight near-identical services, a strict shape mapping gives
you eight identical boxes. The renderer detects this and records it: components
sharing kind, height and footprint are drawn identically and cannot be told apart.

Do not fix that by varying shape — that breaks the vocabulary for every future
reader. Fix it by varying `criticality` and `scale`, which is honest, or accept
the repetition, which is also honest: the drawing is telling you the architecture
is uniform.

## The form vocabulary

These are the shapes a profile maps onto. Set `form` directly only when
deviating deliberately, or when running with `--profile off`.

| Form | Reads as | Typical use |
|---|---|---|
| `tower` | the tall important one | primary service, main plant, headquarters |
| `slab` | general workhorse | processing service, generic block, department |
| `stack` | tiered or sharded | partitioned store, multi-stage process, hierarchy |
| `drum` | contained volume | database, tank, reservoir, warehouse of record |
| `silo` | queue that drains | message bus, hopper, buffer, backlog |
| `vault` | bulk hall | archive, data warehouse, cold storage, depot |
| `lattice` | structure not substance | load balancer, mesh, fabric, CDN edge, network |
| `plinth` | wide shallow field | node pool, rack farm, sensor array, fleet |
| `pyramid` | many into few | aggregator, reducer, approval gate, funnel |
| `dish` | reaches outside | third party, external API, satellite, regulator |
| `core` | the point of the drawing | the one authoritative or emissive centre |

**One `core`/`authority`, maximum.** It glows and it wins the eye. A second one
destroys the hierarchy and the sheet stops having a subject. If nothing in the
system is genuinely central, use none at all and mark the important component
`"accent": true` instead.

To add a form beyond these eleven, or a kind to a profile, see
`references/drafting-conventions.md`.

## Choosing path kinds

| Kind | Line | Use for |
|---|---|---|
| `data` | solid | synchronous request/response |
| `control` | dash-dot | command, config, orchestration |
| `event` | dashed | asynchronous notification |
| `bulk` | heavy double | batch, replication, ETL |
| `telemetry` | fine dotted | metrics, logs, traces |
| `secure` | ticked | mutually authenticated or encrypted channel |

Set `"accent": true` on the two or three edges that form the critical path. Every
edge accented is the same as none accented.

`payload` should name **what travels**, not what happens: `order.created`,
`auth.jwt`, `hourly batch`, `340 kV` — not "sends data to". Keep it under about
22 characters or the tag crowds the conduit it belongs to. Omit `payload`
entirely on paths where the class already says everything, which is usually true
of `telemetry`.

## Writing the notes panel

This is where the drawing stops being decorative. The pictorial view shows what
connects to what; the notes say what a reader would otherwise get wrong. Aim for
two short paragraphs of operation description plus two to four numbered notes,
and reference components by their letter — "the core (D)" — because that is how
the schedule and the drawing are keyed together.

Good notes are load-bearing constraints and invariants:

> The warehouse (H) is a read-only derivative of the event stream. It must never
> be used as a source of truth for entitlement decisions.

Bad notes restate the diagram:

> The gateway connects to the identity service.

If you learned something during discovery that surprised you, that is almost
certainly a note.

## Choosing a skin

`diazo` is the default and the right answer when someone says "blueprint".
`sepia` for an inherited, workshop, archival feel. `cyanotype` when the drawing
needs to survive being printed or pasted into a light-background document.
`stark` for the retro-futurist register — dark film, amber and ice-blue trace.
Details and palettes: `references/skins.md`.

## Failure modes worth knowing

- **Labels colliding.** The placement engine tries many positions and falls back
  to the least-bad one, so a genuine collision means the sheet is over-full.
  Shorten labels and payloads, or cut components, rather than fighting it.
- **A sparse, floating plot.** Too few components for the sheet. Add the ones you
  elided, or merge tiers so the bands are fuller.
- **Everything the same height.** The most common way a technically correct
  drawing ends up saying nothing.
- **Conduits taking long detours.** The router keeps half a unit of clearance
  from every footprint, so a component boxed in on all sides forces a long way
  round. Give the crowded tier one more unit of spacing by widening a footprint,
  or set `cell` by hand.
- **A wall of text in the notes panel.** Prose gets trimmed to fit the frame, so
  anything past the fold is silently lost. Write to the space. Departure notes are
  printed ahead of yours precisely so they cannot be the thing that falls off.
- **A page of departure notes.** You are fighting the profile. Either you have the
  wrong profile for this domain, or you want `--profile off` because the drawing is
  decorative rather than documentary.

## Reference files

- `references/spec-schema.md` — every field, defaults, and worked examples
  including a non-software one
- `profiles/software.json`, `profiles/plant.json` — the controlled kind
  vocabularies, with aliases so `postgres`, `db` and `store` all resolve
- `references/skins.md` — the four skins, their palettes, and when each is right
- `references/drafting-conventions.md` — what each piece of sheet furniture is
  for, and how to add a new component form
- `assets/example-spec.json` — a complete 10-component software spec
