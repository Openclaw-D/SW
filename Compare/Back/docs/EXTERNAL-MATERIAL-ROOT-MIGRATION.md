# External material-root migration guide

This document defines a future authorised migration only. It does not claim that images, contact sheets, native packs, or ZIP archives were moved, copied, deleted, archived, committed, or made public.

When configured, HTTP original preview reads only from the absolute external `COMPARE_MATERIAL_ROOT`, under `native-material-packs/`. That directory is not authoritative fact storage: the manifest and current SQLite `MaterialVersion.contentHash` must match. Any mismatch stops preview.

```text
<COMPARE_MATERIAL_ROOT>/
├── native-material-packs/    API-readable originals and manifests only
├── p5-materials/             historical/mock compatibility assets; not HTTP fallback
└── p5-contact-sheets/        build-time input only; not runtime-loaded
```

No binary fixture is required in Git. Back tests create minimal de-identified manifests and files in temporary directories; Front tests use in-memory contracts.

## Security rules

- Set the root only in a local or deployment environment. Do not put a real username path, archive path, or material path in Git, README examples, SQLite, or responses.
- An unset root reports `originalAccess.status=not_configured`; core project, score, collaboration, and P6 routes remain available.
- Relative paths, unreadable directories, symlink roots, or a missing fixed layout report `invalid_root`; there is no fallback to `COMPARE_IMPORT_ROOT` or `Front/public`.
- The API accepts only manifest-validated project/material/SHA-256 bindings. It does not list directories or accept file paths, URLs, base64, or binary paths.
- The original route rechecks the current content hash and rejects traversal, cross-project access, missing files, and tampering. It does not disclose absolute paths and uses private no-store, `nosniff`, and Range streaming.

## Authorised migration gate

An authorised owner must verify manifests, same-project source paths, SHA-256 values, and a relative-path/size/hash inventory before staging a copy. Validate the staged root with a fresh repository-external SQLite database, a bound image/Excel/PDF original read, HTTP Range/content type/hash, and cross-project/non-imported failures. Then test Front HTTP preview and the truthful unavailable state after unsetting the root. Only after those gates and archive-owner authorisation may original directories be moved or archived.

Rollback means unsetting the variable or pointing it to the previously verified external root. Do not weaken hash validation, rewrite SQLite facts, or use a repository fallback.
