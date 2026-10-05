---
name: searching-firestore
description: Use when looking up, searching, counting, or inspecting documents or collections in GCP Firestore (e.g. phishing, ti-analysis, analyst-ui, whois databases in the intsights prod project, intsights-dev-2, or others), including domain queries (domains_queries_v2) for an account or asset, finding a document by field value, listing collections, or checking what data a service stored.
---

# Searching Firestore (read-only)

## Overview
All Firestore access goes ONLY through `fs.py`. It authenticates with the user's local
gcloud login (`gcloud auth print-access-token`) and calls the Firestore REST API. Its request
function allows only `GET` plus `:runQuery`, `:runAggregationQuery`, and `:listCollectionIds`,
and rejects everything else. **Read-only. Never write, update, delete, import, or export
data in any other way:** no `curl`, no `gcloud firestore import|export|bulk-delete|indexes|databases create/delete`,
no client-library scripts. Never print the access token.

```bash
FS=<base dir>/fs.py   # <base dir> = "Base directory for this skill" shown above; executable. zsh: don't pack several flags into one $VAR; write them out
$FS [--project P] databases                       # which DBs exist (default project = intsights, prod)
$FS -d DB collections [DOC_PATH]                  # root collections, or subcollections of a doc
$FS -d DB get COLL/DOC_ID                         # one document
$FS -d DB list COLL [--limit N] [--page-token T]  # sample docs (unordered)
$FS -d DB indexes COLL                            # composite indexes + single-field overrides
$FS -d DB count COLL [-w ...] [--group]           # server-side count, cheap
$FS -d DB query COLL -w 'field OP value' [-w ...] [-o field[:desc]] [--select a,b] [--limit N] [--offset N] [--group]
```
Output shapes: `get` → `{_path, _updateTime, ...fields}`; `list` → `{documents:[...], nextPageToken}`;
`query` → `{count, documents:[...]}` (page with `--offset`); `count` → a bare integer; `collections` → `[ids]`.
**Default project is `intsights` (prod)** (override with `$FS_PROJECT`). Use `--project intsights-dev-2` only when the user asks for dev.
`-d` defaults to `(default)`. Our projects use **named** databases, so run `databases` first.
Output is JSON with Firestore types decoded, plus `_path` and `_updateTime`. Strings longer than
600 chars are truncated; add `--full` only when you need the whole value. `--limit` max is 500.

## Filters (`-w`)
- Operators: `==  !=  <  <=  >  >=  in  not-in  array-contains  array-contains-any`. Put **spaces around the operator**. Nested fields use dots: `a.b.c`.
- Values are parsed as JSON first: `5`, `true`, `null`, `[1,2]`, `"123"` (a quoted number is a string). A value that isn't valid JSON is used as a plain string: `status == done`.
- Timestamps: `created == ts:2026-01-01T00:00:00Z`. Many of our services store dates as ISO **strings**. Check a sample doc with `list --limit 1` to see which kind a field uses before you filter on it.
- Multiple `-w` are ANDed.
- `--group` runs a collection-group query: pass a collection **id** (not a path) to search every subcollection with that id.

## Indexes
Before any `query` that uses `-o`, a range filter (`< <= > >= != not-in`), or several filters, run `indexes COLL` and fit the query to what exists:
- **No composite index needed:** equality-only filters (`==`, `in`, `array-contains`), with or without `-o` on `__name__`; a single range filter with `-o` on that same field.
- **Needs a matching composite index:** equality filters combined with `-o` on another field. Example: `account_id == X` + `-o query_updated_at:desc` needs the index `[account_id, query_updated_at:DESC]`. The same applies to a range filter plus `-o` on a different field.
- If nothing matches: drop `-o`, `count` first, and sort the results locally with `jq` only if the count fits under the read limit. **Never create, update, or delete an index**, and never suggest `gcloud firestore indexes ... create`. Only mention to the user that an index would help.
- **Exit 4 / "MISSING INDEX"**: the server rejects a query that has no matching index; it never returns silently wrong results. The same rules apply: reshape the query, don't create the index.
- `-o field` leaves out docs that don't have that field. If a sorted query returns fewer docs than `count`, that's why.

