"""Symbol profiles: the controlled mapping from component kind to drawn form.

Why this exists
---------------
Without a profile, the shape of a component means whatever the author felt like
that day. That is fine for one drawing and useless for a drawing *set* -- a
reader cannot learn a vocabulary that changes between sheets.

A profile fixes the nominal channel (shape carries kind) and leaves the
quantitative channels free (height carries criticality, footprint carries
scale). Those must not be mixed. If height denoted kind, height could no longer
denote importance, and importance is the strongest signal the drawing has.

Deviation is always permitted, and never silent
-----------------------------------------------
An author who needs a shape the profile does not sanction can just say so. The
cost is not a refusal or a warning in a log nobody reads -- it is a line in the
notes panel and a mark against the row in the component schedule. That is how
engineering practice has always handled a concession: you may depart from the
standard, and the drawing says you did.

This asymmetry is the whole design. Complying is free and silent; deviating is
free and visible. That is what keeps a default alive without making it a cage.

Enforcement modes (`profile_enforcement` in the spec):
  "record"  default -- resolve, draw, and print the departure register
  "strict"  refuse to render on a substitution or an unregistered kind
  "warn"    print departures to stderr only, keep the sheet clean
  "off"     no profile; `form` and `height` are taken literally
"""

import json
import os

PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           os.pardir, "profiles")

# Criticality band -> (low, high, default) height in grid units. Three bands is
# deliberate: readers reliably rank three sizes at a glance and stop being able
# to at five.
BANDS = {
    1: (0.8, 1.4, 1.1),
    2: (1.8, 2.4, 2.1),
    3: (2.8, 3.5, 3.1),
}

# Scale rank -> footprint. Footprint area carries fan-out or physical extent.
SCALES = {
    1: [2, 2],
    2: [2, 2],
    3: [3, 3],
}


class Profile:
    def __init__(self, data):
        self.id = data.get("id", "custom")
        self.version = data.get("version", "0.0")
        self.label = data.get("label", self.id)
        self.kinds = data.get("kinds", {})
        self.aliases = {k.lower(): v for k, v in (data.get("aliases") or {}).items()}
        # Reverse index so a spec that names `form` directly is still recognised
        # as compliant when that form is the canonical shape for exactly one
        # kind. Existing specs therefore keep working without a mass rewrite,
        # which matters: a standard that invalidates all prior drawings on day
        # one gets abandoned on day two.
        self._by_form = {}
        for kind, d in self.kinds.items():
            forms = [d.get("form")]
            forms += list((d.get("band_forms") or {}).values())
            for f in forms:
                if f:
                    self._by_form.setdefault(f, set()).add(kind)

    def resolve_kind(self, name):
        if not name:
            return None
        key = str(name).strip().lower().replace(" ", "-").replace("_", "-")
        key = self.aliases.get(key, key)
        return key if key in self.kinds else None

    def kind_for_form(self, form):
        s = self._by_form.get(form)
        return next(iter(s)) if s and len(s) == 1 else None

    def form_for(self, kind, band):
        d = self.kinds[kind]
        bf = (d.get("band_forms") or {}).get(str(band))
        return bf or d.get("form", "slab")

    def note_for(self, kind):
        return (self.kinds.get(kind) or {}).get("note", "")


def load(name):
    """Load a profile by id, by file path, or return None for 'off'/'none'."""
    if not name or str(name).lower() in ("off", "none", "false"):
        return None
    p = str(name)
    cand = p if os.path.isfile(p) else os.path.join(PROFILE_DIR, p + ".json")
    if not os.path.isfile(cand):
        avail = []
        if os.path.isdir(PROFILE_DIR):
            avail = sorted(f[:-5] for f in os.listdir(PROFILE_DIR)
                           if f.endswith(".json"))
        raise SystemExit("unknown profile %r -- available: %s (or 'off')"
                         % (name, ", ".join(avail) or "none installed"))
    with open(cand) as fh:
        return Profile(json.load(fh))


def apply(profile, nodes, mode="record"):
    """Resolve every node against the profile, in place.

    Returns a list of departure strings, ready to be printed on the sheet. An
    empty list means the drawing is fully compliant, which is the common case
    and should cost the author nothing.
    """
    if profile is None:
        return []

    dep = []
    for n in nodes:
        kind = profile.resolve_kind(n.get("kind"))
        declared_kind = n.get("kind")

        if kind is None and declared_kind:
            dep.append("%s (%s) uses kind '%s', which is not registered in "
                       "profile %s. Shape is uncontrolled."
                       % (n["label"], n["ref"] or "-", declared_kind,
                          profile.version))
        if kind is None and not declared_kind:
            kind = profile.kind_for_form(n.get("form"))

        # criticality -> height band. An explicit height always wins; it is a
        # quantitative channel and the author may have a real figure.
        band = n.get("criticality")
        try:
            band = int(band) if band is not None else None
        except (TypeError, ValueError):
            band = None
        if band not in BANDS:
            band = None
        if band is None:
            h = n.get("_height_explicit")
            band = 3 if (h or 0) >= 2.8 else (1 if (h or 0) <= 1.4 else 2)
        elif n.get("_height_explicit") is None:
            n["h"] = BANDS[band][2]
        n["band"] = band

        sc = n.get("scale")
        try:
            sc = int(sc) if sc is not None else None
        except (TypeError, ValueError):
            sc = None
        if sc in SCALES and n.get("_footprint_explicit") is None:
            n["w"], n["d"] = float(SCALES[sc][0]), float(SCALES[sc][1])

        if kind is None:
            if n.get("form") and mode != "off":
                dep.append("%s (%s) is drawn as '%s', a shape not registered in "
                           "profile %s." % (n["label"], n["ref"] or "-",
                                            n["form"], profile.version))
            continue

        n["kind"] = kind
        want = profile.form_for(kind, band)
        got = n.get("_form_explicit")
        if got and got != want:
            dep.append("%s (%s) is drawn as '%s' by author override. Profile %s "
                       "assigns '%s' to kind '%s'."
                       % (n["label"], n["ref"] or "-", got, profile.version,
                          want, kind))
            n["form"] = got
        else:
            n["form"] = want
        if not n.get("spec"):
            note = profile.note_for(kind)
            if note:
                n["spec"] = [note]

    dep += _ambiguities(nodes)
    return dep


def _ambiguities(nodes):
    """Flag components a reader cannot tell apart.

    Two components of the same kind at the same height and footprint are drawn
    identically. That is the failure mode a strict shape vocabulary invites --
    eight services become eight indistinguishable boxes -- and it is worth
    saying out loud on the sheet rather than leaving the reader to wonder
    whether the repetition is meaningful.
    """
    seen = {}
    out = []
    for n in nodes:
        if not n.get("kind"):
            continue
        key = (n["kind"], round(n["h"], 2), round(n["w"], 2), round(n["d"], 2))
        seen.setdefault(key, []).append(n)
    for key, group in seen.items():
        if len(group) > 1:
            refs = ", ".join("%s (%s)" % (g["label"], g["ref"] or "-")
                             for g in group)
            out.append("Identical massing: %s share kind '%s' at the same height "
                       "and footprint, so they cannot be told apart by shape. "
                       "Vary height or footprint, never shape." % (refs, key[0]))
    return out
