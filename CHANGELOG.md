# Changelog

All notable changes to this plugin are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semver.

## [0.2.0] — 2026-08-17

### Added
- **Symbol profiles.** A controlled mapping from component `kind` to drawn shape,
  so a shape means the same thing on every sheet in a set. `software` is the
  default; `plant` covers process and physical plant. The active profile is cited
  in the title block and named in the legend header.
- Three encoding channels, kept deliberately separate: shape carries kind
  (`kind`), height carries criticality (`criticality`, three bands), footprint
  carries scale (`scale`). Height is quantitative — a reader sees a tall object as
  *more*, not as *different* — so spending it on kind would cost the drawing its
  strongest hierarchy signal.
- A kind may render a different silhouette per height band (`service` is a slab at
  bands 1–2, a tower at band 3) without the kind changing.
- Alias tables, so `postgres`, `db`, `store` and `cache` all resolve to
  `datastore`. Authors write what they call the thing.
- **Departure register.** Overriding `form` is always permitted and never silent:
  the sheet prints a numbered departure note and marks the schedule row with `*`.
  Complying is free and silent; deviating is free and visible. That asymmetry is
  what keeps a default alive without making it a cage.
- **Identical-massing detection.** Components sharing kind, height and footprint
  are drawn identically and cannot be told apart. This is the failure a fixed
  vocabulary invites, so the sheet says so rather than leaving the reader to guess
  whether the repetition is meaningful.
- `profile_enforcement`: `record` (default), `warn` (stderr only), `strict`
  (refuse to render), `off` (no profile). CLI: `--profile`, `--enforce`.
- `SYM-001` symbol library plate, drawn by the renderer it governs.

### Changed
- The legend now names **kinds** rather than shapes when a profile is active. A
  legend that names shapes teaches a reader nothing about the vocabulary.
- The title block's `PROJECTION` cell became `STANDARD` and cites the profile
  version. The projection moved to the datum rose, where a reader looks for it.
- Departure notes print ahead of author notes, because notes are trimmed from the
  end when the panel would overflow and a concession that falls off the sheet
  defeats the point of recording it.

### Compatibility
- Specs written before profiles existed remain compliant and flag nothing. Where a
  node declares `form` but no `kind`, the kind is inferred from the form when that
  form is the canonical shape for exactly one kind. A standard that invalidated
  every prior drawing on day one would be abandoned on day two.

## [0.1.0] — 2026-08-17

First release.

### Added
- `blueprint-system-map` skill: isometric general-arrangement drawings on a vintage
  engineering blueprint sheet, output as one self-contained SVG.
- Eleven component forms (`slab`, `tower`, `stack`, `drum`, `silo`, `vault`,
  `lattice`, `plinth`, `pyramid`, `dish`, `core`), chosen by role rather than by
  literal shape so the vocabulary covers software and physical plant alike.
- Six dependency path classes (`data`, `control`, `event`, `bulk`, `telemetry`,
  `secure`) with distinct line styles and payload tags.
- Four skins: `diazo`, `sepia`, `cyanotype`, `stark`. Layout is identical across
  skins, so one drawing in two skins reads as one document reproduced two ways.
- Orthogonal conduit router with turn and congestion penalties, so parallel runs
  fan into separate channels instead of stacking into one illegible trunk.
- Annotation keep-out register with least-overlap fallback.
- Dependency matrix, component schedule, revision history and notes panels.
- Print-size PDF export (`svg_to_pdf.py`) for A4–A0 and ANSI B–E.
- `/system-map` command accepting prose, a repo path, or nothing.
- Benchmark set of three prompts and fourteen assertions in `evals/`.

### Fixed during pre-release evaluation
- PDF export passed PostScript points into cairosvg's pixel arguments, producing
  sheets at 0.75 scale — an "A1" that was nearer A2. Now verified against the
  output MediaBox.
- Panel text was hard-sliced at a character count, producing mid-word breaks such
  as "Derived — never authoritat". Now elides at a word boundary. This defect
  passed an overflow check precisely because the truncation kept it inside the
  frame.

### Known limits
- Above roughly eighteen components the annotation crowds and the dependency matrix
  is suppressed.
- cairosvg ignores SVG filters, so check renders omit grain, mottle and ink bleed.
  Browsers, Figma and PDF export apply them correctly.
