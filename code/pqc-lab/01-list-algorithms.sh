#!/usr/bin/env bash
# Step 1: confirm the OpenSSL build and list the PQC KEM, signature, and TLS group support.
set -euo pipefail
source "$(dirname "$0")/common.sh"

banner "OpenSSL version"
require_openssl_35

banner "KEM algorithms (ML-KEM and hybrid TLS KEMs)"
run "$OPENSSL" list -kem-algorithms

banner "PQC signature algorithms (ML-DSA and SLH-DSA only)"
printf '\n$ %s\n' "$OPENSSL list -signature-algorithms | grep -Ei 'ml-dsa|slh-dsa'"
"$OPENSSL" list -signature-algorithms | grep -Ei 'ml-dsa|slh-dsa'

banner "TLS 1.3 groups offered by this build"
printf '\n$ %s\n' "$OPENSSL list -tls-groups -tls1_3"
"$OPENSSL" list -tls-groups -tls1_3 2>/dev/null || echo "(this build does not support 'list -tls-groups')"
