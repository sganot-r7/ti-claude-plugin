#!/usr/bin/env python3
"""Read-only Firestore client. Auth = `gcloud auth print-access-token` (the user's local gcloud login).

Only these Firestore REST calls are ever made (all read-only):
  GET  .../documents/{path}                  get doc / list docs in a collection
  POST .../documents[/{doc}]:listCollectionIds
  POST .../documents[/{doc}]:runQuery
  POST .../documents[/{doc}]:runAggregationQuery
plus read-only gcloud: `firestore databases list`, `firestore indexes composite|fields list`,
`config get-value project`, `auth print-access-token`.
Any other method or path suffix is rejected in _request().
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://firestore.googleapis.com/v1"
READ_POST_SUFFIXES = (":listCollectionIds", ":runQuery", ":runAggregationQuery")
MAX_LIMIT = 500
# A query reads up to offset+limit docs (skipped offset docs are billed too). Above this, stop and ask the user.
MAX_READS = int(os.environ.get("FS_MAX_READS", "1000"))
EXIT_LARGE = 3
TRUNC = 600

OPS = {
    "==": "EQUAL", "!=": "NOT_EQUAL", "<": "LESS_THAN", "<=": "LESS_THAN_OR_EQUAL",
    ">": "GREATER_THAN", ">=": "GREATER_THAN_OR_EQUAL", "in": "IN", "not-in": "NOT_IN",
    "array-contains": "ARRAY_CONTAINS", "array-contains-any": "ARRAY_CONTAINS_ANY",
}


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def gcloud(*args):
    try:
        out = subprocess.run(["gcloud", *args], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        die("gcloud CLI not found in PATH")
    if out.returncode != 0:
        err = out.stderr.strip()
        if "auth" in err.lower() or "login" in err.lower() or "reauth" in err.lower():
            die(f"AUTH EXPIRED - ask the user to run: ! gcloud auth login\n{err}", 2)
        die(err or f"gcloud {' '.join(args)} failed")
    return out.stdout.strip()


_token = None


def token():
    global _token
    if _token is None:
        _token = gcloud("auth", "print-access-token")
    return _token


def _request(method, url, body=None):
    path = urllib.parse.urlparse(url).path
    if not path.startswith("/v1/projects/") or "/databases/" not in path:
        die(f"refusing non-Firestore path: {path}")
    if method == "GET":
        pass
    elif method == "POST" and path.endswith(READ_POST_SUFFIXES):
        pass
    else:
        die(f"refusing {method} {path}: read-only client")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token()}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if e.code == 400 and "requires an index" in detail:
            die("MISSING INDEX - no composite index covers this filter/order combination. Do NOT create it.\n"
                "Run `indexes COLL` to see what exists and reshape the query to fit one, or drop -o.\n" + detail, 4)
        if e.code == 401:
            die(f"AUTH EXPIRED (401) - ask the user to run: ! gcloud auth login\n{detail}", 2)
        die(f"HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        die(f"cannot reach Firestore: {e.reason}")


# ---------- value (de)serialization ----------

def decode(v):
    if "nullValue" in v:
        return None
    for k in ("stringValue", "booleanValue", "doubleValue", "timestampValue", "referenceValue", "bytesValue"):
        if k in v:
            return v[k]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "geoPointValue" in v:
        return {"lat": v["geoPointValue"].get("latitude"), "lng": v["geoPointValue"].get("longitude")}
    if "arrayValue" in v:
        return [decode(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return {k: decode(x) for k, x in v["mapValue"].get("fields", {}).items()}
    return v


def encode(x):
    if x is None:
        return {"nullValue": None}
    if isinstance(x, bool):
        return {"booleanValue": x}
    if isinstance(x, int):
        return {"integerValue": str(x)}
    if isinstance(x, float):
        return {"doubleValue": x}
    if isinstance(x, list):
        return {"arrayValue": {"values": [encode(i) for i in x]}}
    if isinstance(x, dict):
        return {"mapValue": {"fields": {k: encode(i) for k, i in x.items()}}}
    return {"stringValue": str(x)}


def parse_value(raw):
    """`ts:2026-01-01T00:00:00Z` -> timestamp; JSON literals (5, true, null, [..], "x") parsed; else plain string."""
    if raw.startswith("ts:"):
        return {"timestampValue": raw[3:]}
    try:
        return encode(json.loads(raw))
    except ValueError:
        return {"stringValue": raw}


def trunc(x, full):
    if full:
        return x
    if isinstance(x, str) and len(x) > TRUNC:
        return x[:TRUNC] + f"...[+{len(x) - TRUNC} chars]"
    if isinstance(x, list):
        return [trunc(i, full) for i in x]
    if isinstance(x, dict):
        return {k: trunc(i, full) for k, i in x.items()}
    return x


def doc_out(d, db_root, full):
    return {
        "_path": d["name"].split("/documents/", 1)[1],
        "_updateTime": d.get("updateTime"),
        **trunc({k: decode(v) for k, v in d.get("fields", {}).items()}, full),
    }


# ---------- helpers ----------

def enc_path(p):
    return "/".join(urllib.parse.quote(s, safe="") for s in p.strip("/").split("/") if s)


def split_collection(path):
    """'a/b/c' -> parent doc 'a/b', collection id 'c'."""
    parts = [s for s in path.strip("/").split("/") if s]
    if len(parts) % 2 == 0:
        die(f"'{path}' is a document path; expected a collection path (odd number of segments)")
    return "/".join(parts[:-1]), parts[-1]


def parse_where(w):
    for op in sorted(OPS, key=len, reverse=True):
        token_op = f" {op} "
        if token_op in w:
            field, val = w.split(token_op, 1)
            return {"fieldFilter": {"field": {"fieldPath": field.strip()}, "op": OPS[op],
                                    "value": parse_value(val.strip())}}
    die(f"bad --where '{w}'. Format: 'field OP value' with OP in {', '.join(OPS)} (spaces around OP)")


def build_query(a):
    parent, cid = split_collection(a.collection) if not a.group else ("", a.collection)
    q = {"from": [{"collectionId": cid, "allDescendants": bool(a.group)}]}
    if a.where:
        fs = [parse_where(w) for w in a.where]
        q["where"] = fs[0] if len(fs) == 1 else {"compositeFilter": {"op": "AND", "filters": fs}}
    if getattr(a, "order", None):
        q["orderBy"] = []
        for o in a.order:
            f, _, d = o.partition(":")
            q["orderBy"].append({"field": {"fieldPath": f},
                                 "direction": "DESCENDING" if d.lower() == "desc" else "ASCENDING"})
    if getattr(a, "select", None):
        q["select"] = {"fields": [{"fieldPath": f} for f in a.select.split(",")]}
    return parent, q


def print_json(x):
    print(json.dumps(x, indent=2, ensure_ascii=False, default=str))


# ---------- commands ----------

def cmd_databases(a, root):
    out = gcloud("firestore", "databases", "list", f"--project={a.project}", "--format=json")
    print_json([{"database": d["name"].rsplit("/", 1)[-1], "location": d.get("locationId"),
                 "type": d.get("type")} for d in json.loads(out or "[]")])


def cmd_collections(a, root):
    url = f"{root}/documents" + (f"/{enc_path(a.doc)}" if a.doc else "") + ":listCollectionIds"
    ids, page = [], None
    while True:
        body = {"pageSize": 300, **({"pageToken": page} if page else {})}
        r = _request("POST", url, body)
        ids += r.get("collectionIds", [])
        page = r.get("nextPageToken")
        if not page:
            break
    print_json(sorted(ids))


def cmd_get(a, root):
    if len([x for x in a.doc.strip("/").split("/") if x]) % 2:
        die(f"'{a.doc}' is a collection path; use `list` or `query` (doc paths have an even number of segments)")
    print_json(doc_out(_request("GET", f"{root}/documents/{enc_path(a.doc)}"), root, a.full))


def cmd_list(a, root):
    split_collection(a.collection)
    limit = min(a.limit, MAX_LIMIT)
    qs = {"pageSize": limit}
    if a.page_token:
        qs["pageToken"] = a.page_token
    r = _request("GET", f"{root}/documents/{enc_path(a.collection)}?{urllib.parse.urlencode(qs)}")
    print_json({"documents": [doc_out(d, root, a.full) for d in r.get("documents", [])],
                "nextPageToken": r.get("nextPageToken")})


def guard_reads(n, what, a):
    if n > MAX_READS and not a.allow_large:
        die(f"LARGE OPERATION - {what} would read ~{n} documents (limit {MAX_READS}). "
            "Stop and ask the user before rerunning with --allow-large.", EXIT_LARGE)


def cmd_query(a, root):
    parent, q = build_query(a)
    guard_reads(a.offset + min(a.limit, MAX_LIMIT), f"query (offset {a.offset} + limit {a.limit})", a)
    q["limit"] = min(a.limit, MAX_LIMIT)
    if a.offset:
        q["offset"] = a.offset
    url = f"{root}/documents" + (f"/{enc_path(parent)}" if parent else "") + ":runQuery"
    rows = _request("POST", url, {"structuredQuery": q})
    docs = [doc_out(r["document"], root, a.full) for r in rows if "document" in r]
    print_json({"count": len(docs), "documents": docs})


def cmd_indexes(a, root):
    cid = a.collection.strip("/").split("/")[-1]
    db = ["--project", a.project, "--database", a.database, "--format=json"]
    comp = json.loads(gcloud("firestore", "indexes", "composite", "list", *db) or "[]")
    fields = json.loads(gcloud("firestore", "indexes", "fields", "list", *db) or "[]")
    fmt = lambda f: f"{f['fieldPath']}:{(f.get('order') or f.get('arrayConfig', '')).replace('ENDING', '')}"
    out = {
        "collection": cid,
        "note": "Single-field asc/desc/array-contains indexes exist for every field unless exempted below. "
                "Equality-only filters on several fields work without a composite index. "
                "Order by a field other than the filtered ones, or range + order on different fields, needs a composite index.",
        "composite": [{"scope": i.get("queryScope"), "state": i.get("state"),
                       "fields": [fmt(f) for f in i["fields"] if f["fieldPath"] != "__name__"]}
                      for i in comp if i["name"].split("/collectionGroups/")[1].split("/")[0] == cid],
        "single_field_overrides": [
            {"field": f["name"].rsplit("/fields/", 1)[1],
             "indexes": [fmt(x["fields"][0]) for x in f.get("indexConfig", {}).get("indexes", [])] or "NONE (exempted)"}
            for f in fields if f["name"].split("/collectionGroups/")[1].split("/")[0] in (cid, "__default__")],
    }
    print_json(out)


def cmd_count(a, root):
    parent, q = build_query(a)
    url = f"{root}/documents" + (f"/{enc_path(parent)}" if parent else "") + ":runAggregationQuery"
    body = {"structuredAggregationQuery": {"structuredQuery": q,
                                           "aggregations": [{"alias": "n", "count": {}}]}}
    rows = _request("POST", url, body)
    for r in rows:
        if "result" in r:
            print(int(r["result"]["aggregateFields"]["n"]["integerValue"]))
            return
    print(0)


def main():
    p = argparse.ArgumentParser(description="Read-only Firestore search via gcloud credentials")
    p.add_argument("--project", default=os.environ.get("FS_PROJECT", "intsights"),
                   help="GCP project (default: intsights, or $FS_PROJECT)")
    p.add_argument("--database", "-d", default="(default)", help="Firestore database id (default: '(default)')")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("databases", help="list Firestore databases in the project")

    s = sub.add_parser("collections", help="list collection ids (root, or subcollections of DOC)")
    s.add_argument("doc", nargs="?")

    s = sub.add_parser("get", help="get one document by path, e.g. users/abc")
    s.add_argument("doc")
    s.add_argument("--full", action="store_true", help="don't truncate long strings")

    s = sub.add_parser("list", help="list documents in a collection (unordered, paged)")
    s.add_argument("collection")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--page-token")
    s.add_argument("--full", action="store_true")

    s = sub.add_parser("indexes", help="composite indexes + single-field overrides for a collection")
    s.add_argument("collection")

    for name in ("query", "count"):
        s = sub.add_parser(name, help=f"{name} documents matching filters")
        s.add_argument("collection", help="collection path (e.g. users or users/abc/orders); with --group: collection id")
        s.add_argument("--where", "-w", action="append", help="'field OP value' (repeatable, ANDed)")
        s.add_argument("--group", action="store_true", help="collection-group query across all parents")
        if name == "query":
            s.add_argument("--order", "-o", action="append", help="field[:desc] (repeatable)")
            s.add_argument("--select", help="comma-separated field paths to return")
            s.add_argument("--limit", type=int, default=20)
            s.add_argument("--offset", type=int, default=0)
            s.add_argument("--full", action="store_true")
            s.add_argument("--allow-large", action="store_true",
                           help=f"allow reading more than {MAX_READS} docs - ONLY after the user approved it")

    a = p.parse_args()
    root = f"{BASE}/projects/{a.project}/databases/{urllib.parse.quote(a.database, safe='')}"
    globals()[f"cmd_{a.cmd}"](a, root)


if __name__ == "__main__":
    main()
