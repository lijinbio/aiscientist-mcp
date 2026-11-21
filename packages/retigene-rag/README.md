# retigene-rag

Questions about inherited retinal disease genes, from two sources. The RetiGene gene table
(https://retigene.erdc.info/) answers what RetiGene curates: a gene's inheritance, phenotype and functional
categories, and every gene with a given combination of them. The RetiGene corpus, about 1,700 full-text
papers (39,563 passages, 426,706 sentences), answers what the papers say: an agent such as Claude writes its
own searches, and for "every gene with a property" a curation reads every sentence that states it and grades
each gene from its own sentences. The curation's answer is two tables, one row per gene and one row per
sentence, each with a verbatim quote, PMID and page.

| Tool | Arguments | Returns |
| --- | --- | --- |
| `get_gene` | `gene`, `inheritance`, `phenotypes` | the gene's records in the gene table: status, inheritance, phenotype categories each with its inheritance, functional categories, OMIM and Orphanet diseases, expression, key papers and whether the corpus holds them; `found: false` when RetiGene does not list it. `gene` may be an HGNC previous symbol or alias. With `inheritance` or `phenotypes`, `check` says which of them the established record holds |
| `find_genes` | `phenotypes`, `inheritance`, `functions`, `status`, `gene_class`, `cell_type`, `cell_group`, `tissue_expression`, `variant_spectrum`, `disease`, `group_by`, `limit` | every gene that meets all the conditions, with the count; with `group_by`, the count per value of one field |
| `search_sentences` | `terms`, `gene`, `limit`, `offset`, `aliases` | every sentence that holds a term, as `PMID p c: sentence` lines, paged; case, spaces, hyphens and PDF ligatures ignored. With `gene`, only sentences that name it (`aliases`: also by its other HGNC names), and `gene_facts` |
| `search_passages` | `query`, `terms`, `top_k`, `gene` | the passages nearest the query by chunk co-embedding (PubMedBERT); with `terms`, only passages that hold one are ranked. With `gene`, the gene's own passages first, each with its `scope`, and `gene_facts` |
| `read_passage` | `pmid`, `chunk` | the whole passage with its citation, title and DOI |
| `submit_curation` | `question`, `terms`, `estimate_only`, `max_cost_usd`, `rerun` | `curation_id`, `state`; when COMPLETED the A and B genes and the run's time, calls, tokens and cost. `estimate_only`: genes, calls, tokens and cost, no model call |
| `curation_status` | `curation_id` | `state`, model calls so far; when COMPLETED as above |
| `get_genes` | `curation_id`, `grades`, `top`, `full` | the gene table: grade, phenotype, quote with PMID, page and sentence id, what the rules changed, and what RetiGene has on the gene (`retigene`, `table_note`) |
| `get_evidence` | `curation_id`, `gene`, `pmid`, `grades`, `offset`, `limit` | the sentence table: every sentence read for a gene, with the checks behind its grade |
| `evaluate` | `curation_id`, `reference` | A recall (all, ocular, syndromic), B listed apart, N listed, pass flags, against the curator reference |
| `write_report` | `curation_id` | `report.md`: the A genes, the B genes apart, the run |
| `list_curations` | none | `curations` |

**The gene table** (`get_gene`, `find_genes`) is a RetiGene release file, `Full_gene_table_v<version>.tsv`,
read as released (RCHENLAB/AiScientist #124). The server takes the file named by `RETIGENE_GENE_TABLE`, else the
highest release in the index folder or its `gene_table/` folder, and every answer names the release. The file
is not part of this package: get it from RetiGene. Inheritance is given as AR, AD, XL and MT; a value the
table does not hold is refused with the values it does hold. A symbol can have two records (established for
one phenotype, a candidate for another), and a few records are loci. A gene's key papers are where a search
starts, not a filter: in the corpus, the statements about a gene are often in papers about other genes.

**The table beside the corpus** (RCHENLAB/AiScientist #124, phase 1). The two sources meet at the gene.

- *Names.* `get_gene` finds a gene by RetiGene's own name, then by HGNC: an approved symbol, a previous
  symbol or an alias (`NPHP6` is CEP290; `matched_by` is then `hgnc`, and each record gives its
  `hgnc_symbol`). An alias of several HGNC genes is the one RetiGene lists (`RP11`: PRPF31), and an alias of
  several RetiGene genes is refused with them (`CRD`: CRX, RPGR). The HGNC table is the index's
  `hgnc_complete_set.txt`; without one a gene is known by RetiGene's name only.
- *Facts with the text.* A search with `gene` returns `gene_facts` beside its sentences or passages: the
  release, and each record's status, inheritance, phenotype categories with their inheritance, and functional
  categories. `found: false` says RetiGene does not list the gene.
- *The gene's passages first.* `search_passages(gene=...)` ranks the gene's own passages before the rest of
  the corpus, each part by cosine: the passages of its key papers (`scope` `key paper`) and the passages with
  a sentence that names it by symbol or by another HGNC name (`names the gene`). The rest of the corpus fills
  what is left of `top_k` (`rest of the corpus`). `search_sentences(gene=..., aliases=true)` counts those
  other names too; they are previous symbols and aliases of four characters or more that belong to this gene
  alone and are not an abbreviation of the field.
- *What the table does not hold.* `get_gene(gene, inheritance=[...], phenotypes=[...])` checks statements
  against the established record: `check.differs` names each stated mode or phenotype category that the
  table does not have for the gene. In a curation, `get_genes` gives every row the gene's status and
  inheritance in RetiGene (`retigene`), and an A or B row a `table_note` when that record does not fit a
  haploinsufficiency claim: the gene is recessive only, or RetiGene discarded it. The note is read from the
  table when the row is read. It changes no grade and is not stored with the curation.

On RetiGene v1.12 with the HGNC table of 2026-10-14: 759 of the 762 gene names are approved symbols, 2 are
previous symbols (CLUAP1, TRAF3IP1) and 1 is unknown to HGNC (OR2W7). 2,104 other HGNC names resolve to a
RetiGene gene, and 16 are aliases of two of them. None of the 15 A genes of the curator reference is
recessive only or discarded in the table. ABCA4, CLN8 (recessive only) and FSCN2 (discarded), three of the A
genes outside the reference in the test below, each get a note, and so does RCBTB1, which the curator graded
B. The corpus tools were not run on the RetiGene index for this, only on the tests' index.

**The curation** (`submit_curation`) is the corpus-wide scan of RCHENLAB/AiScientist #95, with the
sentence grading of #99 (Ziyao Ma, rules revision 17):

1. Every sentence that states a dosage mechanism in words (haploinsufficiency, gene dosage, one functional
   copy, loss of one allele, ...) or holds one of the agent's terms, every hit taken, grouped by the gene
   named in the sentence or next to it (HGNC symbols and aliases). On RetiGene: 474 sentences, 301 genes.
2. The check model reads each gene's sentences twice against closed questions (is it a dosage claim, is the
   claim hedged, is it about this gene's own dosage, which mechanism, which phenotype, is it the paper's own
   finding or a reference entry), and the readings are merged field by field.
3. The review model grades the genes with a claim by the curator's definitions: **A**, the authors state
   without a hedge that heterozygous loss of function causes a retinal or ocular disease, or a syndrome with
   one, through haploinsufficiency; **B**, hedged, contradicted by another corpus paper, or one of several
   mechanisms; **N**, not supported.
4. The code bounds the grade: every quote is checked verbatim against the corpus, an A needs a sentence that
   meets the A conditions, and a contradiction, a hedged primary conclusion, a milder-phenotype statement or
   a non-ocular phenotype lowers it.

A curation is kept under an id made of its terms, the rules, the models and the index fingerprint, and
asking again reuses it. Every model reply is cached (`RETIGENE_CACHE`), so a rerun, a reworded question with
the same sentences, or a corpus update reads only what changed.

The id also holds the server's minor version (`0.0`), so 0.0.4 reuses curations made by 0.0.2 and 0.0.3.
Within one minor version, a curation made before a change to the readings is rerun. Version 0.0.2 changed
how a gene's two readings are merged, so 0.0.1 curations need to be rerun because
the kept tables do not show every case that the change affects. `submit_curation` runs such a curation
again from the cached replies and names what it replaces in `replaces`. Until it is run again, `curation_status` and `list_curations` give it the state `OUTDATED`, and
the tools that read a curation refuse it.

**The model comes from the caller**: `RETIGENE_PROVIDER`, `RETIGENE_CHECK_MODEL` / `RETIGENE_REVIEW_MODEL` and the
key or endpoint settings below. The curation records which model read it. It is validated on Claude Haiku
5.5 (the defaults, both readers; the 15-gene test below); for another model, run the test again.

With `RETIGENE_PROVIDER=relay` the server holds no key and no model address: each prompt is written to
`RETIGENE_RELAY_DIR/req/<id>.json` (`{"id", "messages", "max_tokens"}`) and the caller's platform answers in
`resp/<id>.json` with `{"text", "usage", "cost_usd"}` or `{"error", "kind"}` (the protocol of AiScientist's
`gateway/llm_relay.py`). `kind` `stop` ends the curation, keeping the replies read so far; `transport` is
tried again; `model` fails that one prompt, so its gene is read again and otherwise listed `unresolved`. The
cost is the platform's own figure.

| Variable | Meaning | Default |
| --- | --- | --- |
| `RETIGENE_INDEX` | the index, read-only, laid out as the AiScientist shared dataset `retigene` (`mechanism_cache/sentences.jsonl`, `chunks.jsonl`, `chunk_vecs.npy`, `manifest.csv`, `hgnc_complete_set.txt`) | required |
| `RETIGENE_GENE_TABLE` | a RetiGene gene table release (`Full_gene_table_v<version>.tsv`) for `get_gene` and `find_genes` | the highest release in the index folder or its `gene_table/` |
| `RETIGENE_PROVIDER` | `anthropic` (Claude), `openai` (any OpenAI-compatible endpoint) or `relay` (the caller's platform answers each prompt, see below) | `anthropic` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` | the Claude key (and a proxy) | for `anthropic` |
| `RETIGENE_BASE_URL`, `RETIGENE_API_KEY` | the endpoint (`http://host:port/v1`) and its key; `RETIGENE_OPENAI_BODY` is JSON merged into each request (the temperature is the endpoint's default, as for Claude) | for `openai` |
| `RETIGENE_RELAY_DIR`, `RETIGENE_RELAY_TIMEOUT` | for `relay`: the folder the platform answers in (`req/`, `resp/`), and how long to wait for one reply | `900` s |
| `RETIGENE_CHECK_MODEL`, `RETIGENE_REVIEW_MODEL` | the two readers | `claude-haiku-5-5`, `claude-haiku-5-5` |
| `RETIGENE_EFFORT`, `RETIGENE_CHECK_PASSES`, `RETIGENE_WORKERS` | Claude reasoning effort; readings per gene; genes graded at a time | `low`, `2`, `16` |
| `RETIGENE_PRICE_IN`, `RETIGENE_PRICE_OUT` | USD per million tokens for a model outside the Claude price table | `0` |
| `RETIGENE_CACHE` | model replies, kept across curations | `$AISCI_DATA_DIR/retigene-rag/cache` |
| `AISCI_DATA_DIR` | curations: `<root>/retigene-rag/<curation_id>/` (`genes.csv`, `sentences.csv`, `curation.json`, `report.md`) | `./aiscientist-mcp-data` |
| `AISCI_EXECUTOR`, `AISCI_SLURM` | how `submit_curation` runs: `slurm`, `local` or `inline` (see `aiscientist_mcp.common.jobs`) | `slurm` |

Install the `embed` extra (`sentence-transformers`, with torch) for `search_passages`. The image holds the
query model at the revision that made the chunk vectors.

## The 15-gene test

`eval/agent_eval.py` starts the server over stdio, as an MCP client does, gives Claude only the server's
tools and instructions, and scores the curation Claude made with `evaluate`. `eval/curation_eval.py` runs
one curation with no agent, for the model paths. The reference is the curator review of 2026-11-04
confirmed by Dr. Chen, bundled as `reference/reference_genes_reviewed.csv` (24 genes: 15 A, of them 10
ocular and 5 syndromic, 7 B, 2 N; grades without the quotes and review notes).

```bash
python eval/agent_eval.py --out run.json --model claude-haiku-5-5
python eval/agent_eval.py --out rw.json --question "Which genes cause eye disease when one copy is lost, according to the RetiGene papers?"
python eval/curation_eval.py --out cur.json
```

Tested on the lab's copy of the index (1,736 papers, 426,706 sentences) with anthropic 1.13.0, mcp 2.3.0 and
Python 3.13.3, ten runs each with an empty reply cache. The check model was Claude Haiku 5.5 at low effort,
reading each gene twice. Time and cost are for the whole question: agent turns, server start, the corpus
load and the curation. Input tokens include the cached system prompts (about three quarters).

| Question | Agent | Review model | Runs | Sentences, genes | Time | Model calls | Tokens in / out | Cost | A genes (ocular, syndromic) | B listed apart | N listed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| "What are haploinsufficient genes in RetiGene papers?" | Claude Haiku, 4 turns | Haiku | 3 | 474, 301 | 194-204 s | 714-717 | 2.24 M / 0.46 M | $0.31 | 15/15 (10/10, 5/5) | 7/7 | none |
| the same | Claude Sonnet, 4 turns | Haiku | 3 | 474, 301 | 190-197 s | 719-720 | 2.25 M / 0.46-0.47 M | $0.36-0.37 | 15/15 (10/10, 5/5) | 7/7 | none |
| "Which genes cause eye disease when one copy is lost, according to the RetiGene papers?" | Claude Haiku | Haiku | 1 | 517, 328 | 206 s | 770 | 2.38 M / 0.48 M | $0.32 | 15/15 (10/10, 5/5) | 7/7 | none |
| the same | Claude Sonnet | Haiku | 1 | 517, 328 | 195 s | 769 | 2.38 M / 0.49 M | $0.39 | 15/15 (10/10, 5/5) | 7/7 | none |
| the first question, no agent | none | Haiku | 1 | 474, 301 | 156 s | 712 | 2.24 M / 0.47 M | $0.31 | 15/15 (10/10, 5/5) | 7/7 | none |
| the same | none | Claude Sonnet 5.5 | 1 | 474, 301 | 157 s | 711 | 2.24 M / 0.45 M | $0.78 | 15/15 (10/10, 5/5) | 7/7 | none |
| v3 (the RetiGene scan of 2026-10-20), for comparison | | | | 1,537 passages | 10 min | 1,537 | | $1.08 | 18 of the 24-gene reference | | |

- **What the agents did.** Every agent searched "haploinsufficien" with variants of its own ("one functional
  copy", "reduced dosage", "dosage sensitiv", "one copy") and called `submit_curation` once with them. The
  rules' own dosage wording already covers most of these: the first question reads the same 474 sentences
  with or without them, and "one copy" adds 43 for the reworded one.
- **B genes.** All 7 were kept apart in every run, graded B, except RP1 graded N once.
- **A genes outside the reference.** ABCA4 and FSCN2 in every run; CLN8 and FH (the CFH protein, factor H,
  read as a gene) in some. They are not in the curator's 24 and have not been checked by a curator.
- **Reuse.** The same curation asked again answers at once from the kept result. With `rerun=true` and the
  reply cache it takes 17 s and no model call, with an identical gene table.
- **Estimate.** `estimate_only` gave $0.25-0.40, 678-753 calls and 2.1-3.8 min for the first question.
- **The image.** Built from `containers/retigene-rag/Dockerfile` (2.68 GB) and run one container per call
  with the index mounted read-only, as AiScientist runs a pinned server: `search_sentences` 10 s and
  `search_passages` 15 s per call (most of it the corpus and model load), and its query vectors equal the
  stored chunk vectors (cosine 1.000000 on 8 passages).

The offline tests use a stand-in model and embedder (`offline-test`): 33 tests, about 10 s.
