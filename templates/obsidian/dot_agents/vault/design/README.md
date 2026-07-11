# design/

Design notes, diagrams, spec drafts. Less formal than `decisions/` — a place for working through problems.

Diagrams get a folder each: `<slug>/` holding the Mermaid `.mmd` source **and**
its rendered `.svg` picture (via mermaid-cli), re-rendered on every source
change (see the `diagram` skill). The `.mmd` source is the artifact of record;
the `.svg` is what a human opens without tooling — both are committed.
