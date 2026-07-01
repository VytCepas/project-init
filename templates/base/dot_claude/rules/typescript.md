---
description: TypeScript strict type-checking conventions
globs: ["**/*.ts", "**/*.tsx", "tsconfig.json", "tsconfig.base.json"]
alwaysApply: false
---

## TypeScript environment

```bash
bunx tsc --noEmit   # type check (strict mode, per tsconfig.base.json)
bunx eslint .        # lint (no-explicit-any + friends, per eslint.config.mjs)
```

`tsconfig.base.json` is a direct structural analog to `mypy --strict` /
`.golangci.yml`'s strict linters — `strict`, `noUncheckedIndexedAccess`, and
`exactOptionalPropertyTypes` all on. `tsconfig.json` extends it; keep your
own paths/target edits there, not in the base file.

Use [Zod](https://zod.dev/) for runtime boundary validation (parsing
untyped `JSON.parse`/API-response data into a typed shape) — the
TypeScript analog to pydantic/serde. TypeScript's type system is
compile-time only; it does not validate data at runtime on its own.
