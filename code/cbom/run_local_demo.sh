#!/usr/bin/env bash
# Reproduce the captured CBOM samples in sample-output/ against local OpenSSL servers.
#
# Starts four throwaway `openssl s_server` instances on 127.0.0.1:
#   14433  P-256 ECDSA certificate, key exchange limited to X25519MLKEM768 (hybrid PQ)
#   14434  P-256 ECDSA certificate, key exchange limited to X25519 (classical only)
#   14435  ML-DSA-65 certificate, key exchange limited to X25519MLKEM768 (PQ key exchange and PQ signature)
#   14436  RSA-3072 certificate, TLS 1.3 disabled (legacy TLS 1.2 terminator)
# then runs cbom_scan.py against each and against the throwaway certificates.
#
# Requires OpenSSL 3.5 or later. Keys and certificates are created in a temp
# directory and deleted on exit; nothing secret is written to the repo.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${HERE}/sample-output"
PY="${PYTHON:-python3}"
WORK="$(mktemp -d)"
PIDS=()
cleanup() {
  for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done
  rm -rf "$WORK"
}
trap cleanup EXIT
mkdir -p "$OUT"

openssl version | tee "$OUT/openssl-version.txt"

openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 30 \
  -subj "/CN=pms-api.example.test" -keyout "$WORK/ec.key" -out "$WORK/ec.pem" 2>/dev/null
openssl req -x509 -newkey ML-DSA-65 -nodes -days 30 \
  -subj "/CN=pq-gateway.example.test" -keyout "$WORK/mldsa.key" -out "$WORK/mldsa.pem" 2>/dev/null
openssl req -x509 -newkey rsa:3072 -nodes -days 3650 \
  -subj "/CN=Example Legacy Root CA" -keyout "$WORK/rsa.key" -out "$WORK/rsa-root.pem" 2>/dev/null

start() { # port cert key groups
  openssl s_server -accept "$1" -cert "$2" -key "$3" -groups "$4" -www -quiet >/dev/null 2>&1 &
  PIDS+=($!)
}
start 14433 "$WORK/ec.pem" "$WORK/ec.key" X25519MLKEM768
start 14434 "$WORK/ec.pem" "$WORK/ec.key" X25519
start 14435 "$WORK/mldsa.pem" "$WORK/mldsa.key" X25519MLKEM768
openssl s_server -accept 14436 -cert "$WORK/rsa-root.pem" -key "$WORK/rsa.key" -no_tls1_3 -www -quiet >/dev/null 2>&1 &
PIDS+=($!)
sleep 1

run() { # name args...
  local name="$1"; shift
  "$PY" "$HERE/cbom_scan.py" "$@" -o "$OUT/$name.json" 2> "$OUT/$name.findings.txt"
  echo "== $name"; cat "$OUT/$name.findings.txt"
}
run cbom-hybrid-pq        --endpoint 127.0.0.1:14433 --servername pms-api.example.test --probe-pq
run cbom-classical-x25519 --endpoint 127.0.0.1:14434 --servername pms-api.example.test --probe-pq
run cbom-mldsa-cert       --endpoint 127.0.0.1:14435 --servername pq-gateway.example.test --probe-pq
run cbom-legacy-tls12     --endpoint 127.0.0.1:14436 --servername legacy.example.test --probe-pq
# Relative paths so the CBOM records file names, not the temp directory.
(cd "$WORK" && run cbom-local-certs --cert-file rsa-root.pem --cert-file mldsa.pem)
