---
description: Draw a system as an isometric general-arrangement drawing on a vintage engineering blueprint sheet
argument-hint: [description of the system, a repo path, or nothing to be asked]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

Draw an isometric blueprint system map.

Use the `blueprint-system-map` skill in this plugin. Read its `SKILL.md` and follow
the workflow there — it owns the spec schema, the form vocabulary, the skins and
the renderer invocation. Do not hand-write SVG.

## Handling the argument

The user typed: `$ARGUMENTS`

Interpret it as follows.

**A prose description of a system** — go straight to authoring the spec. This is
the common case. Infer what you reasonably can rather than interrogating them;
ask only about things that change the drawing's meaning.

**A path to a repo or directory** — discover the topology first. Read
`docker-compose.yml`, Terraform/Helm/k8s manifests, workspace manifests, service
directories and CI config. Prefer declared dependencies over inferred ones. Show
the user the component list you extracted and let them correct it *before* you
render, because a wrong topology drawn beautifully is worse than no drawing.

**Empty** — ask what system they want drawn, roughly what the components are, and
what depends on what. Also ask which register they want: technical review, print
or wall display, or a hero image — that choice drives the skin. Do not guess at
this one; a diazo sheet is wrong for a document with a white background.

## Before you finish

Render a check PNG and actually look at it, as the skill instructs. Then present
the SVG with `present_files`. Say which skin you used and why, so the user can ask
for a different one in a single follow-up rather than re-describing the system.
