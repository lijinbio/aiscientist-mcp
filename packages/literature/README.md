# literature

Independent MCP tools for biomedical citation search, hybrid corpus retrieval, PaperQA answers,
and evidence-checked whole-corpus gene curation. The scientific implementation is ported from
AiScientist `48f64a6be1b9f44eb2948eea1ac448df6a4219e2`; the package imports no AiScientist application
or HarnessTool code.

| Tool | Main arguments | Result |
| --- | --- | --- |
| `literature_search` | `query`, `limit`, `pubmed_only`, `abstracts` | Europe PMC citations, optional abstracts |
| `search_corpus` | `queries`, `top_k`, `max_per_paper`, `terms`, `pmids` | Verbatim passages, PMID/page/citation, hybrid retrieval diagnostics |
| `deep_literature` | `question` | PaperQA answer and supporting contexts; empty evidence is a failure |
| `extract_haploinsufficient_genes` | retrieval/pilot settings, `pmids`, optional typed `spec` | Verified `genes.csv`, `hits.csv`, `requests.csv`, warnings and review flags |
| `literature_job_status` | `analysis_id`, `task_id` | Job state, original result or diagnostic failure |

All four analysis tools accept `analysis_id` (default `default`) and `rerun` (default false).
Their outputs live under `$AISCI_DATA_DIR/literature/<analysis_id>/`: `work/`, `artifacts/`,
`jobs/<task_id>/request.json`, `result.json`, `state.json`, `done.json` and job logs. IDs are validated;
symlink escapes are refused. A workspace binds its corpus version and model identity so old model
judgments are not silently reused against another corpus or endpoint. Use a new analysis ID to change
those inputs. Repeating the current completed request reuses its result; `rerun=true` creates a new attempt.
Failed attempts remain individually addressable by task ID.

## Install and run

From the repository:

```bash
uv sync --all-packages
uv run literature-mcp
# Full local retrieval, PDF extraction and PaperQA dependencies:
uv sync --all-packages --extra full
# Or from a clean interpreter:
pip install ./packages/common './packages/literature[full]'
```

Configure a corpus root containing `papers/`, `mechanism_cache/chunks.jsonl`,
`mechanism_cache/sentences.jsonl`, optional `chunk_vecs.npy`, `paperqa_manifest.csv`,
`hgnc_complete_set.txt`, `hf_cache/`, and the prebuilt PaperQA `index_pubmedbert/` directory:

```bash
export LITERATURE_CORPUS_ROOT=/path/to/corpus
export AISCI_DATA_DIR=/path/to/results
export AISCI_EXECUTOR=slurm
export AISCI_SLURM='--partition=<partition> --cpus-per-task=4 --mem=16G --time=04:00:00'
export AISCI_JOB_PREFIX='apptainer exec --bind /path/to/corpus:/path/to/corpus:ro,/path/to/results /path/to/literature.sif'
aiscientist-mcp --server literature-mcp call search_corpus \
  '{"queries":["Does loss of one PRPF31 copy cause retinitis pigmentosa?"],"analysis_id":"example"}'
# Poll with the returned task_id:
aiscientist-mcp --server literature-mcp call literature_job_status \
  '{"analysis_id":"example","task_id":"<returned-task-id>"}'
```

The common `slurm`, `local`, and `inline` executors are supported. Slurm/local returns the job
identity promptly; inline blocks inside its compute allocation and returns the original result
fields plus `state`, `analysis_id`, `task_id`, and `job_id`. A failed algorithm writes `FAILED`,
never `COMPLETED`; its partial result remains available through `literature_job_status`.
There is one active task per analysis to protect shared checkpoints. Follow common-runtime
`AISCI_SLURM_FALLBACK` and `AISCI_JOB_PREFIX` configuration for scheduling and image selection.

