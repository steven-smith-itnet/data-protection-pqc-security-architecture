#!/usr/bin/env bash
# Step 2: ML-KEM-768 key generation, encapsulation, and decapsulation.
# Shows that the sender (encapsulate with the public key) and the receiver
# (decapsulate with the private key) derive the same 32-byte shared secret.
set -euo pipefail
source "$(dirname "$0")/common.sh"
cd "$WORK"

banner "Generate an ML-KEM-768 key pair (throwaway, in a temp dir)"
run "$OPENSSL" genpkey -algorithm ML-KEM-768 -out mlkem768.key
run "$OPENSSL" pkey -in mlkem768.key -pubout -out mlkem768.pub
printf '\n$ %s\n' "$OPENSSL pkey -pubin -in mlkem768.pub -text -noout   (first lines only)"
"$OPENSSL" pkey -pubin -in mlkem768.pub -text -noout > pub.txt
sed -n '1,4p' pub.txt
echo "    ... ($(wc -l < pub.txt) lines in total; encapsulation key trimmed) ..."

banner "Sender: encapsulate to the public key"
run "$OPENSSL" pkeyutl -encap -pubin -inkey mlkem768.pub -out ct.bin -secret ss_sender.bin

banner "Receiver: decapsulate the ciphertext with the private key"
run "$OPENSSL" pkeyutl -decap -inkey mlkem768.key -in ct.bin -out ss_receiver.bin

banner "Sizes (bytes)"
printf 'ciphertext        %s\n' "$(stat -c %s ct.bin)"
printf 'sender secret     %s\n' "$(stat -c %s ss_sender.bin)"
printf 'receiver secret   %s\n' "$(stat -c %s ss_receiver.bin)"
printf 'public key (DER)  %s\n' "$("$OPENSSL" pkey -pubin -in mlkem768.pub -outform DER | wc -c)"

banner "Compare shared secrets"
sender_hex="$(xxd -p -c 64 ss_sender.bin)"
receiver_hex="$(xxd -p -c 64 ss_receiver.bin)"
echo "sender   : $sender_hex"
echo "receiver : $receiver_hex"
if cmp -s ss_sender.bin ss_receiver.bin; then
  echo "RESULT: shared secrets MATCH"
else
  echo "RESULT: shared secrets DIFFER" >&2
  exit 1
fi

banner "Negative test: decapsulate a ciphertext with one flipped byte"
cp ct.bin ct_tampered.bin
printf '\xff' | dd of=ct_tampered.bin bs=1 seek=100 conv=notrunc status=none
run "$OPENSSL" pkeyutl -decap -inkey mlkem768.key -in ct_tampered.bin -out ss_tampered.bin
echo "tampered : $(xxd -p -c 64 ss_tampered.bin)"
if cmp -s ss_sender.bin ss_tampered.bin; then
  echo "RESULT: unexpected match" >&2; exit 1
else
  echo "RESULT: tampered ciphertext yields an unrelated secret (implicit rejection); no error is raised"
fi
