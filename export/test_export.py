#!/usr/bin/env python3
"""Cross-checks the exported JSON against the raw CLIF files and exercises config errors.

    python export/test_export.py [path/to/config.yaml]
"""
import json, subprocess, sys, tempfile
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG_PATH = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "config.yaml"
cfg = yaml.safe_load(CFG_PATH.read_text())
src = (CFG_PATH.parent / cfg["clif_data_dir"]).resolve()
ext = cfg["filetype"]
rd = (lambda n: pd.read_csv(src / f"clif_{n}.csv", low_memory=False)) if ext == "csv" else (lambda n: pd.read_parquet(src / f"clif_{n}.parquet"))
for k in ("bal_file", "susceptibility_file"):   # make optional file paths absolute so the temp config still finds them
    if cfg.get(k):
        cfg[k] = str((CFG_PATH.parent / cfg[k]).resolve())
fails = []


def check(name, got, want):
    ok = got == want
    shown = f"{len(got)} ids" if isinstance(got, set) else got
    print(("PASS " if ok else "FAIL ") + f"{name}: {shown}" + ("" if ok else f" (expected {want if not isinstance(want, set) else str(len(want)) + ' ids'})"))
    if not ok:
        fails.append(name)


def run(config_path):
    return subprocess.run([sys.executable, str(ROOT / "export" / "export.py"), "--config", str(config_path)],
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    out = tmp / "out"
    c = dict(cfg, clif_data_dir=str(src), output_dir=str(out))
    (tmp / "c.yaml").write_text(yaml.safe_dump(c))
    r = run(tmp / "c.yaml")
    check("export exits 0", r.returncode, 0)
    idx = json.loads((out / "index.json").read_text())
    H = idx["hospitalizations"]
    ids = {h["id"] for h in H}
    P = {i: json.loads((out / "patients" / f"{i}.json").read_text()) for i in ids}

    adt = rd("adt"); adt["h"] = adt.hospitalization_id.astype(str)
    icu_ids = set(adt[adt.location_category == "icu"].h)
    check("cohort = hospitalizations with an ICU ADT row", ids, icu_ids)

    mi = rd("medication_admin_intermittent"); mi["h"] = mi.hospitalization_id.astype(str)
    raw_abx = mi[(mi.med_group == "CMS_sepsis_qualifying_antibiotics") & mi.h.isin(ids)]
    check("antibiotic doses", sum(len(a["doses"]) for p in P.values() for a in p["abx"].values()), len(raw_abx))

    mb = rd("microbiology_culture"); mb["h"] = mb.hospitalization_id.astype(str); mb = mb[mb.h.isin(ids)]
    pos = mb[mb.organism_name.notna() & (mb.organism_name.astype(str).str.upper() != "CANCELLED")]
    check("hospitalizations with positive culture", sum(h["positive_culture"] for h in H), pos.h.nunique())

    vit = rd("vitals"); vit["h"] = vit.hospitalization_id.astype(str)
    t = vit[(vit.vital_category == "temp_c") & vit.h.isin(ids) & vit.vital_value.between(*cfg["temp_valid_range_c"])]
    check("temperature points (implausible removed)", sum(len(p["temp"]) for p in P.values()), len(t))
    check("no temperature outside valid range", all(cfg["temp_valid_range_c"][0] <= v <= cfg["temp_valid_range_c"][1] for p in P.values() for _, v in p["temp"]), True)

    lab = rd("labs"); lab["h"] = lab.hospitalization_id.astype(str)
    w = lab[(lab.lab_category == "wbc") & lab.h.isin(ids) & lab.lab_value_numeric.notna()]
    check("WBC points", sum(len(p["labs"].get("wbc", {"values": []})["values"]) for p in P.values()), len(w))

    rs = rd("respiratory_support"); rs["h"] = rs.hospitalization_id.astype(str)
    check("IMV hospitalizations", sum(h["imv"] for h in H), rs[(rs.device_category == "IMV") & rs.h.isin(ids)].h.nunique())
    check("respiratory bands never overlap or invert",
          all(y["start"] >= x["end"] - 1 and x["end"] > x["start"] for p in P.values() for x, y in zip(p["resp"]["bands"], p["resp"]["bands"][1:])) and
          all(b["end"] > b["start"] for p in P.values() for b in p["resp"]["bands"]), True)

    mc = rd("medication_admin_continuous"); mc["h"] = mc.hospitalization_id.astype(str)
    pr = mc[mc.med_category.isin(["norepinephrine", "epinephrine", "phenylephrine", "dopamine", "vasopressin"]) & mc.h.isin(ids)]
    check("hospitalizations with pressors", sum(h["pressor"] for h in H), pr.h.nunique())
    check("no negative pressor doses", all(v >= 0 for p in P.values() for a in p["pressors"]["agents"].values() for _, v in a["dose"]), True)

    # vasopressin units/hour -> units/min
    vrows = pr[pr.med_category == "vasopressin"].copy()
    vrows["ts"] = pd.to_datetime(vrows.admin_dttm, utc=True)
    first = vrows.sort_values("ts").groupby("h").head(1).iloc[0]          # earliest vasopressin row of one hospitalization
    exp = P[first.h]["pressors"]["agents"]["vasopressin"]["dose"]
    check("vasopressin first dose converted units/h -> units/min", round(exp[0][1], 4), round(first.med_dose / 60, 4))

    # NEE definition on a hand-built example
    p0 = next(p for p in P.values() if {"norepinephrine", "vasopressin"} <= set(p["pressors"]["agents"]))
    t0, v0 = next((t, v) for t, v in p0["pressors"]["nee"] if v > 0)
    hand = 0.0
    for k, a in p0["pressors"]["agents"].items():
        d = max([x for x in a["dose"] if x[0] <= t0], key=lambda x: x[0], default=[0, 0])[1]
        hand += d * {"norepinephrine": 1, "epinephrine": 1, "phenylephrine": 0.1, "dopamine": 0.01, "vasopressin": 2.5}[k]
    check("NE-equivalent matches hand calculation", round(v0, 4), round(hand, 4))

    check("axis starts at hospital admission", all(abs(p["axis"]["start"] - p["axis"]["admission"]) < 1 for p in P.values()), True)
    check("ICU stays inside the hospital axis", all(s["start"] >= p["axis"]["start"] - 1 and s["end"] <= p["axis"]["end"] + 1 for p in P.values() for s in p["icu_stays"] if s["start"] >= p["axis"]["start"]), True)
    check("every ICU hospitalization has >=1 ICU stay bar", all(len(p["icu_stays"]) >= 1 for p in P.values()), True)
    check("valid JSON (no NaN)", all("NaN" not in (out / "patients" / f"{i}.json").read_text() for i in ids), True)

    # ---- config errors ----
    # CLIF 2.1 microbiology_susceptibility
    sus_path = cfg.get("susceptibility_file") or (src / f"clif_microbiology_susceptibility.{ext}")
    if Path(sus_path).exists():
        sdf = pd.read_csv(sus_path, keep_default_na=False, dtype=str) if str(sus_path).endswith(".csv") else pd.read_parquet(sus_path)
        check("susceptibility columns follow CLIF 2.1", list(sdf.columns),
              ["organism_id", "antimicrobial_name", "antimicrobial_category", "sensitivity_name", "susceptibility_name", "susceptibility_category"])
        check("susceptibility_category within CLIF permissible values",
              sorted(set(sdf.susceptibility_category) - {"susceptible", "non_susceptible", "indeterminate", "NA"}), [])
        linkable = set(mb.organism_id.astype(str)) | set(rd("microbiology_culture").organism_id.astype(str))
        if cfg.get("bal_file"):
            b = pd.read_csv(cfg["bal_file"], dtype=str)
            for k in range(1, 7):
                linkable |= set(b[f"organism_id{k}"].dropna())
        check("every susceptibility organism_id links to a culture or BAL organism", sorted(set(sdf.organism_id) - linkable)[:5], [])
        exported_ids = sum(1 for p in P.values() for m in p["micro"] for x in m.get("susc", [])) + sum(
            1 for p in P.values() for bb in p.get("bal", []) for o in bb["culture"]["organisms"] if o.get("susc"))
        check("cultures shown with an antibiogram > 0", exported_ids > 0, True)

    bad = tmp / "bad.yaml"
    bad.write_text(yaml.safe_dump(dict(c, clif_data_dir=str(tmp / "does-not-exist"))))
    r = run(bad)
    check("missing data folder exits non-zero", r.returncode != 0, True)
    check("missing data folder message names the path", "does-not-exist" in r.stderr, True)

    empty = tmp / "empty"; empty.mkdir()
    bad.write_text(yaml.safe_dump(dict(c, clif_data_dir=str(empty))))
    r = run(bad)
    check("missing required table message", "Required CLIF table not found" in r.stderr, True)

    # optional table missing -> still exports, lane is empty
    part = tmp / "partial"; part.mkdir()
    for f in src.glob(f"clif_*.{ext}"):
        if "microbiology" not in f.name:
            (part / f.name).symlink_to(f)
    bad.write_text(yaml.safe_dump(dict(c, clif_data_dir=str(part), output_dir=str(tmp / "out2"))))
    r = run(bad)
    check("missing optional table still exports", r.returncode, 0)
    i2 = json.loads((tmp / "out2" / "index.json").read_text())
    check("no microbiology table -> zero cultures", sum(h["n_cultures"] for h in i2["hospitalizations"]), 0)

print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