| Setting | Meaning |
| --- | --- |
| `LITERATURE_CORPUS_ROOT` | Admitted read-only corpus tree and defaults below |
| `LITERATURE_ALLOWED_ROOTS` | Additional permitted input roots, separated by the OS path separator |
| `LITERATURE_PAPERS` | PDF directory; default `<corpus>/papers` |
| `LITERATURE_CACHE_DIR` | Text/vector cache; default `<corpus>/mechanism_cache` |
| `LITERATURE_MANIFEST` | Manifest CSV; default `<corpus>/paperqa_manifest.csv` |
| `LITERATURE_HGNC` | HGNC table; default `<corpus>/hgnc_complete_set.txt` |
| `LITERATURE_HF_CACHE` | Pre-staged embedding cache; default `<corpus>/hf_cache` |
| `LITERATURE_EMBEDDING` | Local embedding identifier; default `st-NeuML/pubmedbert-base-embeddings` |
| `LITERATURE_INDEX_DIR`, `LITERATURE_INDEX_NAME` | Prebuilt PaperQA index root and name; defaults `index_pubmedbert`, `retigene_full_pubmedbert` |
| `LITERATURE_MODEL_ENDPOINT`, `LITERATURE_MODEL` | Explicit OpenAI-compatible `/v1` endpoint and served model name; no default |
| `LITERATURE_MODEL_API_KEY_FILE` | Preferred model credential file; read only by the worker |
| `LITERATURE_MODEL_API_KEY` | Optional credential environment value if no key file is set |
| `LITERATURE_MODEL_TIMEOUT` | Whole-corpus model request timeout, seconds; default 180 |
| `LITERATURE_MODEL_MAX_TOKENS` | Optional positive response token limit for PaperQA model roles; unset preserves PaperQA defaults |
| `LITERATURE_SEARCH_URL` | Optional Europe PMC-compatible URL; defaults to the public Europe PMC search endpoint |

Explicit paths must resolve inside an admitted root, including manifest PDF locations. Shared
corpus caches stay read-only. Missing text caches may be built from PDFs only inside the analysis
workspace. PaperQA gets an atomic private copy of the prebuilt corpus index inside that
workspace, because Tantivy takes a writer lock even during searches. Saved
embeddings are reused; the shared index remains read-only. Index synchronization is disabled during queries.

## Models, network, and budgets

`literature_search` sends its public keyword query to Europe PMC. `search_corpus` never calls a
language model: it uses local PubMedBERT embeddings and BM25. Embeddings use pre-staged weights
only and do not download them during analysis. PaperQA may perform bibliographic metadata requests.
Both answer and curation models use the configured endpoint exclusively; without endpoint/model
settings they report `not_enabled`. Credentials are never tool arguments or persisted job requests.
Model HTTP redirects are refused for the extraction client; keys are redacted from worker output.

The original app priced model calls through its gateway relay. This standalone server has no
provider-specific price catalog, so a positive `max_cost_usd` is explicitly refused rather than
pretending to enforce it. Use an endpoint with its own spending controls for priced models. The
pilot still detects failed or unparsable model replies before the full pass.

## Validation and rollout

The package includes the original synthetic extraction, quote verification, HGNC, curation-spec,
BM25/fusion and public-search regression fixtures, plus real MCP schema/argument checks, an actual
stdio-to-inline-worker run against a local synthetic HTTP service, confinement tests, model key-file
routing, and PaperQA configuration tests. These prove software behavior on synthetic fixtures.
They do not establish parity on the school's real corpus or validate a released image.

Before enabling this port in AiScientist, build and pin its image, run the original and port on the
same approved corpus/settings/model, compare citations, passages, verified gene/hit/request tables,
and verify the website-to-HPC3-to-artifact chain. Keep the existing application tools until that
acceptance passes. No release tag or digest is supplied by this source-only change.

## Tool reference

### literature_search

Search Europe PMC using focused biomedical keyword queries, with no API key or language model. Returns real citations with title, authors, year, journal, DOI, PMID and URL. `abstracts=true` includes bounded plain-text abstracts; `pubmed_only=true` restricts results to PubMed records. `limit` is 1-25, default 8.

The original query focusing, generic-poster filtering and IDF-weighted title/abstract relevance ranking are preserved. Only cite returned identifiers. This tool sends its query to the configured Europe PMC-compatible endpoint, defaulting to the public service. Empty queries and HTTP failures return failed tasks with diagnostics.

Use `analysis_id` for the output workspace and poll `literature_job_status` when asynchronous. For local corpus passages use `search_corpus`; for a synthesized answer with evidence use `deep_literature`.

### search_corpus

Retrieve verbatim passages from the configured read-only corpus without calling a language model. Accepts 1-6 `queries`, `top_k` 1-30 (default 12), `max_per_paper` (default 3), optional exact `terms` (up to 12), and optional `pmids` to restrict papers.

