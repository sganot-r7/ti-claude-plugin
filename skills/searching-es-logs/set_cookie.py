#!/usr/bin/env python3
"""Save the Kibana session cookie from stdin (run by the USER, not Claude).

Accepts either a raw `Cookie:` header value or the DevTools
Application -> Cookies table (tab/space separated rows). Keeps only the
cookies Kibana needs: CF_Authorization, CF_AppSession, sid.

  pbpaste | python3 <skill dir>/set_cookie.py
  xclip -o -selection clipboard | python3 <skill dir>/set_cookie.py   # Linux
"""
import os
import re
import sys

NEEDED = ("CF_Authorization", "CF_AppSession", "sid")
PATH = os.path.expanduser("~/.config/es-logs/cookie")

text = sys.stdin.read()
found = {}
for part in re.split(r";\s*", text.strip().removeprefix("Cookie:").strip()):
    if "=" in part:
        k, v = part.split("=", 1)
        if k.strip() in NEEDED:
            found[k.strip()] = v.strip()
for line in text.splitlines():
    cols = line.split()
    if len(cols) >= 2 and cols[0] in NEEDED:
        found[cols[0]] = cols[1]

missing = [k for k in NEEDED if k not in found]
if missing:
    sys.exit(f"missing cookies: {missing}. Copy them from logs-kibana DevTools.")
os.makedirs(os.path.dirname(PATH), exist_ok=True)
fd = os.open(PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("; ".join(f"{k}={found[k]}" for k in NEEDED))
print(f"saved {PATH}")
