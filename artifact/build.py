#!/usr/bin/env python3
"""Inline the exported CLIF JSON into template.html -> index.html (single self-contained file)."""
import json, sys
from pathlib import Path

data_dir = Path(__file__).resolve().parent.parent / "app" / "public" / "data"
here = Path(__file__).resolve().parent

def slim(o):
    if isinstance(o, dict):
        return {k: slim(v) for k, v in o.items()}
    if isinstance(o, list):
        return [slim(v) for v in o]
    if isinstance(o, float):
        if o == int(o) and abs(o) < 1e15:
            return int(o)
        return round(o, 3)
    return o

idx = json.loads((data_dir / "index.json").read_text())
patients = {}
for r in idx["hospitalizations"]:
    patients[r["id"]] = slim(json.loads((data_dir / "patients" / f"{r['id']}.json").read_text()))
meta = idx["meta"]; meta.pop("source", None)           # no local paths in a shared page
meta["source_label"] = "MIMIC-IV demo in CLIF 2.1 format"
blob = json.dumps({"meta": slim(meta), "rows": slim(idx["hospitalizations"]), "p": patients}, separators=(",", ":"))
blob = blob.replace("</", "<\\/")
html = (here / "template.html").read_text().replace("/*__DATA__*/", blob)
(here / "index.html").write_text(html)
print(f"index.html {len(html)/1e6:.2f} MB, {len(patients)} patients")
