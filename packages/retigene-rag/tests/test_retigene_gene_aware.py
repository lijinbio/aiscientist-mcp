"""The gene table beside the corpus (RCHENLAB/AiScientist #124, phase 1): a gene under its other names, the
table's facts with a gene's search results, a gene's own passages first, and what the table does not hold."""

import asyncio
import csv

QUESTION = "What are haploinsufficient genes in RetiGene papers?"
# symbol, aliases, previous symbols: an alias of two HGNC genes (LCA10, CRD), an abbreviation of the field
# (LCA) and a gene HGNC has renamed since RetiGene listed it (RPGR -> RPGR1; made up).
MORE_HGNC = [("CEP290", "NPHP6|LCA10|LCA", ""), ("L1CAM-AS1", "LCA10", ""), ("CRX", "CRD", ""),
             ("RPGR1", "CRD", "RPGR")]  # fmt: skip


def _more_hgnc(index):
    with (index / "hgnc_complete_set.txt").open("a", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        for sym, alias, prev in MORE_HGNC:
            w.writerow([sym, alias, prev, "Approved"])


def _load(index):
    from aiscientist_mcp.retigene_rag.corpus import Hgnc
    from aiscientist_mcp.retigene_rag.gene_table import GeneTable

    return GeneTable.load(index / "Full_gene_table_v9.9.tsv"), Hgnc(index / "hgnc_complete_set.txt")


def test_a_gene_is_found_by_its_other_names(index):
    _more_hgnc(index)
    t, h = _load(index)

    def found(symbol):
        got = t.resolve(symbol, h)
        return [r.gene for r in got["records"]], got["matched_by"]

    assert found("prpf31") == (["PRPF31"], "symbol")
    assert found("NPHP6") == (["CEP290"], "hgnc")  # an alias
    assert found("LCA10") == (["CEP290"], "hgnc")  # an alias of two HGNC genes; RetiGene lists one
    assert found("RPGR1") == (["RPGR"], "hgnc")  # RetiGene still has the previous symbol
    assert t.hgnc_symbol("RPGR", h) == "RPGR1" and t.hgnc_symbol("PAX6", h) == "PAX6"
    assert t.resolve("CRD", h) == {"records": [], "matched_by": "", "ambiguous": ["CRX", "RPGR"]}
    assert t.resolve("TP53", h)["records"] == [] and t.resolve("NPHP6")["records"] == []  # no HGNC table: no alias
    assert [r.status for r in t.resolve("RHO", h)["records"]] == ["established", "candidate"]

    assert h.names("NPHP6") == ["CEP290", "NPHP6"]  # LCA10 is not CEP290's alone; LCA is the disease here
    assert h.names("PAX6") == ["PAX6"] and h.names("NOTAGENE") == []  # AN2 has three characters


def test_what_the_table_does_not_hold_is_named(index):
    t, _ = _load(index)
    crx = t.get("CRX")
    got = t.check(crx, inheritance=["recessive", "x-linked"], phenotypes=["lca", "RP"])
    assert got["checked"] == [{"field": "inheritance", "stated": "AR", "in_table": True},
                              {"field": "inheritance", "stated": "XL", "in_table": False},
                              {"field": "phenotype", "stated": "LCA", "in_table": True},
                              {"field": "phenotype", "stated": "RP", "in_table": False}]  # fmt: skip
    assert got["differs"] == ["inheritance XL: RetiGene v9.9 has AD, AR for CRX",
                              "phenotype RP: RetiGene v9.9 has CD/CRD, LCA for CRX"]  # fmt: skip
    assert t.check(t.get("SOX2"), inheritance=["AD"])["differs"] == [
        "SOX2 is not an established gene in RetiGene v9.9 (candidate)"
    ]
    # a haploinsufficiency claim against the record: only a recessive gene or a discarded one is noted
    assert "lists CEP290 as AR only" in t.dosage_note(t.get("CEP290"))
    assert "discarded DYRK1A" in t.dosage_note(t.get("DYRK1A"))
    assert [t.dosage_note(t.get(g)) for g in ("PAX6", "CRX", "RPGR", "MT-ND4", "SOX2")] == [""] * 5
    facts = t.facts(t.get("RHO"))
    assert facts["source"] == "RetiGene v9.9" and facts["gene"] == "RHO"
    assert facts["records"][0] == {"status": "established", "inheritance": "AD/AR",
                                   "phenotypes": "RP (AD/AR); CSNB (AD)",
                                   "functions": "Visual cycle and phototransduction (VCPh)"}  # fmt: skip
    assert facts["records"][1] == {"status": "candidate", "candidate_reason": "One family with CSNB (AR)"}
    assert t.get("CRX")[0].diseases[0].get("digenic") is None


def test_digenic_is_kept_beside_the_modes():
    from aiscientist_mcp.retigene_rag.gene_table import _diseases

    (d,) = _diseases("Retinitis pigmentosa 7 (AD-AR-Digenic dominant, 608133)", "")
    assert (d["inheritance"], d["digenic"], d["id"]) == ("AD/AR", "dominant", "608133")


def test_gene_tools(env, index):
    from aiscientist_mcp.retigene_rag.server import server
    from mcp import Client

    _more_hgnc(index)
    table = index / "Full_gene_table_v9.9.tsv"  # PRPF31 as a recessive gene, to see a note on an A gene
    table.write_text("".join(line.replace("AD", "AR") if line.startswith("PRPF31\t") else line
                             for line in table.read_text().splitlines(keepends=True)))  # fmt: skip

    async def flow():
        async with Client(server, raise_exceptions=True) as c:
            g = (await c.call_tool("get_gene", {"gene": "PRP31"})).structured_content
            assert g["found"] and g["matched_by"] == "hgnc" and "are one gene in HGNC" in g["note"]
            assert g["records"][0]["gene"] == "PRPF31" and g["records"][0]["hgnc_symbol"] == "PRPF31"
            assert "check" not in g
            amb = (await c.call_tool("get_gene", {"gene": "CRD"})).structured_content
            assert amb["found"] is False and amb["ambiguous"] == ["CRX", "RPGR"]
            chk = (await c.call_tool("get_gene", {"gene": "CRX", "inheritance": ["XL"]})).structured_content
            assert chk["matched_by"] == "symbol"
            assert chk["check"]["differs"] == ["inheritance XL: RetiGene v9.9 has AD, AR for CRX"]

            args = {"terms": ["haploinsufficien"], "gene": "UNC119"}
            none = (await c.call_tool("search_sentences", args)).structured_content
            assert none["total_sentences"] == 0 and none["gene_facts"]["found"] is False  # the paper says HRG4
            assert "gene_names" not in none
            alias = (await c.call_tool("search_sentences", args | {"aliases": True})).structured_content
            assert alias["total_sentences"] == 1 and alias["gene_names"] == ["UNC119", "HRG4"]
            assert alias["sentences"].startswith("PMID 104 p2 c0: Haplo-insufficiency of the HRG4 gene")
            pax6 = await c.call_tool("search_sentences", {"terms": ["haploinsufficien"], "gene": "PAX6"})
            facts = pax6.structured_content["gene_facts"]
            assert pax6.structured_content["total_sentences"] == 2 and facts["found"]
            assert facts["records"][0]["inheritance"] == "AD" and facts["source"] == "RetiGene v9.9"
            plain = (await c.call_tool("search_sentences", {"terms": ["haploinsufficien"]})).structured_content
            assert "gene_facts" not in plain and plain["total_sentences"] == 9

            q = {"query": "Filler passage about clinical imaging and visual acuity in a cohort", "top_k": 3}
            far = (await c.call_tool("search_passages", q)).structured_content
            assert all(int(p["pmid"]) >= 200 and "scope" not in p for p in far["passages"])
            near = (await c.call_tool("search_passages", q | {"gene": "PRPF31"})).structured_content
            assert [(p["pmid"], p["scope"]) for p in near["passages"][:2]] == [("102", "key paper")] * 2
            assert near["passages"][2]["scope"] == "rest of the corpus" and int(near["passages"][2]["pmid"]) >= 200
            assert near["gene_passages"] == 2 and near["from_rest_of_corpus"] == 1
            assert near["gene_facts"]["records"][0]["phenotypes"] == "RP (AR)"
            hrg4 = (await c.call_tool("search_passages", q | {"gene": "HRG4", "top_k": 1})).structured_content
            assert hrg4["passages"][0]["pmid"] == "104" and hrg4["passages"][0]["scope"] == "names the gene"
            assert hrg4["gene_names"] == ["HRG4", "UNC119"] and hrg4["gene_facts"]["found"] is False

            cur = (await c.call_tool("submit_curation", {"question": QUESTION,
                                                          "terms": ["haploinsufficien"]})).structured_content  # fmt: skip
            got = (await c.call_tool("get_genes", {"curation_id": cur["curation_id"],
                                                    "grades": "A,B,N"})).structured_content  # fmt: skip
            rows = {r["gene"]: r for r in got["rows"]}
            assert rows["PRPF31"]["grade"] == "A" and "lists PRPF31 as AR only" in rows["PRPF31"]["table_note"]
            assert rows["PAX6"]["retigene"] == "established AD" and "table_note" not in rows["PAX6"]
            assert rows["SOX2"]["retigene"] == "candidate" and "table_note" not in rows["SOX2"]
            assert rows["UNC119"]["retigene"] == "not listed"
            assert rows["DYRK1A"]["grade"] == "N" and "table_note" not in rows["DYRK1A"]  # a note is for A and B
            assert got["table_notes"] == ["PRPF31"]

    asyncio.run(flow())


def test_gene_tools_without_a_gene_table_or_hgnc(env, index):
    from aiscientist_mcp.retigene_rag.server import server
    from mcp import Client

    (index / "Full_gene_table_v9.9.tsv").unlink()

    async def flow():
        async with Client(server, raise_exceptions=True) as c:
            hits = (await c.call_tool("search_sentences", {"terms": ["haploinsufficien"], "gene": "PAX6",
                                                            "aliases": True})).structured_content  # fmt: skip
            assert hits["total_sentences"] == 2 and "gene_facts" not in hits  # no table: the search still answers
            near = (await c.call_tool("search_passages", {"query": "aniridia", "gene": "PAX6",
                                                           "top_k": 2})).structured_content  # fmt: skip
            assert {p["scope"] for p in near["passages"]} == {"names the gene"} and "gene_facts" not in near

    asyncio.run(flow())
