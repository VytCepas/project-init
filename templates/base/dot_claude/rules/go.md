---
description: Go environment and tooling
globs: ["**/*.go", "go.mod", "go.sum"]
alwaysApply: false
---

## Go environment

```bash
go build ./...
go test ./... -count=1
golangci-lint run   # revive, godoclint, gocognit, cyclop, dupl, errcheck, govet, staticcheck, gosec — see .golangci.yml
golangci-lint fmt   # gofumpt (stricter than gofmt) — no separate binary needed
```
