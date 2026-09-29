# Production RFC 3161 receipts

Unlike `release_tsa/`, these files come from a public TSA. They are real
receipts, verified offline against the production roots in
`releases/anchors/`, so a test can show which responder certificates the
production pins in `scripts/receipt_pins.py` admit.

`digicert-2026-responder-probe.tsr` is DigiCert's response to a SHA-256
request for the bytes of `digicert-2026-responder-probe.txt`, fetched from
`http://timestamp.digicert.com` on 2026-09-28 (genTime 18:36:12Z). It is
signed by "DigiCert SHA256 RSA4096 Timestamp Responder 2026 1", serial
`084FDC334F7E454EDBC30F8FF9921835`. To fetch a fresh one:

```sh
printf 'tsa pin probe %s' "$(date -u +%F)" > probe.txt
openssl ts -query -data probe.txt -sha256 -cert -no_nonce -out probe.tsq
curl -sS -H 'Content-Type: application/timestamp-query' \
  --data-binary @probe.tsq http://timestamp.digicert.com -o probe.tsr
```
