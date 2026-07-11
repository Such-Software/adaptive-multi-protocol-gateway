# Signed Service Manifests

> Status: draft | Updated 2026-07-11 | Applies to: AMPG service-manifest v1 consumers and producers

`amp.service-manifest.v1` binds one logical service identity to a bounded set of public
transport endpoints. AMPG can validate, inspect, and calculate digests for these manifests.

A valid manifest proves that its signed endpoints were approved by the service key. It does
not make different endpoints equivalent web origins. Browsers and clients must continue to
isolate cookies, storage, credentials, cache, DNS, and connections by transport context.

A self-signed manifest does not bootstrap trust by itself. Clients must pin the service id or
root key through an explicit import, trusted local configuration, QR code, or another authenticated
discovery channel before accepting endpoint updates.

## Contract

The generated JSON Schema is
[`schemas/amp.service-manifest.v1.schema.json`](../schemas/amp.service-manifest.v1.schema.json).
A cross-language golden vector is available at
[`tests/fixtures/amp.service-manifest.v1.golden.json`](../tests/fixtures/amp.service-manifest.v1.golden.json).
A standalone signed example is available at
[`examples/service-manifest.json`](../examples/service-manifest.json).

The signed payload contains:

- a service id derived from the root public key;
- a display name and optional API contract digest;
- one or more public transport endpoints;
- an issue time, expiration time, and monotonic sequence;
- an optional previous-manifest digest for update chaining.

Each route declares its transport, endpoint, matching transport context, maximum public
interaction tier, priority, authentication methods, payment methods, and optional capability
names. `internal` routes are invalid in a service manifest.

The optional delegation envelope lets an offline root key authorize a distinct online signing
key for a bounded time. The service id remains derived from the root key.

## Canonical Bytes And Signatures

The v1 payload uses the [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
with an integer-only I-JSON profile. Floating-point values, duplicate object keys, lone Unicode
surrogates, and integers outside the interoperable I-JSON range are rejected.

AMPG calculates the 32-byte payload digest with tagged SHA-256 using the tag
`AMPG/service-manifest/v1`. The signature is a 64-byte
[BIP-340](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki) Schnorr signature over
that digest using a 32-byte x-only secp256k1 public key.

Service ids use tagged SHA-256 with `AMPG/service-id/v1`. Delegations use
`AMPG/service-key-delegation/v1`.

AMPG implements dependency-free signature verification. It does not generate service private
keys or sign operational manifests. Applications or a hardened external signer own private-key
operations.

## Validation

```sh
python3 -m ampg service-manifest validate service-manifest.json
python3 -m ampg service-manifest validate service-manifest.json \
  --minimum-sequence 7 \
  --minimum-delegation-sequence 3 \
  --expected-previous "$PREVIOUS_DIGEST"
python3 -m ampg service-manifest digest service-manifest.json
python3 -m ampg service-manifest schema --output service-manifest.schema.json
```

Validation checks strict JSON parsing, fields and bounds, service-id derivation, endpoint and
transport compatibility, public-only interaction tiers, time validity, rollback constraints,
delegation bindings, and BIP-340 signatures.

Manifest files are limited to 256 KiB. Consumers should persist the highest accepted manifest and
delegation sequences per pinned service id and supply them during later validation.

`--at <RFC3339>` makes time checks reproducible. `--skip-time` is intended for fixture and
forensic inspection; it does not disable structural or cryptographic checks.

## Manifest Boundaries

AMPG uses three separate contracts:

- `ampg.route-manifest.v1` is unsigned application-owned publication policy input.
- `amp.service-manifest.v1` is signed public service identity and endpoint discovery.
- `ampg.fixture-manifest.v2` contains expected routes for AMPG/AMPB compatibility tests.

The service manifest may contain public capabilities and a reviewed API contract digest. It
must not contain deny rules, internal route names, upstream addresses, daemon keys, credentials,
worker inventory, or deployment notes.

Clients should probe only the selected route or routes the user explicitly approves. Probing
every advertised transport in parallel can correlate one client across networks.
