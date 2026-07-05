# Generated Daemon Adapters

> Status: generated | Updated by `python3 -m ampg docs generate` | Applies to: AMPG

This file is generated from code. Do not edit it by hand.


## nginx

- Protocols: clearnet, tor, i2p
- Default policy: `adopt`
- Generated artifacts: server block snippets

Notes:
- Clearnet defaults to adopt because TLS and public vhost policy are operator-owned.
- Tor/I2P HTTP targets can use loopback-only server blocks.

## tor

- Protocols: tor
- Default policy: `auto`
- Generated artifacts: torrc hidden-service snippet

Notes:
- AMPG should preserve existing HiddenServiceDir material when adopting.
- Managed hidden-service keys belong under AMPG state.

## i2pd

- Protocols: i2p
- Default policy: `auto`
- Generated artifacts: i2pd server tunnel snippet

Notes:
- Web tunnels should use web-specific key files.
- Existing RPC/P2P tunnel keys are not reused for web publishing.

## agate

- Protocols: gemini
- Default policy: `auto`
- Generated artifacts: Agate plan values

Notes:
- Gemini serves generated Gemtext output directly.
- Certificate and key paths are plan values until install/apply support exists.
