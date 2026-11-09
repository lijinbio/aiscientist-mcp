"""A fake visionkb-api on 127.0.0.1 (stdlib http.server) returning canned envelopes.

Identifiers are real (HGNC:10012 RHO, CL:0000604 retinal rod cell, MONDO:0019200 retinitis pigmentosa,
UBERON:0000966 retina); every value is synthetic. Nothing leaves the loopback interface.
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlsplit

RELEASE = "visionkb-0000.01.0"
TOKEN = "synthetic-test-token-0123456789"
EDGE = "visionkb:e-" + "0" * 39 + "1"
RHO = {"id": "HGNC:10012", "name": "rhodopsin", "category": ["biolink:Gene"]}
ROD = {"id": "CL:0000604", "name": "retinal rod cell", "category": ["biolink:Cell"]}
REL = {
    "edge_id": EDGE,
    "subject": RHO,
    "predicate": "biolink:expressed_in",
    "object": ROD,
    "qualifiers": {"species_context_qualifier": "NCBITaxon:9606"},
    "knowledge_level": "observation",
    "agent_type": "data_analysis_pipeline",
    "primary_knowledge_source": "infores:visionkb-heca",
    "publications": [],
    "n_publications": 0,
    "evidence_count": 1,
    "status": "curated",
}


def env(data, page=None, warnings=(), status="ok", error=None):
    return {"status": status, "kg_release": RELEASE, "data": data, "page": page, "warnings": list(warnings),
            "error": error}  # fmt: skip


def err(code, message):
    return env(None, status="error", error={"code": code, "message": message})


def route(path, q):
    """(http status, body) for a GET; ``q`` is parse_qs output."""
    one = {k: v[0] for k, v in q.items()}
    page = {"limit": int(one.get("limit", 50)), "offset": int(one.get("offset", 0)), "total": 1}
    if path == "/v1/health":
        return 200, env({"neo4j": {"status": "ok"}, "summaries": {"status": "ok", "n_rows": 80},
                         "postgres": {"status": "ok"}, "release": RELEASE, "version": "0.1.1"})  # fmt: skip
    if path == "/v1/ready":
        return 200, env({"neo4j": {"status": "ok"}, "release": RELEASE})
    if path == "/v1/release":
        return 200, env({"kg_release": RELEASE, "biolink_version": "4.4.6", "counts": {"nodes_total": 44}})
    if path == "/v1/entities/search":
        hit = {**RHO, "symbol": "RHO", "synonyms": ["OPN2"], "match": "exact_symbol", "score": 1.0}
        return 200, env([hit], page={**page, "total": None})
    if path.startswith("/v1/entities/"):
        curie = unquote(path.removeprefix("/v1/entities/"))
        if curie != "HGNC:10012":
            return 404, err("not_found", f"{curie} is not in {RELEASE}")
        return 200, env({"node": {**RHO, "symbol": "RHO"}, "degree_by_predicate": {"biolink:expressed_in": {"out": 1, "in": 0}}})
    if path == "/v1/relationships":
        if "subject" not in one and "object" not in one:
            return 400, err("missing_anchor", "give subject or object (or both)")
        return 200, env([REL], page=page)
    if path.startswith("/v1/evidence/"):
        sr = {"id": "visionkb:sr-1", "edge_id": EDGE, "dataset_id": "visionkb:ds-hrca-snrna", "level": "majorclass",
              "group_label": "Rod", "n_cells": 500, "pct_expressing": 0.9}  # fmt: skip
        return 200, env({"edge": REL, "study_results": [sr], "publications": []}, page=page)
    if path == "/v1/gene-sets":
        return 200, env([{"gene_id": "HGNC:10012", "symbol": "RHO", "score": 0.9, "evidence": []}], page=page,
                        warnings=["score = max pct_expressing over supporting edges"])  # fmt: skip
    if path == "/v1/atlas/expression":
        genes = [g for v in q.get("genes", []) for g in v.split(",")]
        if len(genes) > 20:
            return 400, err("too_many_genes", "at most 20 genes per request")
        row = {"dataset_id": "visionkb:ds-hrca-snrna", "atlas_version": "heca-2026.05", "level": one.get("level"),
               "group_label": "Rod", "gene_id": "HGNC:10012", "gene_symbol": "RHO", "n_cells": 500}  # fmt: skip
        return 200, env([row], page=page)
    if path == "/v1/datasets":
        rec = {"id": "visionkb:ds-hrca-snrna", "version": "heca-2026.05", "title": "synthetic", "score": 1.0,
               "bind": {"path": "/path/to/atlas.h5ad", "name": "hrca", "role": "reference"}, "matched": []}  # fmt: skip
        return 200, env([rec], page=page)
    if path == "/v1/redirect":
        return 307, None
    if path == "/v1/not-json":
        return 500, "<html>oops</html>"
    return 404, err("not_found", "no route")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        self.server.log.append({"path": u.path, "query": q, "auth": self.headers.get("Authorization")})
        public = u.path in ("/v1/health", "/v1/ready", "/v1/redirect", "/v1/not-json")
        if not public and self.headers.get("Authorization") != f"Bearer {TOKEN}":
            status, body = 401, err("unauthorized", "missing bearer token")
        else:
            status, body = route(u.path, q)
        self.send_response(status)
        if status in (301, 302, 307):
            self.send_header("Location", "http://127.0.0.1:9/v1/health")
            self.end_headers()
            return
        raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_header("Content-Type", "text/html" if isinstance(body, str) else "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):  # keep test output quiet
        pass
