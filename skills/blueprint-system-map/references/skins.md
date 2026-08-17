# Skins

A skin changes paper, ink and tints. It never changes layout, line weights, or
which drafting furniture appears. That is deliberate: a drawing rendered in two
skins should read as the same document reproduced two different ways, which is
what actually happens with reprographics. If you find yourself wanting a skin to
move things around, you want a change to the renderer, not a new skin.

Each skin also sets `grain` (paper noise strength) and `bleed` (how far ink
soaks into the stock). Those two numbers do most of the work of making the sheet
feel printed rather than plotted.

## `diazo` — white line on Prussian blue

The blueprint everyone pictures. A diazo *negative*: the linework is the unexposed
paper, so it is pale and the field is deep blue. Moderate grain, moderate bleed.

- **Use when** someone says "blueprint" without qualification, for anything
  presented on screen or on a dark slide, and whenever you are unsure.
- **Avoid when** the drawing will be printed on white paper or pasted into a
  light-background document — it will look like a large blue rectangle and burn
  toner.
- Accent is warm amber, secondary is mint. Core glow is ice blue.

## `sepia` — iron-gall ink on aged manila

Foxed stock, brown-black ink, the heaviest grain and bleed of the four. This is
the utilitarian workshop register: a document that has been handled, folded, and
kept in a drawer for decades.

- **Use when** the framing is inherited, archival, historical, or physical plant;
  when the user mentions Soviet-era, vintage, aged, or "found document"; and for
  anything that should feel like it predates computers.
- **Avoid when** you need maximum legibility at small size — the low ink/paper
  contrast plus heavy grain costs some crispness.
- Accent is oxide red, secondary is a muted green.

## `cyanotype` — navy line on faded pale cyan

A whiteprint: a diazo positive that has spent thirty years in a flat file. Dark
ink on a very light ground.

- **Use when** the drawing goes into a light-background document, a README, a
  printed report, or a slide with a white master. This is the practical choice
  for anything that has to survive being printed.
- **Avoid when** you want the drawing to feel like an object in its own right —
  it reads as a reproduction, which is the point, but it is the least dramatic of
  the four.
- Accent is brick, secondary is teal.

## `stark` — amber and ice-blue on near-black film

Not a reproduction process. Dark drafting film with luminous trace: the
retro-futurist register, for a fictional advanced device that still needs to look
engineered. Lowest grain and bleed, because film does not absorb ink the way
paper does.

- **Use when** the subject is a speculative or high-energy system, when the user
  asks for arc-reactor schematics, or when the drawing is a hero image and needs
  to be the most striking thing on the page.
- **Avoid when** the drawing needs to look like a real historical artefact — no
  reprographic process produced this, and a reader who knows drawings will notice.
- **Pair with a `core` node.** The glow is the whole point of this skin, and
  without one the sheet is just dark.

## Adding a skin

Add an entry to `SKINS` in `scripts/skins.py`. Every key in the dict is required;
the docstring at the top of that file documents what each one controls. Two
things to get right:

- **`face_top` > `face_right` > `face_left` in lightness.** The light comes from
  the upper right. Invert this and the volumes read as holes.
- **`ink_faint` must stay legible against `paper`.** It carries the ground grid,
  hatching and telemetry paths. If it disappears, the drawing loses the dense
  linework that makes it look technical, and telemetry paths vanish entirely.

Set `glow` to `None` for a skin with no emissive register; `core` nodes then
render as plain ringed drums, which is a legitimate look for a purely
reprographic skin.
