# phenotype-diagnosis

Standalone MCP server for grounded clinical-text-to-HPO mapping, LIRICAL disease ranking and literature-based differential adjudication. It has no `aiscientist`, HarnessTool, app settings or gateway dependency.

Scientific algorithms, prompts and the bundled HPO lexicon are migrated from AiScientist commit `48f64a6be1b9f44eb2948eea1ac448df6a4219e2`, from `map_phenotype_to_hpo`, `run_lirical`, and `diagnose_disease`. The lexical matcher, closed-set model selection, obsolete-ID replacement, LIRICAL TSV parsing, evidence grading and adjudication retain the original tests.

## Tools

| Tool | Inputs | Result |
|---|---|---|
| `map_phenotype_to_hpo` | `text`, optional `k=8` | Grounded observed/excluded terms, labels, ontology version, unmapped phrases, mode and warnings |
| `run_lirical` | `hpo_terms`, optional `excluded_hpo`, `sample_id`, `vcf_path` | LIRICAL candidates, original post-test probabilities, scoring mode and TSV path |
| `diagnose_disease` | Same inputs plus `candidate_genes`, `max_literature_queries=6` | Adjudicated differential and evidence, with original LIRICAL probabilities retained |
| `phenotype_job_status` | `analysis_id`, `task_id` | Current state and original result/error |

The three action tools also accept `analysis_id="default"` and `rerun=false`. Arguments are validated against the advertised native schema before the SDK can coerce types or discard unknown fields. Credentials, commands and reference paths are server settings, not tool arguments. `vcf_path` is explicitly supplied; there is no app dataset fallback.

All writes are confined to `AISCI_DATA_DIR/phenotype-diagnosis/<analysis_id>/`, including `work/`, `artifacts/phenotype/`, and durable `jobs/<task_id>/` requests/results. One operation writes each analysis at a time. Repeated identical successful/current requests reuse the job; `rerun=true` creates a new attempt. LIRICAL gets a unique TSV prefix each attempt, so a missing new output cannot reuse an old ranking. Input metadata and configuration participate in job identity.

`AISCI_EXECUTOR=inline|local|slurm` uses the common jobs runtime. Inline completion returns the original result plus `analysis_id`, `task_id`, `job_id`, `state`; asynchronous calls return task identity/state until polled. Non-success scientific results produce `FAILED` jobs. Failed action calls are MCP errors containing the task ID; status queries retain the diagnostic result. Missing deployments never produce invented rankings. Large native MCP responses contain bounded candidate/evidence previews, the unchanged total counts and `full_result` pointing to the complete persisted result; this also applies to status calls.

## Server settings

| Variable | Meaning |
|---|---|
| `AISCI_DATA_DIR` | Write root (default `./data`) |
| `AISCI_EXECUTOR` | `slurm` by default; `inline` for synchronous execution, `local` for a child worker |
| `AISCI_SLURM` | Common Slurm options; default 4 CPU, 16 GB, 4 hours |
| `PHENOTYPE_ALLOWED_ROOTS` | OS path-separated read roots for explicit VCF, HPO lexicon and LIRICAL references |
| `PHENOTYPE_HPO_LEXICON` | Optional replacement lexicon; default is packaged `hpo/hpo_lexicon.tsv.gz` |
| `LIRICAL_DATA_DIR` | Staged LIRICAL reference directory (`hp.json`, `phenotype.hpoa`, HGNC, transcript references) |
| `LIRICAL_COMMAND` | Administrator-configured argv string, parsed without a shell; default `lirical` |
| `LIRICAL_ASSEMBLY` | Default `hg38`; accepts original GRCh37/hg19 and GRCh38/hg38 aliases |
| `LIRICAL_EXOMISER_HG19`, `LIRICAL_EXOMISER_HG38` | Optional matching Exomiser data directories; genotype-aware scoring needs both VCF and matching DB |
| `LIRICAL_TIMEOUT` | Command timeout in seconds, default 14400 |
| `PHENOTYPE_MODEL_ENDPOINT`, `PHENOTYPE_MODEL` | Explicit OpenAI-compatible base URL and model for HPO extraction/closed-set selection |
| `PHENOTYPE_MODEL_API_KEY_FILE` | Preferred server credential source, read by worker; overrides `PHENOTYPE_MODEL_API_KEY` |
| `PHENOTYPE_MODEL_TIMEOUT` | Model request timeout in seconds, default 180 |
| `PHENOTYPE_MODEL_MAX_TOKENS` | Positive response token limit for HPO model mapping; default 10000, configure lower for smaller model contexts |
| `PHENOTYPE_LITERATURE_COMMAND` | Explicit stdio MCP server command for the literature evidence track; unset means LIRICAL-only |
| `PHENOTYPE_LITERATURE_TIMEOUT` | Total time allowed for each literature query/poll sequence, default 14400 seconds |