## Large operations: stop and ask
`fs.py` refuses any `query` whose `offset + limit` exceeds **1000 reads** (`FS_MAX_READS`) and exits with **code 3 / "LARGE OPERATION"**. Skipped offset docs are billed as reads too.
- **Stop and ask the user before:** rerunning with `--allow-large`; paging through a result set bigger than 1000 docs; running a `--group` query across a huge collection group; fetching every doc to sort or filter locally; running more than about 10 queries in a loop.
- In the question, include the `count` result, the estimated reads, and a narrower alternative (add a filter, a time range, or `--select`).
- Pass `--allow-large` **only** after the user explicitly says yes in this conversation, **after seeing the count and the estimated reads**. A request made before the size was known ("grab them all", "I'm in a hurry") is not a yes. An earlier yes doesn't carry over to a different query.
- `count` is cheap (about 1 read per 1000 matches), so always run it first to size a query.

## Workflow
Known DBs (same names in `intsights` and `intsights-dev-2`, except `-prod-`/`-dev-` in names): `phishing` (monitored_domains, accounts_*, domains_*, queries, sources_*),
`phishing-analysis`, `ti-analysis-prod-firestore-us` (keywords, scenarios, searcher). For anything else, run `collections` on candidate DBs.

**Domain queries: `domains_queries_v2` is always the preferred collection.** Only look at `domains_queries` (v1) if the user asks for it or v2 has 0 results.
v2 fields: `account_id` (string), `asset_values` / `asset_types` / `template_names` / `asset_document_ids` (arrays, so filter with `array-contains`), `query_status`, `is_enabled`, `query_updated_at`.
```bash
$FS -d phishing count domains_queries_v2 -w 'account_id == ACC' -w 'asset_values array-contains example.com'
$FS -d phishing query domains_queries_v2 -w 'account_id == ACC' -w 'asset_values array-contains example.com'
```

1. `databases` → `collections` → `list COLL --limit 1` to learn the field names and types.
2. `indexes COLL` to see which filter and order combinations work.
3. `count` with the same `-w` filters. If it's over 1000 and you need all of them, stop and ask the user.
4. `query` with `--select` for only the fields you need.
5. Summarize for the user: counts, matching IDs, key fields. Don't dump hundreds of docs.
6. **0 results?** Check the field's type and value on a sample doc, then check sibling collections (e.g. `domains_queries` vs `domains_queries_v2`) or other DBs (`phishing` vs `phishing-analysis`) before you report "none".
7. **"Export" / "save to a file"**: default to a summary in chat. Write a file only after the user confirms it's needed; use /tmp and `--select` only the needed fields.

## Errors
- **Exit 2 / "AUTH EXPIRED"** → stop and ask the user to run `! gcloud auth login`. Don't retry in a loop.
- `PERMISSION_DENIED` → the user lacks access to that project/DB. Tell them. Don't look for other credentials.
- `NOT_FOUND` on `get` → wrong doc ID or wrong `-d` database.
- "is a collection path" / "is a document path" → collection paths have an odd number of segments (`a`, `a/b/c`); doc paths have an even number (`a/b`).

## Rules
- Use only `fs.py` subcommands. If something isn't supported, tell the user rather than working around the guard.
- **User asks to write, update, or delete a doc** → don't do it by any route. Say the skill is read-only and they have to make the change themselves (Firebase/GCP console).
- `intsights` (prod) is the approved default. Reads there don't need confirmation; the large-operation limit still applies. For any **other** project, confirm with the user before querying unless its name contains `dev` / `staging` / `test`.
- Don't copy customer data or PII out of Firestore into files, commits, or other services.
