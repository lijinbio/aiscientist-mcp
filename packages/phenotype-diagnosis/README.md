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
`PHENOTYPE_MODEL_*`. A truncated peer evidence response is rejected for grading.
