<!--
GENERATED FILE — DO NOT EDIT BY HAND.

Source repo: wsollers/lra-governance
Source commit: 2cacbe0374e5dcfb08d141ec07ab682df6e4473a
Generated from:
- docs/governance/...
- docs/architecture/...
- docs/governance/repo-overlays/lra-reading-categorizer.md

Regenerate from lra-governance.
Emergency downstream edits must be ported upstream before regeneration.
-->

# Claude Instructions

@AGENTS.md

If import semantics are unavailable, use the generated `AGENTS.md` content for
the same repository as the canonical local instruction body.

## Global Agent Rules

- Treat generated instruction files as derived artifacts.
- Follow the owning repository boundary for every task.
- Do not include secrets, credentials, tokens, or machine-local private values.
- Do not modify mathematical content during governance or wrapper-generation tasks.
- Do not touch the retired `Learning-Real-Analysis` monorepo.
- Keep context small: use governance docs as targeted references, not preload material.
- Open only the workflow, standard, schema, or overlay needed for the current task.
- Port emergency downstream instruction repairs back to `lra-governance`.

## Repo Overlay

# lra-reading-categorizer Overlay

This overlay applies to `lra-reading-categorizer`.

## Owned Concerns

`lra-reading-categorizer` owns tooling and metadata for:

- a human-in-the-loop UI for categorizing a local mathematical PDF collection;
- the approved reading subject taxonomy and matching directory scaffold;
- the recoverable SQLite categorization queue;
- review exports that summarize categorization progress;
- conservative copy-only placement of PDFs into managed reading folders.

## Non-Owned Concerns

`lra-reading-categorizer` does not own:

- original PDF files outside the repository;
- source-profile manifests or active-profile exports owned by
  `lra-source-profiles`;
- PDF text extraction, OCR, or bibliography normalization owned by
  `lra-pdf-extractor` or `lra-source-profiles`;
- final LRA note content or bibliography shards;
- canonical predicate / notation / relation YAML;
- theorem explorer internals or generated graph data;
- Lean formalization rules, NURBS / Vulkan / simulation rules, or
  numerical-analysis benchmark rules.

## Project Overlay Abilities

Agents working in this repo may use project-local tools to:

- import a deduplicated categorization queue from reviewed source-profile data;
- maintain the taxonomy under `taxonomy/` and its reference scaffolds under
  `subjects/` and `readings/`;
- update the Python UI under `src/reading_categorizer/`;
- update thin operator entrypoints under `scripts/`;
- export review/progress CSVs under `review/`;
- copy PDFs into managed `readings/<main>/<sub>/` destinations only through the
  repo's explicit save workflow.

These abilities are local collection-management abilities. They do not
authorize direct changes to source-profile manifests, extractor outputs, volume
content, final bibliography shards, canonical YAML, or explorer data.

## Safety Rules

Original PDFs outside the repository, including any configured reading root or
source-profile path, must not be modified, moved, deleted, or renamed.

PDF placement must be copy-only unless the user explicitly asks for a move and
the target/source paths are confirmed. Existing managed PDFs must not be
overwritten silently.

The SQLite queue under `data/` is recoverable local state. Do not commit
machine-local queue databases unless the task explicitly promotes a fixture or
review artifact. Prefer committed taxonomy, source code, tests, docs, and
review exports over transient runtime state.

Classifier output and imported source-profile metadata are hints. Human review
in the UI is the authority for final category/subcategory placement in this
repo.

## Integration Boundary

Outputs from `lra-reading-categorizer` may inform source-profile cleanup,
reading-library organization, or later bibliography work, but integration must
happen through the owning repository's normal review path.

If categorization work reveals that `lra-source-profiles`,
`lra-pdf-extractor`, a volume repo, or governance needs a change, report the
owning repo and required follow-up rather than applying it from this repo.

## Governance Doc Set

Load these governance documents for reading-categorizer work:

- `docs/governance/repo-overlays/lra-reading-categorizer.md`;
- `docs/governance/code-repo-standards.md`;
- `docs/architecture/repository-layout.md`;
- `docs/architecture/multi-repo-sync.md`;
- `docs/governance/repo-overlays/lra-source-profiles.md` only when
  coordinating imported source-profile queue data;
- `docs/governance/repo-overlays/lra-pdf-extractor.md` only when coordinating
  extraction/metadata boundaries.

Use the local `[external:lra-reading-categorizer] README.md`,
`taxonomy/subjects.yaml`, and local tests for operational details.
Shared Python layout and code-style rules live in
`docs/governance/code-repo-standards.md` and are enforced by
`tools/governance/validate_code_repo_layout.py` through the shared
`build-repo` path.

## Provider Notes

Claude should use this wrapper as a pointer to the generated repo instructions.
