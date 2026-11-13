# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Each package is
versioned on its own ([Semantic Versioning](https://semver.org/)) and released with the tag
`<package>-vX.Y.Z`.

## [Unreleased]

### Fixed

- `atlas-expression-exploration`: `get_summary.level` exposes its three supported values in the
  MCP input schema and rejects unsupported levels before reading the server settings or query data.
- `atlas-expression-exploration` 0.0.4: stream full-transcriptome library totals in bounded row
  chunks, retaining only query genes and necessary metadata. This avoids loading the full
  atlas, unrelated layers and raw matrices for a small gene query. Missing observation
  columns now name the required server setting before matrix reading begins.

### Added

- Seven standalone server packages (0.0.1): `scrna-analysis` (11 analysis tools), `cellqc`,
  `literature` (4 tools), `variant-annotation`, `phenotype-diagnosis` (3 tools),
  `scgpt-annotation`, and `data-utilities` (2 tools), each with a typed job-status tool,
  independent installation, domain descriptions, regression tests and container definition.
- `common` 0.0.3: confined task workspaces, immutable attempt history, input/configuration
  identities, explicit Slurm/local/inline execution, shared Cell Ranger readers, configured
  model transport, and opt-in strict validation before the MCP SDK can coerce or discard fields.
- Install and container CI covers the new server entry points. Workspace tests use importlib
  collection so separate packages can retain their original test names.

- Community and maintenance files following the AiScientist skills registry: code of conduct,
  security policy, citation, editor and pre-commit configuration, CODEOWNERS, Dependabot, issue
  and pull request templates, `docs/governance.md`, `docs/architecture.md`, `CLAUDE.md`.
- A uv workspace with `uv.lock`. CI runs index, lint (with dependency audit), test (Python 3.12
  and 3.13), pip install and container build gates. The release workflow checks the version,
  pushes the image and publishes a GitHub release.
- A README catalog grouped by category, generated with `servers.json` by `index_servers.py`
  (`--check` in CI).

## visionkb-kg 0.0.1 - Unreleased

### Added

- New server `visionkb-kg` (category `knowledge-graph`): read-only tools over the VisionKB knowledge graph API
  (visionkb-api `/v1`): `search_entities`, `get_entity`, `get_relationships`, `get_evidence`, `get_gene_set`,
  `query_atlas_expression`, `find_datasets`, `get_release`. Each result is the API envelope with `kg_release` and
  `warnings`; failures are `status: "error"` with the API's code, never a fallback. Settings `VISIONKB_API_URL`,
  `VISIONKB_API_TOKEN_FILE` (bearer token read from a file, never logged), `VISIONKB_TIMEOUT_S`. Standard-library
  HTTP; redirects are refused so the token only reaches the configured host. Container
  `containers/visionkb-kg/Dockerfile`; CI install and container gates.
- List results carry `paging` (`returned`, `offset`, `limit`, `total`, `trimmed`, `next_offset`, `trimmed_lists`,
  `summary`). The API may return fewer rows than `limit` to stay within its character cap, so the next page starts
  at `next_offset` (offset + rows returned), not offset + limit. A trimmed page is also flagged in `warnings`.
  Results stay within 24,000 characters (compact JSON); rows are dropped from the end if this client's fields would exceed it.

## common 0.0.2 - 2026-11-04

### Added

- `AISCI_EXECUTOR=inline` runs a job in the foreground, so `submit` returns when it ends. Use it
  when each tool call is a fresh process or container.

### Fixed

- A local job whose process is gone without `done.json` was reported RUNNING if its pid was reused,
  for example in a new container PID namespace. Jobs are now identified by host, pid and start
  time, and a lost job is reported FAILED with a note.
- An unknown `AISCI_EXECUTOR` value is rejected.

## atlas-expression-exploration 0.0.3 - 2026-11-04

### Fixed

- The image had no Helvetica-metric font, so PNG text and figure layout used DejaVu Sans while
  the PDF text was Helvetica. The image now installs Nimbus Sans (`fonts-urw-base35`), and the build
  fails if the figure font does not resolve to it. The Python code is unchanged from 0.0.2.

## atlas-expression-exploration 0.0.2 - 2026-11-04

### Changed

- Requires `aiscientist-mcp-common>=0.0.2`. `submit_query` refreshes a stale state before it reuses
  a query, so a lost local job is resubmitted.

## common 0.0.1 - 2026-11-04

### Added

- Server factory, path checks, a Slurm/local job runner with preemption fallback and a container
  prefix, and the `aiscientist-mcp` CLI client.

## atlas-expression-exploration 0.0.1 - 2026-11-04

### Added

- The first server, with 9 tools. They resolve gene names, run the full-atlas scanpy step, and
  return summaries, scanpy dot, violin and UMAP plots, and a report. It was tested on the HRCA
  snRNA-seq atlas (3.18M nuclei). The category is `single-cell`.
