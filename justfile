lint:
    #!/usr/bin/env bash
    if grep -q BAD x.txt; then exit 1; fi
