---
name: searching-es-logs
description: Use when investigating production logs, errors, exceptions, or service behavior for TI / phishing / TC services in Elasticsearch or Kibana (logs-kibana.prod.internal.ti.r7ops.com), including trace IDs, account IDs, pods, and error rates.
---

# Searching ES Logs (read-only)

## Overview
Prod logs live in the `logs-elasticsearch` cluster behind Kibana. Access goes ONLY
through `es_logs.py`, which uses the user's Kibana session cookie and sends every ES
request with `method=GET` on allowlisted paths. **Read-only. Never use curl, the
Kibana UI API, or any other route to the cluster. Never read or print the cookie file.**

```bash
ES=<base dir>/es_logs.py   # <base dir> = "Base directory for this skill" shown above; executable; zsh does not word-split "$ES", so no "python3 ..." prefix
$ES health                                   # verify cookie first
$ES indices 'app-tc-*'                       # list indices
$ES fields 'logs-*' 'json.*'   # discover fields
$ES count  INDEX '{"query":{...}}'
$ES search INDEX '{"query":{...},"size":20}'  # default size 20, max 500, sorted @timestamp desc
```
Long strings are truncated to 600 chars; pass `--raw` for the full response only when needed.

**Exit code 2 / "COOKIE EXPIRED"** → stop and ask the user to run:
`! pbpaste | python3 <base dir>/set_cookie.py` (write out the real absolute path for them)
(after copying cookies from Kibana DevTools). Do not retry. "cannot reach" → ask about VPN/WARP.

## Where logs are

**Phishing logs → Kibana space `DevOps` (script default), index `logs-*`.** Start every phishing
investigation there. Other spaces: `ES_LOGS_SPACE=tc|tip|platform|phishing|analytics $ES ...`.

| Services | Index | Service field | Level | Message |
|---|---|---|---|---|
| **Phishing** `ti-phishing-*` microservices (GKE ns `ti-phishing`: llm-classifier, query-api, query-generator, elastic-storer, webpage-monitoring…) | **`logs-*`** (Elastic Agent; filter `kubernetes.namespace: ti-phishing`) | `service.name` / `kubernetes.container.name` | `json.level` (INFO/WARNING/ERROR) | `json.message` (keyword) |
| Legacy TC k8s (ns `tc`: phishing-*-worker, phishing-*-interface, collect-worker…) | `app-tc-filebeat-*` (Filebeat) | `kubernetes.container.name` | `level` (mixed case: `info`/`INFO`/`error`/`ERROR`) | `message` (text) |
| TIP / platform / devops k8s | `app-tip-filebeat-*`, `app-platform-filebeat-*`, `app-devops-filebeat-*` | same as above | `level` | `message` |
| Legacy phishing python (vision_interface, phishing_domains/websites/subdomains_interface, zone-files) | `app-tc-phishing-logstash*` | `elasticapm_service_name.keyword` | `level.keyword` | `message` |
| Other logstash apps | `app-tc-logstash*`, `app-platform-logstash*` | `elasticapm_service_name.keyword` | `level.keyword` | `message` |

Filebeat (`ti-tf-infra/applications/filebeat/.../filebeat.yml`) decodes JSON log lines into
`json.*`, then renames `json.message|msg`→`message`, `json.level`→`level`, `json.stack_trace`→`stack_trace`,
`json.extra`→`extra`, etc. Other JSON keys stay under `json.*`.

Useful fields (new stream): `json.account_id`, `json.elasticapm_trace_id`, `json.exc_info` (traceback),
`json.exception.type`, `json.message_labels.trace_labels.{generation_id,candidate_id,asset_value,correlation_id}`,
`kubernetes.pod.name`. Unknown field? Run `fields` before guessing. `.keyword` is needed on text fields
in logstash indices for `term`/`aggs`.

## Query recipes
Always include a time range. Use `size:0` + aggs to profile before pulling hits.
```bash
# Errors for a service, last hour, grouped by message
$ES search 'logs-*' '{"size":0,"query":{"bool":{"filter":[{"term":{"kubernetes.namespace":"ti-phishing"}},
 {"range":{"@timestamp":{"gte":"now-1h"}}},{"term":{"service.name":"websites-llm-classifier"}},
 {"term":{"json.level":"ERROR"}}]}},"aggs":{"m":{"terms":{"field":"json.message","size":20}}}}'

# Follow a trace / account across services
'{"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-24h"}}},
 {"term":{"json.elasticapm_trace_id":"<id>"}}]}},"_source":["@timestamp","service.name","json.message","json.level"]}'

# Free text in legacy filebeat
'{"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-2h"}}},
 {"term":{"kubernetes.container.name":"phishing-domains-interface"}},
 {"match_phrase":{"message":"timeout"}}]}}}'
```

## Rules
- Only `health | indices | fields | mapping | count | search`. The script rejects anything else; don't try to work around it.
- Narrow time ranges (start ≤ 24h, widen if needed); use `_source` to limit fields.
- Summarize findings (counts, top messages, timeline, sample IDs) instead of dumping raw hits.
- Don't copy log contents containing secrets or customer PII into files or other services.