The original hybrid ranking combines local PubMedBERT cosine similarity and BM25 over question words, preserves a share of semantic matches, boosts exact gene-symbol matches and alternates across questions. `terms` are checked against the corpus, with diagnostics for missing terms. Returned contexts carry text, PMID, page, citation, source metadata, ranking score, cosine and the query that retrieved them. No passage is synthesized.

Requires prebuilt `mechanism_cache/chunks.jsonl` and local embedding weights. `LITERATURE_HF_CACHE` accepts an HF_HOME containing `hub/` or the hub itself. No runtime model download is attempted. Missing vectors may be computed in memory; the shared cache is never rewritten. No matches is a failed lookup, not evidence that a biomedical association is false. Refreshing corpus indexes is a separate administrator operation.

Results and durable jobs stay in this analysis workspace. The caller may send returned passages to its chosen answer model; this tool itself does no generation.

### deep_literature

Answer one focused `question` with PaperQA's search, evidence gathering and synthesis over the prebuilt local corpus index. Ask a complete biomedical question rather than a bag of identifiers. Returns the answer, supporting contexts/citations and retrieval diagnostics. Zero contexts or no generated answer is a failed lookup.

All model roles use the explicit server `LITERATURE_MODEL_ENDPOINT` and `LITERATURE_MODEL`; there is no public model fallback. Configure `LITERATURE_MODEL_API_KEY_FILE` if needed. Embeddings remain local (`st-` sentence-transformers weights). PaperQA may make bibliographic metadata network requests. Model/protocol parameters are not tool arguments.

The shared corpus index is read-only and index synchronization is disabled. Mutable answer files live under the current analysis workspace. Evidence breadth, concurrency, answer length and model timeouts are administrator settings described in the package README. The default deterministic PaperQA agent preserves the original search/gather/answer workflow.

Use `analysis_id` to isolate questions/workflows and poll `literature_job_status` for asynchronous execution. To curate a gene list across corpus passages use `extract_haploinsufficient_genes`; one RAG answer is not a whole-corpus scan.

### extract_haploinsufficient_genes

Curate genes reported as haploinsufficient in retinal disease from the configured corpus. The original pipeline is retained: model-written retrieval questions, local embedding/BM25 retrieval, keyword and exact-term rounds, per-passage JSON judgments, gene-directed follow-up, optional unread-passage checking, exact-quote verification, HGNC normalization, evidence flags and review tables. A statement is kept only when its quoted text can be found in the cited passage. A mechanism assertion and an experimental dosage measurement remain distinct.

The tool writes `genes.csv`, `hits.csv`, and `requests.csv` plus durable requests/judgments in its analysis workspace. Tables carry PMIDs, verbatim quotes, source pages, evidence classes, classification/verification flags and gene-normalization diagnostics. Inspect review flags and source quotes before using a candidate list. A bounded smoke run demonstrates execution, not exhaustive recall or scientific completeness.

The schema exposes retrieval settings (`n_requests`, `k_per_request`, `keyword_round`, `term_round`, `max_term_passages`, `k_per_gene`), output controls (`max_quotes_per_gene`), parallelism (`concurrency`), smoke-test cap (`max_passages`, zero means all), pilot settings, unread checks, optional `pmids` and optional `spec`. A pilot detects failed or unparsable model replies before the full pass. This standalone service cannot price arbitrary endpoints: a positive `max_cost_usd` is refused; configure spending controls at the model service.

To curate another property, provide the complete typed `spec` object:

```json
{
  "target": "the property to curate",
  "definition": "what qualifies, phrased precisely",
  "counts_when": ["an explicit qualifying statement in a retrieved passage"],
  "does_not_count": ["a gene mention without the qualifying assertion"],
  "classes": ["a supported evidence class"],
  "scope": "the relevant disease or biological context",
  "requests": ["a focused retrieval question"],
  "terms": ["an exact phrase to read in full"]
}
```

The spec definition/rules become the reading prompt; its questions and exact terms drive retrieval. Unknown spec fields are rejected. Without a spec, the original haploinsufficiency rules apply. Model endpoint/name/key are explicit server settings, never tool arguments. Shared corpus paths remain read-only; missing text extraction writes only to this analysis. Reuse an analysis after a recoverable interruption to resume stored judgments; use a new analysis ID when changing corpus/model identity.
