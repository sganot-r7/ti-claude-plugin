#!/usr/bin/env python3
"""Read-only Elasticsearch log search via the Kibana console proxy.

Every request is sent to ES with method=GET and an allowlisted path, so no
write/delete API is reachable from this script. The cookie is read from
~/.config/es-logs/cookie and is never printed.

Usage:
  es_logs.py health
  es_logs.py indices [PATTERN]            # _cat/indices, e.g. 'app-*-filebeat-*'
  es_logs.py fields INDEX [FIELD_GLOB]    # _field_caps, e.g. 'kubernetes.*'
  es_logs.py mapping INDEX
  es_logs.py count INDEX BODY_JSON|-      # _count
  es_logs.py search INDEX BODY_JSON|- [--raw]
"""
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

KIBANA = os.environ.get("ES_LOGS_KIBANA", "https://logs-kibana.prod.internal.ti.r7ops.com")
SPACE = os.environ.get("ES_LOGS_SPACE", "devops")
COOKIE_FILE = os.path.expanduser(os.environ.get("ES_LOGS_COOKIE_FILE", "~/.config/es-logs/cookie"))
MAX_SIZE = 500
MSG_TRUNC = 600

# Top-level keys permitted in a _search / _count body. Anything else is rejected.
SEARCH_KEYS = {
    "query", "size", "from", "sort", "_source", "fields", "aggs", "aggregations",
    "track_total_hits", "timeout", "search_after", "collapse", "highlight",
    "docvalue_fields", "stored_fields", "runtime_mappings", "min_score",
    "terminate_after", "post_filter",
}
COUNT_KEYS = {"query"}
INDEX_RE = re.compile(r"^[A-Za-z0-9*.,_\-]+$")


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_cookie():
    try:
        with open(COOKIE_FILE, encoding="utf-8") as f:
            cookie = f.read().strip()
    except FileNotFoundError:
        die(f"cookie file {COOKIE_FILE} not found. Ask the user to refresh it.", 2)
    if not cookie:
        die(f"cookie file {COOKIE_FILE} is empty. Ask the user to refresh it.", 2)
    return cookie


def es_get(path, params=None, body=None):
    """Send a GET to ES through Kibana's console proxy. Returns parsed JSON."""
    es_path = path.lstrip("/")
    if params:
        es_path += "?" + urllib.parse.urlencode(params)
    qs = urllib.parse.urlencode({"path": es_path, "method": "GET"})
    url = f"{KIBANA}/s/{SPACE}/api/console/proxy?{qs}"
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Cookie", load_cookie())
    req.add_header("kbn-xsrf", "true")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh) es-logs-readonly")
    if body is not None:
        req.add_header("Content-Type", "application/json")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(
        NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    try:
        with opener.open(req, timeout=60) as r:
            status, text = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, text = e.code, (e.read().decode("utf-8", "replace") if e.fp else "")
    except urllib.error.URLError as e:
        die(f"cannot reach {KIBANA}: {e.reason}. Is VPN / Cloudflare WARP connected?")

    if status in (301, 302, 303, 307, 401) or text.lstrip().startswith("<"):
        die("COOKIE EXPIRED or not authorized (redirected to login). "
            "Ask the user to refresh ~/.config/es-logs/cookie. Do not retry.", 2)
    if status == 403:
        die(f"forbidden (403): {text[:300]}", 2)
    try:
        payload = json.loads(text)
    except ValueError:
        die(f"HTTP {status}, non-JSON response: {text[:300]}")
    if status >= 400:
        err = payload.get("error", payload)
        die(f"HTTP {status}: {json.dumps(err)[:800]}")
    return payload


def check_index(index):
    if not INDEX_RE.match(index) or index.startswith(("_", "-")):
        die(f"invalid index pattern {index!r}")
    return urllib.parse.quote(index, safe="*,-_.")


def read_body(arg, allowed):
    raw = sys.stdin.read() if arg == "-" else arg
    try:
        body = json.loads(raw)
    except ValueError as e:
        die(f"body is not valid JSON: {e}")
    if not isinstance(body, dict):
        die("body must be a JSON object")
    bad = set(body) - allowed
    if bad:
        die(f"read-only guard: keys not allowed in body: {sorted(bad)}")
    return body


def trunc(v):
    if isinstance(v, str) and len(v) > MSG_TRUNC:
        return v[:MSG_TRUNC] + f"...[+{len(v) - MSG_TRUNC} chars]"
    if isinstance(v, dict):
        return {k: trunc(x) for k, x in v.items()}
    if isinstance(v, list):
        return [trunc(x) for x in v]
    return v


def cmd_search(index, body_arg, raw=False):
    body = read_body(body_arg, SEARCH_KEYS)
    size = body.get("size", 20)
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        die(f"size must be a non-negative integer, got {size!r}")
    body["size"] = min(size, MAX_SIZE)
    body.setdefault("track_total_hits", True)
    body.setdefault("sort", [{"@timestamp": "desc"}])
    res = es_get(f"{check_index(index)}/_search", body=body)
    if raw:
        return res
    hits = res.get("hits", {})
    return {
        "took_ms": res.get("took"),
        "timed_out": res.get("timed_out"),
        "total": hits.get("total"),
        "hits": [dict(_index=h.get("_index"), **trunc(h.get("_source") or h.get("fields") or {}))
                 for h in hits.get("hits", [])],
        "aggregations": res.get("aggregations"),
    }


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "health":
        out = es_get("_cluster/health")
        out = {k: out.get(k) for k in ("cluster_name", "status", "number_of_nodes")}
    elif cmd == "indices":
        pat = check_index(args[0]) if args else "app-*"
        out = es_get(f"_cat/indices/{pat}", {"format": "json", "h": "index,docs.count,store.size,creation.date.string", "s": "index"})
    elif cmd == "fields" and args:
        glob = args[1] if len(args) > 1 else "*"
        res = es_get(f"{check_index(args[0])}/_field_caps", {"fields": glob})
        out = {name: sorted(types) for name, types in res.get("fields", {}).items()}
    elif cmd == "mapping" and args:
        out = es_get(f"{check_index(args[0])}/_mapping")
    elif cmd == "count" and len(args) == 2:
        out = es_get(f"{check_index(args[0])}/_count", body=read_body(args[1], COUNT_KEYS))
    elif cmd == "search" and len(args) >= 2:
        out = cmd_search(args[0], args[1], raw="--raw" in args[2:])
    else:
        die(f"unknown or malformed command. Run with --help.")
    print(json.dumps(out, indent=1, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
