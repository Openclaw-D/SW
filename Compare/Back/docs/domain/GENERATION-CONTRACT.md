# Deterministic generation contract

`app.services.generation.create_workbench_generator(settings)` returns the `WorkbenchGenerator` for the local reference dataset. It generates deterministic, de-identified demonstration projects from configured seed and domain rules; it is not a real-customer data importer, statistical model, or risk-decision engine.

The generator preserves the six equal 0–100 dimensions, higher-is-better semantics, separate score/decision/confidence/evidence/hard-gate fields, and simulated-data provenance. It must not turn missing or unverifiable material into automatic rejection. Generated facts remain subject to Back versioning and human-authority contracts.

Generation input, output, seed, and source/disclaimer fields are part of the local deterministic contract. Any future real-data ingestion, statistical calibration, or production model work requires an independent contract and validation gate.
