---
description: Rust environment and tooling
globs: ["**/*.rs", "Cargo.toml", "Cargo.lock"]
alwaysApply: false
---

## Rust environment

```bash
cargo build
cargo test
cargo llvm-cov --fail-under-lines 70              # tests + coverage gate — CI always runs this (`just test-cov`)
cargo audit                                       # dependency CVE/advisory scan (`just audit`) — CI always runs this
cargo clippy -- -D warnings -D clippy::pedantic   # pedantic + cognitive-complexity gate per clippy.toml
cargo fmt --check                                 # verifies only; `cargo fmt` (no flag) writes changes
```

`cargo llvm-cov`/`cargo audit` need `cargo install cargo-llvm-cov cargo-audit`
+ `rustup component add llvm-tools-preview` once locally; CI installs all of
it per-run (prebuilt binaries, not a source compile).

The compiler is the type checker — no separate strict-mode gate needed.
`-D warnings` (`.cargo/config.toml`) is the Rust analog to `mypy --strict` /
tsconfig `"strict": true`. Use [`serde`](https://serde.rs/) for structured
data validation — the Rust analog to pydantic/Zod.
