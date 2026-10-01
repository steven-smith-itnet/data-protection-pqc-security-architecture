#!/usr/bin/env bash
# Shared setup for the PQC lab scripts. Sourced, not executed.
# All keys, certificates, and ciphertexts are throwaway lab material written to a
# temporary directory that is deleted on exit. Nothing generated here is committed.
set -euo pipefail

OPENSSL="${OPENSSL:-openssl}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pqc-lab.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# Print a command, then run it (used so captured output shows exactly what ran).
run() {
  local out="" a
  for a in "$@"; do
    case "$a" in
      *[[:space:]]*) out+=" '$a'" ;;
      *)             out+=" $a" ;;
    esac
  done
  printf '\n$%s\n' "$out"
  "$@"
}

banner() {
  printf '\n==== %s ====\n' "$*"
}

require_openssl_35() {
  local v
  v="$("$OPENSSL" version)"
  echo "$v"
  case "$v" in
    "OpenSSL 3.5"*|"OpenSSL 3.6"*|"OpenSSL 3.7"*|"OpenSSL 4"*) ;;
    *) echo "This lab needs OpenSSL 3.5 or later (ML-KEM, ML-DSA, SLH-DSA)." >&2; exit 1 ;;
  esac
}
