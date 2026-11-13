# Scientific operator maintenance

Run these scripts from a checkout of this repository inside the matching published MCP image on a compute node. Bind the scripts read-only and use a dedicated writable output directory. They do not require the AiScientist application package. They are operator commands, not additional MCP tools or planner-selectable executable overrides.

- `build_hpo_lexicon.py` refreshes the phenotype package's ontology asset from official HPO JSON. It preserves the phenotype subtree, exact synonyms and obsolete-term replacements.
- `hpo_mapper_smoke.py` calls the native phenotype server against five synthetic descriptions. Generative mapping requires explicit server model settings; no patient input is included.
- `build_paperqa_directory_index.py` builds the original PaperQA directory index with a local embedding model and a disabled generative endpoint. The embedding must match `LITERATURE_EMBEDDING` at retrieval time.
- `query_paperqa_index.py` preserves the original direct index retrieval, citation selection and snippet limits. `--mode retrieve` makes no generative call. `--mode answer` requires `LITERATURE_MODEL_ENDPOINT`, `LITERATURE_MODEL` and, when needed, `LITERATURE_MODEL_API_KEY_FILE`; it uses an OpenAI-compatible operator endpoint, does not read an app session or a `.env` key automatically, and rejects redirects. The app's selected model remains mediated by its guarded gateway relay.
- `peek_paperqa_embeddings.py` inspects a trusted, operator-owned PaperQA index. Its cached objects use Python pickle; do not use untrusted downloaded cache files.

The application retains dataset/reference transfer, manifest preparation, run ownership and publication. Scientific implementations and dependencies belong to the MCP packages and these maintenance scripts. A script-only change does not alter an already published container or move its immutable tag.
