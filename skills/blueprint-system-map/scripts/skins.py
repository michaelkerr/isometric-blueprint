"""Skin definitions for blueprint-system-map.

A skin is only paper + ink + a few tints. Layout, linework weights and drafting
furniture are identical across skins, so a drawing rendered in `diazo` and the
same drawing in `sepia` read as the same document reproduced two ways -- which is
exactly what happens with real reprographics.

Fields
  paper        base sheet colour
  paper_edge   slightly different tone used for the vignette at the sheet edges
  ink          primary linework colour
  ink_soft     secondary linework (grid, hatching, dimension lines)
  ink_faint    tertiary (paper grain lines, tick marks)
  accent       one highlight colour for the critical path / core component
  accent2      second highlight, used sparingly
  face_top     fill for the top face of a solid
  face_right   fill for the right (+x) face
  face_left    fill for the left (+y) face -- the darkest
  glow         colour of the emissive halo on `core` forms (None disables it)
  grain        0..1 strength of the paper-noise overlay
  bleed        0..1 strength of the ink-bleed blur on linework
"""

SKINS = {
    # White linework on Prussian blue -- the diazo negative everyone pictures
    # when they hear "blueprint".
    "diazo": {
        "label": "DIAZO NEGATIVE",
        "paper": "#123a5e",
        "paper_edge": "#0d2c49",
        "ink": "#eaf4ff",
        "ink_soft": "#9dc4e4",
        "ink_faint": "#5b8bb2",
        "accent": "#ffd479",
        "accent2": "#7ff0d0",
        "face_top": "#20527c",
        "face_right": "#19446b",
        "face_left": "#10345a",
        "glow": "#9fe8ff",
        "grain": 0.16,
        "bleed": 0.35,
    },
    # Aged manila stock, iron-gall ink. The utilitarian workshop document:
    # foxed paper, coffee, pencil annotation.
    "sepia": {
        "label": "SEPIA PRINT / AGED STOCK",
        "paper": "#d9c9a3",
        "paper_edge": "#c3ae83",
        "ink": "#2b2118",
        "ink_soft": "#6a5540",
        "ink_faint": "#9c8666",
        "accent": "#9c2f16",
        "accent2": "#3c5a44",
        "face_top": "#cdbb92",
        "face_right": "#bda880",
        "face_left": "#a8906a",
        "glow": "#c9741f",
        "grain": 0.30,
        "bleed": 0.55,
    },
    # Faded whiteprint: dark navy line on washed-out cyan. What a diazo print
    # looks like after thirty years in a flat file.
    "cyanotype": {
        "label": "WHITEPRINT / FADED CYAN",
        "paper": "#dfe9ea",
        "paper_edge": "#c4d6d8",
        "ink": "#17324a",
        "ink_soft": "#4d7690",
        "ink_faint": "#8aa8b8",
        "accent": "#a8431f",
        "accent2": "#1d6b6b",
        "face_top": "#d3e2e4",
        "face_right": "#c0d4d7",
        "face_left": "#a9c3c8",
        "glow": "#2e8fa8",
        "grain": 0.22,
        "bleed": 0.40,
    },
    # Retro-futurist: near-black drafting film, amber and ice-blue trace.
    # Use for the arc-reactor register -- advanced device, inherited document.
    "stark": {
        "label": "DRAFTING FILM / NEGATIVE",
        "paper": "#0c1013",
        "paper_edge": "#05080a",
        "ink": "#d9e6ee",
        "ink_soft": "#6f8794",
        "ink_faint": "#3d4d57",
        "accent": "#ffb340",
        "accent2": "#5fd8ff",
        "face_top": "#1a2329",
        "face_right": "#141b20",
        "face_left": "#0e1418",
        "glow": "#7fe4ff",
        "grain": 0.12,
        "bleed": 0.25,
    },
}

DEFAULT_SKIN = "diazo"


def get(name):
    if not name:
        name = DEFAULT_SKIN
    key = str(name).strip().lower()
    if key not in SKINS:
        raise SystemExit(
            "unknown skin %r -- choose from: %s" % (name, ", ".join(sorted(SKINS)))
        )
    out = dict(SKINS[key])
    out["name"] = key
    return out