There is no default public model endpoint. A keyless configured local endpoint is supported. Without a model the original conservative lexical fallback operates; text with negation/family history returns `mode="needs_llm"` with no asserted terms. Model extraction expects a JSON array, so this client does not force `response_format=json_object`. Key files/values are absent from job requests and model identity, and failures never echo request headers or response bodies.

`PHENOTYPE_LITERATURE_COMMAND` can be a separately installed `literature-mcp` or an administrator-owned SSH/Apptainer wrapper. The child inherits server environment; configure that server's `LITERATURE_*` model/corpus settings there. The bridge calls `deep_literature` and polls `literature_job_status` over real MCP with a distinct deterministic analysis ID per case/question. It never reads the other service's output directory and carries no PaperQA dependency. Network behavior is entirely that of the explicitly configured endpoints/commands; clinical phenotype phrases enter the literature question. The original evidence adapter distinguishes no retrieved evidence from unsupportive/refuting evidence, and retains the citations/passages supporting grades.

## Run

```sh
uv sync --package aiscientist-mcp-phenotype-diagnosis
export AISCI_EXECUTOR=inline
export AISCI_DATA_DIR=/srv/aiscientist/outputs
export PHENOTYPE_ALLOWED_ROOTS=/srv/references:/srv/inputs
export LIRICAL_DATA_DIR=/srv/references/lirical
uv run --package aiscientist-mcp-phenotype-diagnosis phenotype-diagnosis-mcp
```

```sh
aiscientist-mcp --server phenotype-diagnosis-mcp call map_phenotype_to_hpo \
  '{"text":"Patient has night blindness and tunnel vision","analysis_id":"synthetic-case"}'
aiscientist-mcp --server phenotype-diagnosis-mcp call run_lirical \
  '{"hpo_terms":["HP:0000662","HP:0001133"],"analysis_id":"synthetic-case"}'
```

The Dockerfile includes pinned LIRICAL 2.4.1 and Java 17. Reference data and Exomiser databases remain external read-only mounts. For an existing SIF, set `LIRICAL_COMMAND` to a wrapper which binds the admitted reference/input roots and the analysis output root; the wrapper must pass argv unchanged. Set Slurm environment/modules in the service wrapper as usual.

## Validation

The standalone suite covers original scientific parity, strict MCP schema/calls, actual stdio server and inline workers, a subprocess producing synthetic LIRICAL TSV, error states, stale TSV rejection, path confinement, explicit model HTTP array responses and credential exclusion, and an actual separate MCP literature fixture with polling/evidence grading. These are synthetic local tests; real cluster ranking and real model/corpus checks are reported separately, never implied by fixture results.

