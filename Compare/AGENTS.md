# signal-council contributor instructions

## Scope

- `C:\Users\22673\Desktop\JW\Compare` is the only write scope for this project.
- `Front/`, `Back/`, and the documentation in this directory are the complete project.
- The former `JW/Front` and `JW/Back` are read-only sources. Do not modify them without explicit authorization.
- A new implementation must not import from the former project across directories at runtime. Reused material must first be selected, adapted, and tested inside `Compare`.

## Priorities

1. Preserve a small, runnable, verifiable, and reversible local reference workbench.
2. Reuse verified business logic before adding missing behavior.
3. Prefer simple, fast, and maintainable work; avoid duplicate components, data models, and explanations.
4. Keep one clear change objective per work package and pass its gate before moving on.

## Current maintenance model

- The primary task owns scope, assignment, review, acceptance, and rework decisions. It must not present its own implementation as delegated work.
- Use a single writer for a defined file area. Do not start parallel writers for overlapping files or bypass an acceptance gate.
- Read this file plus the relevant current documentation and Git status before editing.
- Do not commit, push, deploy, delete, or overwrite important files unless explicitly authorized.

## Product truth

- The six dimensions are equally weighted and each is scored from 0 to 100; a higher score is better.
- Keep `scoreGrade`, `decisionGrade`, `confidence`, evidence, and hard-gate decisions separate.
- Missing or unverifiable material lowers confidence or triggers manual review; it does not automatically mean rejection.
- Simulated materials, simulated recognition, and concept images must be explicitly labelled and must never be presented as real AI output or verified business fact.
- The review flow is: original material → advisory candidate or AI-assisted extraction → human business correction or confirmation → risk determination.
- Every displayed business datum must use a stable evidence reference to the precise material location. A filename alone is not enough; use a page, cell range, or region coordinate.
- Unlocatable evidence must be marked pending or unverifiable. Never generate a false highlight or silently map to an approximate location.
- `AI recognition` is a material-extraction capability, not a chat role. The `business`, `risk`, and `leadership` roles are advisory-only. Leadership may govern collaboration only; it has no authority over facts, policy, or hard gates.
- Formal questions, answers, corrections, and follow-ups between business and risk belong in one mutually visible, auditable shared review chain. Drafts do not enter that chain.
- Policy is not a chat role. Versioned, reproducible rules enforce hard constraints; policy displays explain rules, triggering facts, evidence, and results.
- Hard constraints define the permitted range. Soft metrics and AI advice are decision support only and must not be combined with hard-gate outcomes, scores, or chat conclusions.

## Ownership boundaries

- `Front/`: navigation, scrollable views, charts, material preview, interaction state, API adaptation, and Front tests.
- `Back/`: project and material APIs, structured data, evidence links, business corrections, risk determination, file safety, and Back tests.
- Freeze the minimal API contract before separate implementation. Front and Back must not independently invent synonymous fields.

## Working rules

- Inspect the current state and relevant implementation before changing a file.
- Do not install a dependency during the initial maintenance scope without explaining the need, alternatives, and impact and receiving approval.
- Avoid unrelated refactors, bulk copying legacy code, and placeholder architecture.
- Use black, white, and warm grey as the visual base; risk colors must express business meaning.
- Prefer fields and charts; collapse long explanations by default. Do not stack decorative cards.
- When a real preview is unavailable, show an explicit simulated or unavailable state; never use a silent fallback that looks successful.
- When no real model is connected, all agent and extraction outputs must say so. UI wording or animation must not imply that real AI is running.
- Update `STATUS.md` only when its historical-gate role requires it; do not rewrite historical evidence as a current claim.

## Validation

- Report Front, Back, and integration validation separately; none substitutes for another.
- Each acceptance run covers normal, empty, error, and simulated-data states where relevant.
- Preserve source records when integrating existing logic and add regression tests for critical mappings.
- Run `git diff --check` before acceptance. Current commands and runtime guidance belong in the English READMEs and [DEPLOYMENT.md](DEPLOYMENT.md).

## Document roles

- `README.md`: public V1 entry point, scope, limitations, and local-operation links.
- `DEPLOYMENT.md`: Windows local-reference run guide.
- `Front/README.md` and `Back/README.md`: component-specific runtime and contract guidance.
- `ROADMAP.md`, `STATUS.md`, `DECISIONS.md`, `P6-VOICE-HANDOFF.md`, and `Back/evals/`: Chinese historical engineering and evaluation records, not current English V1 operating guides.
