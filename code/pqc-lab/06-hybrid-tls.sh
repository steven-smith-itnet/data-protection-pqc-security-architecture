#!/usr/bin/env bash
# Step 6: local TLS 1.3 handshake with hybrid key exchange X25519MLKEM768.
# Runs s_server on localhost with a throwaway ML-DSA-65 certificate, then s_client.
# A second run pins the classical X25519 group for comparison, and a third run
# uses an ECDSA certificate to show that key exchange and authentication are independent.
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$WORK"
PORT="${PORT:-14433}"

"$OPENSSL" req -x509 -new -newkey ML-DSA-65 -nodes -keyout srv.key -out srv.crt -days 1 \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" 2>/dev/null
"$OPENSSL" req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -keyout srv-ec.key \
  -out srv-ec.crt -days 1 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" 2>/dev/null

handshake() {
  local label="$1" cert="$2" key="$3" sgroups="$4" cgroups="$5"
  banner "$label"
  "$OPENSSL" s_server -accept "$PORT" -cert "$cert" -key "$key" -tls1_3 -groups "$sgroups" \
    -www -quiet >/dev/null 2>&1 &
  local spid=$!
  sleep 1
  printf '\n$ %s\n' "$OPENSSL s_server -accept $PORT -cert $(basename "$cert") -key $(basename "$key") -tls1_3 -groups $sgroups -www -quiet &"
  printf '$ %s\n' "echo Q | $OPENSSL s_client -connect localhost:$PORT -tls1_3 -groups $cgroups -CAfile $(basename "$cert") -servername localhost -msg"
  echo Q | "$OPENSSL" s_client -connect "localhost:$PORT" -tls1_3 -groups "$cgroups" \
      -CAfile "$cert" -servername localhost -msg > client.log 2>&1 || true
  echo "  (handshake messages)"
  grep -E '^(>>>|<<<) TLS 1.3, Handshake .*(ClientHello|ServerHello)' client.log | sed 's/^/    /' || true
  echo "  (negotiated parameters)"
  grep -E '^(Negotiated TLS1.3 group|Peer Temp Key|Peer signature type|Peer signing digest|Server public key|SSL handshake has read|Verification|New,)' client.log \
    | sort -u | sed 's/^/    /' || true
  kill "$spid" 2>/dev/null || true
  wait "$spid" 2>/dev/null || true
}

handshake "Hybrid PQ: X25519MLKEM768 key exchange, ML-DSA-65 server certificate" \
  srv.crt srv.key "X25519MLKEM768" "X25519MLKEM768"
handshake "Classical comparison: X25519 key exchange, ML-DSA-65 server certificate" \
  srv.crt srv.key "X25519" "X25519"
handshake "Most common near-term deployment: X25519MLKEM768 with an ECDSA P-256 certificate" \
  srv-ec.crt srv-ec.key "X25519MLKEM768:X25519" "X25519MLKEM768:X25519"
handshake "Fallback: client offers hybrid then X25519, server supports only X25519" \
  srv-ec.crt srv-ec.key "X25519" "X25519MLKEM768:X25519"

banner "ClientHello and ServerHello sizes: hybrid vs classical key share"
printf '%-16s %18s %18s\n' "group" "ClientHello bytes" "ServerHello bytes"
for g in X25519 X25519MLKEM768; do
  "$OPENSSL" s_server -accept "$PORT" -cert srv-ec.crt -key srv-ec.key -tls1_3 -groups "$g" -www -quiet >/dev/null 2>&1 &
  spid=$!
  sleep 1
  echo Q | "$OPENSSL" s_client -connect "localhost:$PORT" -tls1_3 -groups "$g" -CAfile srv-ec.crt \
      -servername localhost -msg > size.log 2>&1 || true
  ch_hex="$(grep -m1 -E '^>>> TLS 1.3, Handshake .*ClientHello' size.log | sed -E 's/.*length ([0-9a-f]+).*/\1/')"
  sh_hex="$(grep -m1 -E '^<<< TLS 1.3, Handshake .*ServerHello' size.log | sed -E 's/.*length ([0-9a-f]+).*/\1/')"
  printf '%-16s %18d %18d\n' "$g" "$((16#$ch_hex))" "$((16#$sh_hex))"
  kill "$spid" 2>/dev/null || true
  wait "$spid" 2>/dev/null || true
done
echo "Sizes are handshake message bodies as reported by s_client -msg (record headers excluded)."