The supplied phenotype image also installs the literature package and fixes
`PHENOTYPE_LITERATURE_COMMAND=literature-mcp`. Configure the same `LITERATURE_*`
corpus, local embedding, index and explicit model settings described in the
literature README; the peer runs through stdio MCP with an independent literature
analysis namespace. To request a phenotype-only ranking, use `run_lirical` or
`diagnose_disease(max_literature_queries=0)`. The app bridge forwards approved
literature data/model settings and mounts references read-only; it never accepts
an executable override from a tool call. `diagnose_disease` binds the trusted
session model to the peer's `LITERATURE_MODEL_*` settings, while HPO mapping uses
`PHENOTYPE_MODEL_*`. A truncated peer evidence response is never graded directly. Version 0.0.4
reads the literature peer's bounded `literature://results/...` MCP resource pages,
checks task identity, size, contiguous offsets and SHA-256, then grades the complete
JSON. Missing, oversized or inconsistent evidence remains an explicit ungraded
error. No peer workspace is read directly, even in the bundled container.

Website run 36dba619cd19 exercised 0.0.3 with the selected Haiku model: HPO mapping
and LIRICAL completed, but the literature peer's preview was truncated, so the
8,621-row differential remained LIRICAL-only. This is failure evidence for the
integration, not successful literature adjudication. The 0.0.4 resource repair is
covered by real stdio tests with large synthetic evidence; released-image and
website model acceptance must be recorded separately.

## Real HPC validation (2026-11-12)

Actual MCP stdio calls used source-staged standalone packages, the lab's existing
LIRICAL SIF/references and synthetic HPO inputs. Phenotype-only LIRICAL and
`diagnose_disease(max_literature_queries=0)` each retained all 8,621 candidates;
native protocol previews measured 6,576 and 14,770 bytes, respectively. These
checks used the installed lab SIF, not a verified version probe of that SIF.

An isolated authenticated school Qwen3.8-27B-INT4 service also completed HPO text
mapping in 10.44 seconds, returning two observed terms and one excluded hearing
loss term for synthetic text. A separate native literature MCP process then
supplied real corpus evidence to `diagnose_disease`: the completed 327.83-second
call retained 8,621 LIRICAL candidates plus one graded PRPF31 literature record,
with a 15,079-byte protocol preview and the full result saved separately. The
algorithm capped the model's proposed evidence grade to `LIMITED` because only
one independent source was retrieved. This is the tool's research heuristic,
not an official ClinGen classification or patient validation; citations were
DOI-based and had no PMID field. In this existing grading path, the `quote`
fields retain PaperQA summaries rather than verified verbatim excerpts; use
`search_corpus` and the original document when checking exact wording.

The first cross-service run with `evidence_k=2` returned no relevant contexts and
remained ungraded. The successful bounded rerun used evidence_k=8,
search_count=6 and max_sources=4. Evidence breadth is a deployment choice, not a
reason to conceal empty retrieval or represent a partial review as exhaustive.
The local Docker image's own phenotype CLI and bundled literature CLI both
passed actual stdio tool enumeration.

The final fork prerelease `phenotype-diagnosis-v0.0.2` also passed actual MCP stdio
acceptance from its installed wheels, with no source override (Python 3.12.16).
OCI digest:
`sha256:7da799af643c5ff03e2dd568f5d6db58b268915be64323d3c31630a7d8a670c2`;
converted SIF SHA-256:
`717c118c27bb87b792e2f66b2f7ff881bc2da2ea64e7f925456a475f3dc2e52f`.
HPO mapping, LIRICAL and model-backed diagnosis completed in 11.13, 9.18 and
371.24 seconds respectively. Diagnosis preserved all 8,621 candidates and one
graded literature record obtained through the bundled independent literature
MCP process; its native response was 15,287 bytes with the complete result saved
separately. Status polling and invalid type/unknown argument rejection passed.
The clinical text and HPO terms were synthetic; the references, corpus retrieval
and isolated authenticated model service were real.

Reproduce acceptance with
`containers/literature/validate_hpc.py phenotype --image ... --output ...
--corpus ... --binding ... --lirical-data ...` in an authorized CPU allocation.
The script hashes the supplied SIF, removes inherited source overrides, calls
its installed native CLIs, checks model mapping and real cross-MCP evidence, and
rejects an ungraded/error result as an end-to-end pass. Model tests used an
isolated vLLM service; native Anthropic and strict public OpenAI compatibility
remain unverified, and the application's guarded BYOK workflow remains available.
