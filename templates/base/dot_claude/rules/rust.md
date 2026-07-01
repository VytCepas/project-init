---
description: Rust environment and tooling
globs: ["**/*.rs", "Cargo.toml", "Cargo.lock"]
alwaysApply: false
---

## Rust environment

```bash
cargo build
cargo test
cargo clippy -- -D warnings -D clippy::pedantic   # revive/complexity gates per clippy.toml
cargo fmt --check                                 # cargo fmt -- writes; --check only verifies
```

The compiler is the type checker — no separate strict-mode gate needed.
`-D warnings` (`.cargo/config.toml`) is the Rust analog to `mypy --strict` /
tsconfig `"strict": true`. Use [`serde`](https://serde.rs/) for structured
data validation — the Rust analog to pydantic/Zod.
