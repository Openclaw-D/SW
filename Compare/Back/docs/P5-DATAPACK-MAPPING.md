# DataPack mapping and authority boundary

The original core HTTP contract, envelope, error meaning, and Front `Material` union remain compatible. DataPack adds controlled ZIP upload, original reads, material-intelligence candidate operations, and declarative SceneSpec. HTTP failure never requires a Front mock fallback.

At startup, the implementation may apply an idempotent, append-only upgrade to a local database. It adds material/version/evidence/snapshot records while preserving existing fact versions, corrections, shared review, policy history, and approvals. It never deletes an existing database or misrepresents an older database as a new pack.

```text
Authorised external manifest and material
  → SHA-256, classification, authorisation reference, de-identified source reference
  → MaterialVersion
  → provider-neutral strictly validated advisory harness
  → SourceAnchor, observation, field candidate
  → human confirmation command
  → new FactVersion
  → policy/risk/approval reprojection
  → precise evidence return
```

Candidates, observations, and SceneSpec remain advisory. Only the explicit human-confirmation command can create a FactVersion. Synthetic providers have `isSimulated: true`, and response metadata continues to disclose data status, source, and disclaimer.

The API accepts only a safe relative `manifestRef` under `COMPARE_IMPORT_ROOT`; it never returns an absolute path. Manifest `sourceFile` stays relative to its directory without drive roots or `..`; Back recomputes SHA-256 and rejects mismatches without creating a version. Raw material must match the supported Excel/PDF/DOCX/image/real-MP4 union; JSON, SceneSpec, GLB, and provenance remain derived assets and cannot be imported as originals.
