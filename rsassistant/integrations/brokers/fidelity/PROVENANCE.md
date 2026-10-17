# Fidelity adapter provenance

* Source of broker automation: nested fork `braydio/auto-rsa` at `110439c`
  (`src/brokerages/fidelity_api.py`, Zendriver), tag `baseline/auto-rsa-deployed-110439c`.
  Upstream family: NelsonDane/auto-rsa. **License: GPL-3.0** (`auto-rsa/LICENSE`).
* Nothing from that file has been copied into this repository. Any future
  extraction must keep the GPL notice and be a deliberate owner decision (it
  affects how RSAssistant itself may be licensed/distributed).
* `adapter.py` here is original code reading the auto-rsa JSON snapshot only.
* No credentials, cookies or browser profiles belong in fixtures.
