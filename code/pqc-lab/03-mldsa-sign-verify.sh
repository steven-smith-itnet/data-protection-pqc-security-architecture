#!/usr/bin/env bash
# Step 3: ML-DSA-65 key generation, signing, verification, and a tamper test.
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$WORK"

printf 'Folio export batch 2026-09-30, property code LAB01\n' > message.txt

banner "Generate an ML-DSA-65 key pair (throwaway, in a temp dir)"
run "$OPENSSL" genpkey -algorithm ML-DSA-65 -out mldsa65.key
run "$OPENSSL" pkey -in mldsa65.key -pubout -out mldsa65.pub

banner "Sign the message (ML-DSA signs the raw message; no separate digest step)"
run "$OPENSSL" pkeyutl -sign -rawin -inkey mldsa65.key -in message.txt -out message.sig
printf 'signature bytes: %s\n' "$(stat -c %s message.sig)"

banner "Verify with the public key"
run "$OPENSSL" pkeyutl -verify -rawin -pubin -inkey mldsa65.pub -in message.txt -sigfile message.sig

banner "Tamper test: change one character of the message and verify again"
sed 's/LAB01/LAB02/' message.txt > message_tampered.txt
set +e
printf '\n$ %s\n' "$OPENSSL pkeyutl -verify -rawin -pubin -inkey mldsa65.pub -in message_tampered.txt -sigfile message.sig"
"$OPENSSL" pkeyutl -verify -rawin -pubin -inkey mldsa65.pub -in message_tampered.txt -sigfile message.sig 2>&1 | head -2
rc=${PIPESTATUS[0]}
set -e
echo "exit code: $rc (non-zero means verification failed, as expected)"
[ "$rc" -ne 0 ]
