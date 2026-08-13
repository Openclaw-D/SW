# Native material-pack specification

`scripts/build_native_material_packs.py` uses a fixed seed to generate reference inputs for 24 de-identified demonstration projects. Runtime output belongs in ignored `Back/runtime/native-material-packs/`, never in Git. A pack has a package index, per-project ZIP, manifest, business originals, and derived SceneSpec/GLB/provenance assets.

Each reference project has 56 originals: 21 Excel, 14 PDF, and 21 PNG; all have unique SHA-256 values. Derived assets do not enter the manifest or original count. Every project directory and ZIP must be at most 100 MiB; this is a hard gate. All content is `synthetic_demo`, not customer material, public-company fact, or statistical-validation sample.

On a fresh local SQLite seed, matching project ID, material ID, and file hash bind v1 `MaterialVersion.contentHash` to the manifest. Existing databases are append-only: they are neither deleted nor silently rewritten to claim pack binding. A controlled ZIP import accepts only ZIPs within the per-package, extracted-project, and per-original 100 MiB limits; it rejects zip slip, links, duplicate entries, and decompression bombs, then requires manifest preflight and human confirmation.

The source build uses the configured local artifact runtime. It is a development generator, not a public installer, and no dependency is installed by this document. The external material-root guide defines how to make originals optional at runtime without a repository fallback.
