# Superseded HG-CTI preregistration freezes

The exact V2.0 and V2.1 preregistration/freeze pairs are retained as historical records. Both were created before inference and superseded before any model call or scoring.

- V2.0 preregistration SHA-256: `cae3f032e3c91faae311e92600757463c5f7020d3cea703e3124e2401b641e29`
- V2.0 freeze SHA-256: `745cc564cdaa79c3d7b3543086dde27bbfceed565c9b72d60fe36834dadd8806`
- V2.1 preregistration SHA-256: `27e07fd5214c8fbfd0493d8fc33bc5d8c477303a7a3f5a9674bc13c2d54425f9`
- V2.1 freeze SHA-256: `4a8f5c8ad06269593f9223e20b3367d340fd65658ba1ed67fc1ae1aa2b5cc0ae`

V2.0 was superseded to expand P0 provenance/current-state/claim-ledger regression coverage. V2.1 was superseded to correct a test that asserted the future V2 run directory must remain absent; the historical supersession record is now tested instead, allowing the full test suite to remain valid after a later benchmark run. The active protocol is V2.2. No V2.0 or V2.1 raw run or score exists. No V1 artifact was modified to repair the historical documentation drift.
