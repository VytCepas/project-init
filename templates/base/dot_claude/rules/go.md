---
description: Go environment and tooling
globs: ["**/*.go", "go.mod", "go.sum"]
alwaysApply: false
---

## Go environment

```bash
go build ./...
go test ./... -count=1
golangci-lint run   # revive, godoclint, gocognit, cyclop, dupl, errcheck, govet, staticcheck — see .golangci.yml
gofumpt -w .        # stricter than gofmt — same rules plus extra style checks
```
