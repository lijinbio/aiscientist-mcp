"""Thin HTTP client of visionkb-api ``/v1`` (standard library only).

Every call returns the API envelope ``{status, kg_release, data, page, warnings, error}`` (contracts §8), plus
``http_status`` and ``request`` (path and parameters, never the token). Transport and protocol failures become
``status: "error"`` envelopes with an explicit code; nothing is retried, cached or substituted.
"""

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote, urlencode

from . import __version__
from .settings import ClientError, Settings

USER_AGENT = f"aiscientist-mcp-visionkb-kg/{__version__}"
MAX_BODY_BYTES = 4 * 1024 * 1024  # the API caps a response near 24,000 characters; anything far larger is wrong
CURIE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,39}:[^\s/?#%\\]{1,200}$")
ENVELOPE_KEYS = ("status", "kg_release", "data", "page", "warnings", "error")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: the token must only go to the configured host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def error_envelope(code: str, message: str, *, kg_release: str | None = None, warnings=None, **extra) -> dict:
    env = {
        "status": "error",
        "kg_release": kg_release,
        "data": None,
        "page": None,
        "warnings": list(warnings or []),
        "error": {"code": code, "message": message},
    }
    env.update(extra)
    return env


def check_curie(value: str, what: str) -> str:
    """A CURIE that is safe to put in a URL path segment (``prefix:local``, no '/', '?', '#', '%' or spaces)."""
    v = (value or "").strip()
    if not CURIE_RE.match(v):
        raise ClientError("invalid_argument", f"{what} must be a CURIE like HGNC:10012, got {value!r}")
    return v


def split_list(value: str | list[str] | None) -> list[str]:
    """``"RHO, GNAT1"`` or ``["RHO", "GNAT1"]`` -> ``["RHO", "GNAT1"]`` (order kept, blanks dropped)."""
    if value is None:
        return []
    items = re.split(r"[,\s]+", value) if isinstance(value, str) else [str(x).strip() for x in value]
    return [x for x in (i.strip() for i in items) if x]


def _query(params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    clean: dict[str, Any] = {}
    for k, v in params.items():
        if v is None or (isinstance(v, (list, tuple)) and not v):
            continue
        clean[k] = ("true" if v else "false") if isinstance(v, bool) else v
    return urlencode(clean, doseq=True), clean


def _normalize(body: Any, status: int, request: dict) -> dict:
    if not isinstance(body, dict) or body.get("status") not in ("ok", "error"):
        return error_envelope(
            "bad_response",
            f"HTTP {status}: the response is not a visionkb-api envelope",
            http_status=status,
            request=request,
        )
    env = {k: body.get(k) for k in ENVELOPE_KEYS}
    env["warnings"] = list(env["warnings"] or [])
    if env["status"] == "error" and not isinstance(env["error"], dict):
        env["error"] = {"code": f"http_{status}", "message": "error without details"}
    if env["status"] == "ok" and status >= 400:  # never report an HTTP failure as success
        env["status"] = "error"
        env["error"] = {"code": f"http_{status}", "message": f"HTTP {status} with status ok in the body"}
    env["http_status"] = status
    env["request"] = request
    return env


def get(settings: Settings, path: str, params: dict[str, Any] | None = None, *, auth: bool = True) -> dict:
    """GET ``/v1<path>``; ``path`` segments must already be validated or quoted."""
    query, clean = _query(params or {})
    request = {"path": f"/v1{path}", "params": clean}
    try:
        url = f"{settings.base_url()}/v1{path}" + (f"?{query}" if query else "")
        token = settings.token() if auth else None
    except ClientError as exc:
        return error_envelope(exc.code, exc.message, request=request)
    warnings = []
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    if token:
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    elif auth:
        warnings.append("VISIONKB_API_TOKEN_FILE is not set: request sent without a bearer token")
    try:
        with _OPENER.open(req, timeout=settings.timeout_s) as resp:
            status, raw = resp.status, resp.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            raw = exc.read(MAX_BODY_BYTES + 1)
        except OSError:
            raw = b""
        finally:
            exc.close()
        if 300 <= status < 400:
            return error_envelope(
                "redirect_refused",
                f"HTTP {status}: redirects are not followed (check VISIONKB_API_URL)",
                warnings=warnings,
                http_status=status,
                request=request,
            )
    except TimeoutError:
        return error_envelope(
            "timeout",
            f"no response within {settings.timeout_s:g} s (VISIONKB_TIMEOUT_S)",
            warnings=warnings,
            request=request,
        )
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, TimeoutError):  # socket.timeout is TimeoutError (3.10+)
            return error_envelope(
                "timeout",
                f"no response within {settings.timeout_s:g} s (VISIONKB_TIMEOUT_S)",
                warnings=warnings,
                request=request,
            )
        return error_envelope(
            "unreachable",
            f"cannot reach visionkb-api: {getattr(reason, 'strerror', None) or reason}",
            warnings=warnings,
            request=request,
        )
    except OSError as exc:
        return error_envelope(
            "unreachable",
            f"cannot reach visionkb-api: {exc.strerror or type(exc).__name__}",
            warnings=warnings,
            request=request,
        )
    if len(raw) > MAX_BODY_BYTES:
        return error_envelope(
            "bad_response",
            f"HTTP {status}: response larger than {MAX_BODY_BYTES} bytes",
            warnings=warnings,
            http_status=status,
            request=request,
        )
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return error_envelope(
            "bad_response",
            f"HTTP {status}: the response is not JSON",
            warnings=warnings,
            http_status=status,
            request=request,
        )
    env = _normalize(body, status, request)
    env["warnings"] = warnings + env["warnings"]
    return env


def segment(value: str) -> str:
    """Quote one validated path segment (keeps ':' readable)."""
    return quote(value, safe=":")
