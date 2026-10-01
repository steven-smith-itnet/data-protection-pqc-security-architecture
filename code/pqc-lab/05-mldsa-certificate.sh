#!/usr/bin/env bash
# Step 5: create a self-signed ML-DSA-65 certificate and inspect it.
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$WORK"

banner "Self-signed ML-DSA-65 certificate (lab root, 30 days)"
run "$OPENSSL" req -x509 -new -newkey ML-DSA-65 -nodes -keyout lab-root.key -out lab-root.crt \
  -days 30 -subj "/O=Example Hospitality Lab/CN=PQC Lab Root ML-DSA-65" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"

banner "Inspect the certificate (public key hex trimmed)"
printf '\n$ %s\n' "$OPENSSL x509 -in lab-root.crt -noout -text | (trimmed)"
"$OPENSSL" x509 -in lab-root.crt -noout -text \
  | awk '/pub:/{print; getline; print; print "                ... (public key bytes trimmed) ..."; skip=1; next}
         skip && /^[ ]+[0-9a-f][0-9a-f]:/ {next}
         /Signature Value:/{print; getline; print; print "        ... (signature bytes trimmed) ..."; skip=1; next}
         {skip=0; print}'

banner "Verify the self-signature"
run "$OPENSSL" verify -CAfile lab-root.crt lab-root.crt

banner "Certificate size comparison (DER bytes)"
"$OPENSSL" x509 -in lab-root.crt -outform DER -out mldsa.der
"$OPENSSL" req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -keyout ec.key -out ec.crt \
  -days 30 -subj "/O=Example Hospitality Lab/CN=PQC Lab Root ECDSA-P256" 2>/dev/null
"$OPENSSL" x509 -in ec.crt -outform DER -out ec.der
"$OPENSSL" req -x509 -new -newkey rsa:3072 -nodes -keyout rsa.key -out rsa.crt \
  -days 30 -subj "/O=Example Hospitality Lab/CN=PQC Lab Root RSA-3072" 2>/dev/null
"$OPENSSL" x509 -in rsa.crt -outform DER -out rsa.der
printf '%-22s %6s bytes\n' "ECDSA P-256 cert" "$(stat -c %s ec.der)"
printf '%-22s %6s bytes\n' "RSA-3072 cert" "$(stat -c %s rsa.der)"
printf '%-22s %6s bytes\n' "ML-DSA-65 cert" "$(stat -c %s mldsa.der)"
