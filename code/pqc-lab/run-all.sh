#!/usr/bin/env bash
# Run every lab step and capture its output under ./output/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$here/output"
for s in "$here"/0[1-8]-*.sh; do
  name="$(basename "$s" .sh)"
  echo "running $name"
  {
    echo "# Captured: $(date -u +%Y-%m-%dT%H:%M:%SZ) on $(uname -sr), $(openssl version)"
    bash "$s"
  } > "$here/output/$name.txt" 2>&1
done
echo "done: outputs in $here/output/"
