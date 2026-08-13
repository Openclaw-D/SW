# P5-BlindEval

This directory contains one isolated, offline blind evaluation from selected
project-01 source materials to advisory model candidates.

- `generatedBy=codex_isolated_blind_eval`
- `isSimulated=true`
- `advisoryOnly=true`
- `notAProviderCall=true`
- `FactVersionWrites=0`

This is not an HTTP/API/provider integration test. No Provider endpoint was
called. Every candidate remains non-authoritative until explicit human review.
The output contains no score grade, decision grade, confidence override, hard
gate, approval, review transition, or FactVersion write.

## Selected originals

- Image: `runtime/native-material-packs/project-01/originals/现场照片/设备照片/设备总览.png`
- PDF: `runtime/native-material-packs/project-01/originals/租赁标的/融资租赁/融资租赁合同.pdf`
- Excel: `runtime/native-material-packs/project-01/originals/租赁标的/设备清单/设备清单.xlsx`
- Declarative scene: `runtime/native-material-packs/project-01/derived/scene-spec.json`

The frozen blind-run JSON retains its historical hashes and outputs, while the
executable loader rebinds the selected artifact identities, paths and hashes to
the current manifest before validation. The PDF was text-extracted and visually
rendered, the Excel workbook was structurally inspected and rendered, the image
was inspected at original resolution, and the derived SceneSpec was read as data
only; no content was executed.

## Scene schema boundary

The formal `MaterialMediaKind` and `SourceAnchor` union do not define a `scene`
input/anchor kind. Therefore the derived SceneSpec is retained outside the
original-material manifest and used only as the declarative coordinate source for the image result's
`SceneSpec`. Each SceneSpec hotspot is bound to a visually corresponding image
SourceAnchor/locator. No unsupported scene locator was invented.

## Files

- `blind_request.json`: three formal `ModelGatewayRequest` objects plus four
  answer-free material references and the fixed prompt hash.
- `blind_output.json`: three formal `ModelGatewayOutput` objects containing
  formal `MaterialIntelligenceResult` payloads and scene provenance metadata.
- `run_metrics.json`: wall-clock and carrier timing metrics.
- `validate_blind_run.py`: isolated parser and non-authority guard checks.

Run schema validation from `Compare/Back` with a Python environment containing
the declared backend dependencies:

```powershell
python .\evals\model_gateway\blind_run\validate_blind_run.py
```

## Unresolved

- The selected image does not expose a legible manufacturer, model number, or
  nameplate parameters. Those facts are not inferred and remain human-review
  items.
- The formal schema cannot directly bind a SourceAnchor to the scene JSON, as
  described above. This is a contract limitation, not a missing locator guess.
