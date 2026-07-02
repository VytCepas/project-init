---
description: Go environment and tooling
globs: ["**/*.go", "go.mod", "go.sum"]
alwaysApply: false
---

## Go environment

```bash
go build ./...
go test ./... -count=1
just test-cov       # tests + coverage gate (>= 70%, per justfile) — CI always runs this
just audit          # dependency CVE/advisory scan (govulncheck) — CI always runs this
golangci-lint run   # revive, godoclint, gocognit, cyclop, dupl, errcheck, govet, staticcheck, gosec — see .golangci.yml
golangci-lint fmt   # gofumpt (stricter than gofmt) — no separate binary needed
```

`govulncheck` (`go install golang.org/x/vuln/cmd/govulncheck@latest`) only
reports vulnerabilities actually reachable from your code, not every
advisory touching a transitive dependency — a lower false-positive rate than
a plain dependency-list scan.
