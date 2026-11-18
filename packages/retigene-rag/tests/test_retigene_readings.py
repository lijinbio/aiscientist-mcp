"""The two readings of a gene's sentences when a reply cannot be read (``grading.check_gene`` and
``grade_gene``): readings are paired by sentence number, a sentence a reading missed is not agreed, and
a gene with such a sentence is listed unresolved instead of graded. The sentences are made up."""

import json

from aiscientist_mcp.retigene_rag import grading
from aiscientist_mcp.retigene_rag.corpus import SentenceHit

CLAIM = "Haploinsufficiency of {gene} causes dominant retinitis pigmentosa in sentence {n}."
OTHER = "The {gene} transcript was sequenced in family {n} and no dosage statement is made here."


def _hits(gene, texts):
    return [
        SentenceHit(sid=f"1:{k}:0", pmid="1", chunk=k, sent=0, page=1, text=t, genes=[gene])
        for k, t in enumerate(texts, 1)
    ]


def _item(n, quote, claim="yes", gene_dosage=True, kind="retinal", hedge="none"):
    return {
        "sentence": n,
        "dosage_claim": claim,
        "hedge": hedge,
        "hedge_target": "none" if hedge == "none" else "mechanism",
        "subject_is_gene_dosage": gene_dosage,
        "mechanism_stated": "haploinsufficiency" if claim == "yes" else "unspecified",
        "phenotype": "retinitis pigmentosa" if claim == "yes" else None,
        "phenotype_kind": kind if claim == "yes" else "unclear",
        "evidence_type": "primary_finding" if claim == "yes" else "mentioned_nearby",
        "quote": quote,
    }


class Replies:
    """One reply per call, in order; the numbered sentences of the request decide the batch."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def __call__(self, messages):
        self.calls += 1
        r = self.replies.pop(0)
        return r if isinstance(r, str) else json.dumps({"items": r})


def test_string_booleans_are_read_as_written():
    def reply(v):
        return json.dumps({"items": [dict(_item(1, "q"), subject_is_gene_dosage=v)]})

    for value, want in ((True, True), ("true", True), (" True ", True), (False, False), ("false", False),
                        ("no", False), (None, False), (1, False), ("", False)):  # fmt: skip
        (c,) = grading.parse_gene_check(reply(value), 1)
        assert c["subject_is_gene_dosage"] is want, value


def test_a_failed_batch_does_not_shift_the_other_reading(monkeypatch):
    """Three batches of two; the second reading loses its middle batch. Paired by position, sentence 3
    of the first reading met the reading of sentence 5; a shorter second reading raised IndexError."""
    monkeypatch.setattr(grading, "MAX_SENTENCES_PER_CALL", 2)
    texts = [CLAIM.format(gene="PRPF31", n=n) if n in (1, 5) else OTHER.format(gene="PRPF31", n=n) for n in range(1, 7)]
    hits = _hits("PRPF31", texts)

    def batch(first):  # the reply for the batch that starts at sentence ``first`` (1-based)
        return [
            _item(k, texts[first + k - 2], claim="yes" if first + k - 1 in (1, 5) else "no", gene_dosage=True)
            for k in (1, 2)
        ]

    good = [batch(1), batch(3), batch(5)]
    # reading two: the middle batch fails twice (the retry too); the last batch fails in neither reading
    check = Replies([*good, batch(1), "not json", "still not json", batch(5)])
    checks, err = grading.check_gene("PRPF31", hits, check, passes=2, retries=1)
    assert check.calls == 7 and "sentences 3-4" in err
    assert [c["sentence"] for c in checks] == [1, 2, 3, 4, 5, 6]
    assert [c["sentence_id"] for c in checks] == [h.sid for h in hits]
    assert [c["readings_missing"] for c in checks] == [0, 0, 1, 1, 0, 0]
    assert [c["dosage_claim"] for c in checks] == ["yes", "no", "no", "no", "yes", "no"]  # each its own reading
    assert [c["meets_a"] for c in checks] == [True, False, False, False, True, False]
    assert checks[2]["claim_agreed"] is False and checks[2]["readings_differ"] == "one reading only"
    assert not any(c["unread"] for c in checks)

    # the last batch of the second reading fails instead: the reading is shorter, nothing raises
    check = Replies([*good, batch(1), batch(3), "not json", "not json"])
    checks, err = grading.check_gene("PRPF31", hits, check, passes=2, retries=1)
    assert [c["readings_missing"] for c in checks] == [0, 0, 0, 0, 1, 1] and "sentences 5-6" in err
    assert checks[4]["dosage_claim"] == "yes" and checks[4]["meets_a"] is False  # read once: not agreed

    # the first reading loses a batch and the second has it: the one reading stands, unagreed
    check = Replies(["not json", "not json", batch(3), batch(5), *good])
    checks, _ = grading.check_gene("PRPF31", hits, check, passes=2, retries=1)
    assert [c["readings_missing"] for c in checks] == [1, 1, 0, 0, 0, 0]
    assert checks[0]["dosage_claim"] == "yes" and checks[0]["meets_a"] is False and not checks[0]["unread"]
    assert checks[4]["meets_a"] is True


def test_a_gene_with_an_unread_batch_is_unresolved_not_n_by_rule(monkeypatch):
    monkeypatch.setattr(grading, "MAX_SENTENCES_PER_CALL", 1)
    texts = [OTHER.format(gene="CRX", n=1), CLAIM.format(gene="CRX", n=2)]
    hits = _hits("CRX", texts)
    no_claim = [_item(1, texts[0], claim="no")]

    def review(messages):
        raise AssertionError("a gene with an unread sentence is not sent to the review model")

    # sentence 1 is read (no claim); the batch of sentence 2, the claim, is never read
    check = Replies([no_claim, "not json", "not json"])
    g = grading.grade_gene("CRX", hits, check, review, retries=1, check_passes=1)
    assert g.grade == "unresolved" and g.reviewed_by == "" and g.review is None
    assert "1 of 2 sentence(s) lack a reading" in g.error and "sentences 2-2" in g.error
    assert [c["unread"] for c in g.checks] == [False, True] and g.checks[1]["readings_differ"] == "not read"

    # read by one of two readings: still listed apart, never N "by rules" and never A
    check = Replies([no_claim, [_item(1, texts[1])], no_claim, "not json", "not json"])
    g = grading.grade_gene("CRX", hits, check, review, retries=1, check_passes=2)
    assert g.grade == "unresolved" and "1 of 2 sentence(s) lack a reading" in g.error

    # every batch read: the same sentences grade as before (no claim -> N by rule, no review call)
    check = Replies([no_claim, [_item(1, texts[1], claim="no")]])
    g = grading.grade_gene("CRX", hits, check, review, retries=1, check_passes=1)
    assert (g.grade, g.reviewed_by, g.error) == ("N", "rules", "")

    # nothing read at all
    g = grading.grade_gene("CRX", hits[:1], Replies(["x", "y"]), review, retries=1, check_passes=1)
    assert g.grade == "unresolved" and g.checks[0]["unread"]
