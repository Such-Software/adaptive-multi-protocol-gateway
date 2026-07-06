# State Contract

> Status: draft | Updated 2026-07-06 | Applies to: managed daemon state

AMPG keeps managed daemon state under `gateway.state_dir`. The state contract describes
which files AMPG owns, which files daemons or adapters write, which paths may contain
private keys, and which public address files `addresses capture` reads.

## Command

```sh
python3 -m ampg --config gateway.toml state-contract
python3 -m ampg --config gateway.toml state-contract --profile mobile-i2p
python3 -m ampg --config gateway.toml state-contract --protocol tor
```

Each `AMPG_STATE` row includes:

- `role`: state directory, daemon config, identity key, address file, log file, or similar.
- `owner`: `ampg`, `daemon`, or `operator`.
- `required`: whether a managed deployment expects the path.
- `sensitive`: whether the path may contain private identity material.
- `path`: resolved path under `gateway.state_dir` unless an adapter documents otherwise.

## Address Capture

`addresses capture` uses the same contract. For each enabled protocol it checks explicit
`address_file` config first, then contract `address-file` entries in order.

Current managed defaults:

| Protocol | Preferred captured address file | Sensitive identity path |
| --- | --- | --- |
| Tor | `<state_dir>/<site>/tor/hidden-service/hostname` | `<state_dir>/<site>/tor/hidden-service` |
| I2P | `<state_dir>/<site>/i2p/hostname.txt` | `<state_dir>/<site>/i2p/<keys_file>` |
| Reticulum/IPFS/custom | `<state_dir>/<site>/<protocol>/address.txt` | adapter-specific |

## Safety

AMPG must never delete sensitive contract paths without an explicit destructive command.
Live apply should copy reviewed config artifacts into their contract `daemon-config`
paths, start daemons, capture public addresses, and then run published health checks.
