"""Unit tests of settings and the HTTP client against the fake loopback API (no external network)."""

import json
import socket

import pytest
from aiscientist_mcp.visionkb_kg import api
from aiscientist_mcp.visionkb_kg.settings import ClientError, Settings
from vkg_fake import RELEASE, TOKEN


def cfg(url, token_file=None, timeout=5.0):
    return Settings(api_url=url, token_file=token_file, timeout_s=timeout)


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VISIONKB_API_URL", "http://127.0.0.1:8770/v1/")
    monkeypatch.setenv("VISIONKB_API_TOKEN_FILE", str(tmp_path / "t"))
    monkeypatch.setenv("VISIONKB_TIMEOUT_S", "7.5")
    s = Settings.from_env()
    assert (s.base_url(), s.timeout_s, s.token_file) == ("http://127.0.0.1:8770", 7.5, tmp_path / "t")
    monkeypatch.delenv("VISIONKB_TIMEOUT_S")
    assert Settings.from_env().timeout_s == 30.0
    for bad in ("abc", "0", "-1", "601"):
        monkeypatch.setenv("VISIONKB_TIMEOUT_S", bad)
        with pytest.raises(ClientError) as e:
            Settings.from_env()
        assert e.value.code == "invalid_setting"


@pytest.mark.parametrize(
    ("url", "code"),
    [("", "not_configured"), ("ftp://h/x", "invalid_setting"), ("http://", "invalid_setting"),
     ("http://u:p@h:1", "invalid_setting"), ("http://h:1/?a=1", "invalid_setting")],
)  # fmt: skip
def test_bad_url(url, code):
    with pytest.raises(ClientError) as e:
        cfg(url).base_url()
    assert e.value.code == code


def test_token_file(tmp_path):
    p = tmp_path / "tok"
    assert cfg("http://h").token() is None
    for text, want in ((f"\n# comment\n {TOKEN} \n", TOKEN), ("", None), ("a b\n", None)):
        p.write_text(text)
        if want:
            assert cfg("http://h", p).token() == want
        else:
            with pytest.raises(ClientError) as e:
                cfg("http://h", p).token()
            assert e.value.code == "token_unreadable"
            assert TOKEN not in e.value.message
    with pytest.raises(ClientError) as e:
        cfg("http://h", tmp_path / "missing").token()
    assert e.value.code == "token_unreadable"


def test_curie_and_lists():
    assert api.check_curie(" HGNC:10012 ", "x") == "HGNC:10012"
    assert api.check_curie("visionkb:e-" + "a" * 40, "x").startswith("visionkb:e-")
    for bad in ("", "RHO", "HGNC:1/../x", "HGNC:1 2", "HGNC:1?x", "a:%2F", ":1"):
        with pytest.raises(ClientError):
            api.check_curie(bad, "x")
    assert api.split_list("RHO, GNAT1 ,,PDE6B") == ["RHO", "GNAT1", "PDE6B"]
    assert api.split_list([" RHO ", ""]) == ["RHO"]
    assert api.split_list(None) == []


def test_get_ok_sends_token_and_drops_none(fake_api, tmp_path):
    p = tmp_path / "tok"
    p.write_text(TOKEN)
    fake_api.log.clear()
    url = f"http://127.0.0.1:{fake_api.server_address[1]}"
    r = api.get(cfg(url, p), "/gene-sets", {"entity": "CL:0000604", "kind": None, "descendants": False, "x": []})
    assert r["status"] == "ok" and r["kg_release"] == RELEASE and r["http_status"] == 200
    assert r["request"] == {"path": "/v1/gene-sets", "params": {"entity": "CL:0000604", "descendants": "false"}}
    assert r["warnings"] == ["score = max pct_expressing over supporting edges"]
    hit = fake_api.log[-1]
    assert hit["auth"] == f"Bearer {TOKEN}"
    assert hit["query"] == {"entity": ["CL:0000604"], "descendants": ["false"]}
    assert TOKEN not in json.dumps(r)


def test_get_repeated_params(fake_api):
    url = f"http://127.0.0.1:{fake_api.server_address[1]}"
    fake_api.log.clear()
    api.get(cfg(url), "/health", {"genes": ["RHO", "GNAT1"]}, auth=False)
    assert fake_api.log[-1]["query"] == {"genes": ["RHO", "GNAT1"]}


def test_http_errors_are_reported(fake_api, tmp_path):
    url = f"http://127.0.0.1:{fake_api.server_address[1]}"
    r = api.get(cfg(url), "/release")  # no token configured
    assert (r["status"], r["http_status"], r["error"]["code"]) == ("error", 401, "unauthorized")
    assert r["kg_release"] == RELEASE
    assert r["warnings"][0].startswith("VISIONKB_API_TOKEN_FILE is not set")
    r = api.get(cfg(url), "/not-json", auth=False)
    assert (r["status"], r["error"]["code"], r["http_status"]) == ("error", "bad_response", 500)
    r = api.get(cfg(url), "/redirect", auth=False)
    assert (r["error"]["code"], r["http_status"]) == ("redirect_refused", 307)


def test_unreachable_and_timeout():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens here now
    r = api.get(cfg(f"http://127.0.0.1:{port}"), "/health", auth=False)
    assert (r["status"], r["error"]["code"], r["kg_release"]) == ("error", "unreachable", None)
    with socket.socket() as hang:  # accepts connections (backlog) but never answers
        hang.bind(("127.0.0.1", 0))
        hang.listen(1)
        r = api.get(cfg(f"http://127.0.0.1:{hang.getsockname()[1]}", timeout=0.5), "/health", auth=False)
    assert r["error"]["code"] == "timeout"


def test_not_an_envelope():
    r = api._normalize({"detail": "x"}, 200, {"path": "/v1/x", "params": {}})
    assert (r["status"], r["error"]["code"]) == ("error", "bad_response")
    r = api._normalize({"status": "ok", "kg_release": RELEASE, "data": 1}, 500, {"path": "/v1/x", "params": {}})
    assert (r["status"], r["error"]["code"], r["warnings"]) == ("error", "http_500", [])
