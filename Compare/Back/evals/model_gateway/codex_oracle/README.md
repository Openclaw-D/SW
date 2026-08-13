# P5-MG-CodexOracle

This directory is a fixed, offline, project-01 oracle artifact. It is not a
product Provider, route, live model invocation, or authority-writing service.

Inspected inputs are limited to four representative files under the existing
`runtime/native-material-packs/project-01` pack:

- image: the 2048x1152 local synthetic equipment overview; the focal machine
  area and the synthetic caption were visually checked;
- PDF: the one-page synthetic lease contract; it was rendered and the contract
  number, equipment, quantity, total, financing amount, down payment and term
  rows were visually checked;
- Excel: `设备清单!A1:I4`; it was imported and rendered, with the source row at
  row 4 and exact cell locators retained;
- SceneSpec: the declarative-only JSON containing the frozen factory, equipment
  and process point positions.

`replay_fixture.json` keeps the formal request and expected
`ModelGatewayOutput` separate. `build_model_input()` exposes only the request.
The request `inputHash` is the SHA-256 of the exact source file, so the hash can
be recomputed without using expected output data. All outputs remain simulated,
advisory candidates and expect zero `FactVersion` writes.
