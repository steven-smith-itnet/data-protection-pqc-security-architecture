#!/usr/bin/env bash
# Step 7: measure public key, private key, and signature/ciphertext sizes from real files.
# DER sizes include ASN.1/SPKI wrapping, so they are slightly larger than raw FIPS sizes.
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$WORK"
printf 'size test message\n' > msg.txt

printf '%-20s %12s %12s %16s\n' "Algorithm" "PubKey DER" "PrivKey DER" "Sig/CT bytes"
printf '%-20s %12s %12s %16s\n' "---------" "----------" "-----------" "------------"

sig_row() {
  local name="$1"; shift
  "$OPENSSL" genpkey "$@" -out k.pem 2>/dev/null
  local pub priv sig
  pub=$("$OPENSSL" pkey -in k.pem -pubout -outform DER | wc -c)
  priv=$("$OPENSSL" pkey -in k.pem -outform DER | wc -c)
  case "$name" in
    RSA*|ECDSA*) "$OPENSSL" pkeyutl -sign -rawin -digest sha256 -inkey k.pem -in msg.txt -out s.bin ;;
    *)           "$OPENSSL" pkeyutl -sign -rawin -inkey k.pem -in msg.txt -out s.bin ;;
  esac
  sig=$(stat -c %s s.bin)
  printf '%-20s %12s %12s %16s\n' "$name" "$pub" "$priv" "$sig (sig)"
}

kem_row() {
  local name="$1"; shift
  "$OPENSSL" genpkey "$@" -out k.pem 2>/dev/null
  "$OPENSSL" pkey -in k.pem -pubout -out p.pem
  local pub priv ct
  pub=$("$OPENSSL" pkey -in k.pem -pubout -outform DER | wc -c)
  priv=$("$OPENSSL" pkey -in k.pem -outform DER | wc -c)
  case "$name" in
    RSA*)
      head -c 32 /dev/urandom > sym.bin
      "$OPENSSL" pkeyutl -encrypt -pubin -inkey p.pem -pkeyopt rsa_padding_mode:oaep \
        -pkeyopt rsa_oaep_md:sha256 -in sym.bin -out ct.bin ;;
    X25519)
      # ECDH has no ciphertext; the peer sends its public key (32 raw bytes).
      printf '%-20s %12s %12s %16s\n' "$name" "$pub" "$priv" "32 (peer share)"; return ;;
    *) "$OPENSSL" pkeyutl -encap -pubin -inkey p.pem -out ct.bin -secret ss.bin ;;
  esac
  ct=$(stat -c %s ct.bin)
  printf '%-20s %12s %12s %16s\n' "$name" "$pub" "$priv" "$ct (ct)"
}

echo "Key establishment"
kem_row "RSA-3072 (OAEP)"  -algorithm RSA -pkeyopt rsa_keygen_bits:3072
kem_row "X25519"           -algorithm X25519
kem_row "ML-KEM-512"       -algorithm ML-KEM-512
kem_row "ML-KEM-768"       -algorithm ML-KEM-768
kem_row "ML-KEM-1024"      -algorithm ML-KEM-1024
echo
echo "Signatures"
sig_row "RSA-3072"          -algorithm RSA -pkeyopt rsa_keygen_bits:3072
sig_row "ECDSA P-256"       -algorithm EC -pkeyopt ec_paramgen_curve:P-256
sig_row "Ed25519"           -algorithm ED25519
sig_row "ML-DSA-44"         -algorithm ML-DSA-44
sig_row "ML-DSA-65"         -algorithm ML-DSA-65
sig_row "ML-DSA-87"         -algorithm ML-DSA-87
sig_row "SLH-DSA-SHA2-128s" -algorithm SLH-DSA-SHA2-128s
sig_row "SLH-DSA-SHA2-128f" -algorithm SLH-DSA-SHA2-128f
echo
echo "Note: ECDSA signatures are DER-encoded and vary by a byte or two between runs."
echo "Note: OpenSSL 3.5 ML-KEM/ML-DSA private key DER may contain both seed and expanded key."
