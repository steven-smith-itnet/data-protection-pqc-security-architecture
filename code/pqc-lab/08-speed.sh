#!/usr/bin/env bash
# Step 8: short throughput comparison with openssl speed.
# Numbers depend on the CPU, the build, and system load. Treat them as relative only.
set -euo pipefail
source "$(dirname "$0")/common.sh"
SECS="${SECS:-2}"

# Drop the build banner lines so only the result tables remain.
filter() { grep -vE '^(version:|built on:|options:|compiler:|CPUINFO:|Doing |[+])' | sed '/^$/d'; }

banner "CPU"
grep -m1 'model name' /proc/cpuinfo || true

banner "Key establishment: ML-KEM vs X25519 vs RSA-3072 (${SECS}s per test)"
printf '\n$ %s\n' "$OPENSSL speed -seconds $SECS -kem-algorithms ML-KEM-512 ML-KEM-768 ML-KEM-1024"
"$OPENSSL" speed -seconds "$SECS" -kem-algorithms ML-KEM-512 ML-KEM-768 ML-KEM-1024 2>/dev/null | filter
printf '\n$ %s\n' "$OPENSSL speed -seconds $SECS ecdhx25519 rsa3072"
"$OPENSSL" speed -seconds "$SECS" ecdhx25519 rsa3072 2>/dev/null | filter

banner "Signatures: ML-DSA vs ECDSA P-256 vs Ed25519 (${SECS}s per test)"
printf '\n$ %s\n' "$OPENSSL speed -seconds $SECS -signature-algorithms ML-DSA-44 ML-DSA-65 ML-DSA-87"
"$OPENSSL" speed -seconds "$SECS" -signature-algorithms ML-DSA-44 ML-DSA-65 ML-DSA-87 2>/dev/null | filter
printf '\n$ %s\n' "$OPENSSL speed -seconds $SECS ecdsap256 ed25519"
"$OPENSSL" speed -seconds "$SECS" ecdsap256 ed25519 2>/dev/null | filter
