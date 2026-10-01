#!/usr/bin/env bash
# Step 4: SLH-DSA (FIPS 205) sign and verify, small (s) and fast (f) parameter sets.
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$WORK"

printf 'Door lock firmware image v4.2.0 manifest (lab)\n' > manifest.txt

for alg in SLH-DSA-SHA2-128s SLH-DSA-SHA2-128f; do
  banner "$alg"
  run "$OPENSSL" genpkey -algorithm "$alg" -out slh.key
  run "$OPENSSL" pkey -in slh.key -pubout -out slh.pub
  start=$(date +%s.%N)
  run "$OPENSSL" pkeyutl -sign -rawin -inkey slh.key -in manifest.txt -out manifest.sig
  end=$(date +%s.%N)
  printf 'signature bytes: %s   sign wall time: %.2f s\n' "$(stat -c %s manifest.sig)" "$(echo "$end - $start" | bc)"
  run "$OPENSSL" pkeyutl -verify -rawin -pubin -inkey slh.pub -in manifest.txt -sigfile manifest.sig
done
