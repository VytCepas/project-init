---
name: diagram
description: Draw and iterate on diagrams with the user — system architecture, code structure, data models, flows, or idea sketches — as version-controlled Mermaid/DOT/Excalidraw source with live previews
when_to_use: Use when the user says "draw", "diagram", "sketch", "visualize the architecture", "schema", "flowchart", "sequence diagram", "ERD", "mindmap", or wants to see how components/ideas relate.
user-invocable: true
---

# Diagram — draw it together, keep the source

Diagrams here are **source files first** (Mermaid by default): diffable,
regenerable, and reviewable like code. Renders are previews; the committed
source is the artifact.

## 1. Pick the notation by diagram type

| The user wants to see… | Use |
|---|---|
| Components/flow/dependencies | Mermaid `flowchart` (`LR` for pipelines, `TB` for hierarchies); add `layout: elk` frontmatter when >15 nodes |
| Interactions over time | Mermaid `sequenceDiagram` |
| Lifecycle / states | Mermaid `stateDiagram-v2` |
| Data model / tables | Mermaid `erDiagram` |
| Modules / classes | Mermaid `classDiagram` |
| Brainstorm / idea map | Mermaid `mindmap` |
| Timeline / plan | Mermaid `gantt` |

**Escalations (only when Mermaid genuinely fails the job):**
- Dense graph that Mermaid tangles even with `layout: elk` → Graphviz **DOT
  source**. Render only if `dot` is installed (`command -v dot`); otherwise
  ship the source and say plainly that no local renderer is available.
- Free-form idea sketch with spatial meaning → **Excalidraw JSON** (open and
  edit at excalidraw.com). No local render — say so; don't pretend.

## 2. Ground before drawing

- **Code/architecture mode:** derive nodes and edges from reality — read
  `CODE_MAP.md` (if present), imports, and directory structure. Never invent
  a component; if a box isn't backed by a file/module/service you can name,
  it doesn't go on the diagram.
- **Idea mode:** one interview round first — what are the entities, what
  relations matter, what question should the diagram answer?

## 3. The iteration loop

1. Write source to `docs/diagrams/<slug>.mmd` — or `.agents/vault/design/`
   when the project has an Obsidian vault (its existing home for "diagrams,
   spec drafts").
2. Preview:
   - On Claude Code, send the `.mmd` file to the user with inline render —
     the side panel renders Mermaid natively, no tooling needed.
   - For a picture file (or non-Claude surfaces):
     `bunx @mermaid-js/mermaid-cli -i <slug>.mmd -o <slug>.svg` and send the
     SVG.
3. Ask **one** targeted question per round — "right boxes?", "right
   arrows?", "right grouping?" — not "any feedback?".
4. Apply feedback as **small edits, never wholesale regeneration**. Keep
   node IDs stable across rounds so the source diff shows exactly what
   changed.

## 4. Quality rules

- **≤ ~25 nodes per view.** Past that, split: one overview diagram plus
  drill-down diagrams per area. A mega-graph answers no question.
- `subgraph` blocks for layers and boundaries (UI / core / infra;
  trusted / untrusted).
- Label every edge whose relation isn't obvious from the endpoints.
- Title the diagram; add a legend when shapes/styles carry meaning.
- Never encode meaning in color alone (accessibility; renders vary).

## 5. Finalize

- Commit the **source**. Optionally export the SVG next to it (same
  `bunx @mermaid-js/mermaid-cli` command) when a rendered file is needed.
- Embedding:
  - GitHub/GitLab render ```` ```mermaid ```` fences in markdown natively —
    inline the source in docs/README where useful.
  - mkdocs needs one-time config; offer to add it:

    ```yaml
    markdown_extensions:
      - pymdownx.superfences:
          custom_fences:
            - name: mermaid
              class: mermaid
              format: !!python/name:pymdownx.superfences.fence_code_format
    ```

- A diagram that drifted from the code is worse than none: when the
  underlying structure changes, update the source in the same PR — that is
  why the source, not the picture, is the committed artifact.
