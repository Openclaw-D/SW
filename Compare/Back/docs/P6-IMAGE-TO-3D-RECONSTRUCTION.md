# Image-to-3D reconstruction boundary

V1 has no executable real-photo reconstruction engine. Declarative SceneSpec and any GLB are derived reference artifacts only. They do not prove a one-to-one match to an asset or site and are not surveying, manufacturer CAD, scanning, COLMAP output, neural reconstruction, 3D Gaussian Splatting, or verified image-to-3D output.

Any isolated job API must report `unavailable` on the default local path unless an independently authorised and validated reconstruction engine, input provenance, output validation, storage policy, and Front integration are implemented. It must not generate or imply a real 3D asset from a concept image, static reference image, demo material, or synthetic text.

The contract boundary is intentionally strict: source material remains project-scoped and version/hash-bound; a job can be advisory only; output cannot write facts, evidence, scores, confidence, policy, hard gates, or approvals; and every UI state must disclose simulated, unavailable, or unverified provenance. V1 makes no real reconstruction, engine, API, Front-wiring, or independent-asset-validation claim.
