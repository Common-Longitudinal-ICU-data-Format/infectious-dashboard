#!/usr/bin/env python3
"""Export CLIF tables to per-hospitalization JSON for the timeline dashboard.

Usage:  python export/export.py [--config config.yaml]

Reads CLIF 2.x tables (csv or parquet) and writes
  <output_dir>/index.json                 one summary row per hospitalization
  <output_dir>/patients/<hosp_id>.json    full timeline for one hospitalization
All timestamps are epoch milliseconds (UTC).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REQUIRED = ["patient", "hospitalization", "adt"]
OPTIONAL = [
    "respiratory_support",
    "medication_admin_continuous",
    "medication_admin_intermittent",
    "microbiology_culture",
    "labs",
    "vitals",
]

# --- clinical definitions -------------------------------------------------
# Norepinephrine-equivalent (NEE) conversion, mcg/kg/min basis
# (Goradia et al. 2021; same convention used in CLIF vasopressor projects).
# vasopressin is converted from units/min with a factor of 2.5.
PRESSORS = ["norepinephrine", "epinephrine", "phenylephrine", "dopamine", "vasopressin", "angiotensin"]
NEE_FACTOR = {
    "norepinephrine": 1.0,
    "epinephrine": 1.0,
    "phenylephrine": 0.1,
    "dopamine": 0.01,
    "vasopressin": 2.5,   # applied to units/min
}

ANTIMICROBIAL_CLASS = {
    "acyclovir": "antiviral",
    "fluconazole": "antifungal", "micafungin": "antifungal", "voriconazole": "antifungal",
    "caspofungin": "antifungal", "amphotericin": "antifungal",
}
ANTIMICROBIAL_CATEGORIES = {
    "vancomycin", "metronidazole", "cefepime", "piperacillin_tazobactam", "cefazolin", "meropenem",
    "ceftriaxone", "ampicillin", "ciprofloxacin", "levofloxacin", "ceftazidime", "erythromycin",
    "ampicillin_sulbactam", "azithromycin", "tobramycin", "doxycycline", "clindamycin", "aztreonam",
    "gentamicin", "linezolid", "daptomycin", "ertapenem", "imipenem", "cefoxitin", "cefotaxime",
    "trimethoprim_sulfamethoxazole", "rifampin", "amikacin", "colistin", "tigecycline",
    "micafungin", "voriconazole", "fluconazole", "caspofungin", "amphotericin", "acyclovir",
}
ANTIBIOTIC_GROUP = "CMS_sepsis_qualifying_antibiotics"

SITE_GROUP = {
    "blood_buffy": "Blood",
    "genito_urinary_tract": "Urine",
    "respiratory_tract": "Respiratory",
    "respiratory_tract_lower": "Respiratory",
    "nasopharynx_upperairway": "Respiratory",
    "feces_stool": "Stool",
    "meninges_csf": "CSF",
    "peritoneum": "Sterile fluid",
    "pleural_cavity_fluid": "Sterile fluid",
    "joints": "Sterile fluid",
    "skin_rash_pustules_abscesses": "Wound / line",
    "woundsite": "Wound / line",
    "catheter_tip": "Wound / line",
}
SITE_ORDER = ["Blood", "Respiratory", "Urine", "Sterile fluid", "CSF", "Wound / line", "Stool", "Other"]

RESP_RANK = {  # higher = more support
    "IMV": 6, "NIPPV": 5, "CPAP": 4, "High Flow NC": 3, "Face Mask": 2, "Nasal Cannula": 1, "Room Air": 0, "Other": 0,
}

MS_HOUR = 3_600_000


# --- helpers ----------------------------------------------------------------
def die(msg: str) -> None:
    print(f"\nERROR: {msg}\n", file=sys.stderr)
    sys.exit(1)


def to_ms(s: pd.Series) -> pd.Series:
    """Datetime-like -> epoch ms (float, NaN for missing)."""
    s = pd.to_datetime(s, utc=True, errors="coerce")
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    return (s - epoch) / pd.Timedelta(milliseconds=1)


def clean(o):
    """Make an object JSON-safe (NaN -> None, numpy -> python)."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4) if abs(f) < 1e6 else f
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def rnd(x, n=3):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def load_config(path: Path) -> dict:
    if not path.exists():
        die(f"Config file not found: {path}")
    cfg = yaml.safe_load(path.read_text()) or {}
    base = path.parent
    if "clif_data_dir" not in cfg:
        die("config.yaml must set clif_data_dir")
    cfg["clif_data_dir"] = (base / cfg["clif_data_dir"]).resolve() if not Path(cfg["clif_data_dir"]).is_absolute() else Path(cfg["clif_data_dir"])
    out = Path(cfg.get("output_dir", "app/public/data"))
    cfg["output_dir"] = out if out.is_absolute() else (base / out).resolve()
    cfg.setdefault("filetype", "csv")
    if cfg["filetype"] not in ("csv", "parquet"):
        die("filetype must be 'csv' or 'parquet'")
    cfg.setdefault("timezone", "UTC")
    cfg.setdefault("icu_only", True)
    cfg.setdefault("max_patients", None)
    cfg.setdefault("axis_start", "admission")
    cfg.setdefault("tables", {}) or {}
    cfg["tables"] = cfg["tables"] or {}
    cfg.setdefault("icu_merge_gap_hours", 6)
    cfg.setdefault("resp_carry_forward_hours", 12)
    cfg.setdefault("resp_last_record_hours", 1)
    cfg.setdefault("temp_valid_range_c", [30, 45])
    cfg.setdefault("sirs", {"temp_high_c": 38.0, "temp_low_c": 36.0, "wbc_high": 12.0, "wbc_low": 4.0})
    cfg.setdefault("extra_labs", ["lactate", "crp", "creatinine", "neutrophils_absolute", "platelet_count"])
    cfg.setdefault("susceptibility_file", None)   # optional override for the CLIF microbiology_susceptibility table
    cfg.setdefault("susceptibility_synthetic", False)
    cfg.setdefault("bal_file", None)   # optional: wide BAL table (see export/bal_schema.csv); csv or parquet by extension
    if cfg["susceptibility_file"]:
        sp_ = Path(cfg["susceptibility_file"])
        cfg["susceptibility_file"] = sp_ if sp_.is_absolute() else (base / sp_).resolve()
    if cfg["bal_file"]:
        bp = Path(cfg["bal_file"])
        cfg["bal_file"] = bp if bp.is_absolute() else (base / bp).resolve()
    return cfg


def load_table(cfg: dict, name: str, required: bool):
    d: Path = cfg["clif_data_dir"]
    fname = cfg["tables"].get(name) or f"clif_{name}.{cfg['filetype']}"
    p = d / fname
    if not p.exists():
        if required:
            die(f"Required CLIF table not found: {p}\n"
                f"Check clif_data_dir and filetype in config.yaml.")
        print(f"  - {name}: not found, lane will be empty")
        return None
    if cfg["filetype"] == "csv":
        df = pd.read_csv(p, low_memory=False)
    else:
        try:
            df = pd.read_parquet(p)
        except ImportError:
            die("Reading parquet needs pyarrow:  pip install pyarrow")
    if "hospitalization_id" in df.columns:
        df["hospitalization_id"] = df["hospitalization_id"].astype(str)
    if "patient_id" in df.columns:
        df["patient_id"] = df["patient_id"].astype(str)
    print(f"  - {name}: {len(df):,} rows")
    return df


# --- per-lane builders ------------------------------------------------------
def build_adt(adt: pd.DataFrame):
    rows, icu = [], []
    adt = adt.sort_values("in_ms")
    for r in adt.itertuples():
        if math.isnan(r.in_ms):
            continue
        end = r.out_ms if not math.isnan(r.out_ms) else r.in_ms
        rows.append({"start": r.in_ms, "end": end, "category": r.location_category,
                     "type": None if pd.isna(r.location_type) else r.location_type,
                     "name": None if pd.isna(r.location_name) else r.location_name})
    return rows


def merge_icu(rows, gap_h):
    stays = []
    for r in rows:
        if r["category"] != "icu":
            continue
        if stays and r["start"] - stays[-1]["end"] <= gap_h * MS_HOUR:
            stays[-1]["end"] = max(stays[-1]["end"], r["end"])
            if r["type"] and r["type"] not in stays[-1]["types"]:
                stays[-1]["types"].append(r["type"])
        else:
            stays.append({"start": r["start"], "end": r["end"], "types": [r["type"]] if r["type"] else []})
    return stays


def build_resp(df: pd.DataFrame, cfg: dict):
    df = df.sort_values("t").copy()
    df["dev"] = df["device_category"].ffill()
    carry = cfg["resp_carry_forward_hours"] * MS_HOUR
    final = cfg["resp_last_record_hours"] * MS_HOUR
    bands, cur = [], None
    for t, dev in zip(df["t"], df["dev"]):
        if pd.isna(dev) or math.isnan(t):
            continue
        if cur is None:
            cur = {"device": dev, "start": t, "last": t}
        elif dev == cur["device"] and t - cur["last"] <= carry:
            cur["last"] = t
        else:
            switched = dev != cur["device"] and t - cur["last"] <= carry
            end = t if switched else cur["last"] + final
            if end > cur["start"]:  # a device change at the same timestamp leaves no zero-width band
                bands.append({"device": cur["device"], "start": cur["start"], "end": end})
            cur = {"device": dev, "start": t, "last": t}
    if cur is not None:
        bands.append({"device": cur["device"], "start": cur["start"], "end": cur["last"] + final})

    fio2 = df["fio2_set"].copy()
    fio2 = np.where(fio2 <= 1.5, fio2 * 100, fio2)
    peep = df["peep_set"].fillna(df["peep_obs"]) if "peep_obs" in df else df["peep_set"]
    pts = pd.DataFrame({"t": df["t"], "fio2": fio2, "peep": peep})
    fio2_pts = [[t, v] for t, v in zip(pts["t"], pts["fio2"]) if not (math.isnan(t) or math.isnan(v))]
    peep_pts = [[t, v] for t, v in zip(pts["t"], pts["peep"]) if not (math.isnan(t) or math.isnan(v))]
    return bands, fio2_pts, peep_pts


def canonical_pressor_dose(cat: str, dose: float, unit: str):
    """Return dose in mcg/kg/min (or units/min for vasopressin), else None."""
    if math.isnan(dose):
        return None
    u = (unit or "").lower()
    if cat == "vasopressin":
        if u in ("units/min", "u/min"):
            return dose
        if u in ("units/hour", "units/hr", "u/hr", "u/hour"):
            return dose / 60.0
        if u in ("milliunits/kg/min", "mu/kg/min"):
            return None
        return None
    if u == "mcg/kg/min":
        return dose
    if u in ("mcg/kg/hour", "mcg/kg/hr"):
        return dose / 60.0
    if u in ("ng/kg/min",):
        return dose / 1000.0
    return None


def build_pressors(df: pd.DataFrame):
    """Step series per pressor (canonical units) and a norepinephrine-equivalent total."""
    df = df[df["med_category"].isin(PRESSORS)].copy()
    if df.empty:
        return {"agents": {}, "nee": []}
    df = df.sort_values(["t", "med_order_id"])
    agents = {}
    for cat, g in df.groupby("med_category"):
        state, series = {}, []
        for t, grp in g.groupby("t", sort=True):
            for r in grp.itertuples():
                d = canonical_pressor_dose(cat, float(r.med_dose) if not pd.isna(r.med_dose) else math.nan, r.med_dose_unit)
                if d is None and r.mar_action_category != "stop":
                    continue
                state[r.med_order_id] = 0.0 if r.mar_action_category == "stop" else d
            total = sum(state.values())
            if not series or abs(series[-1][1] - total) > 1e-9:
                series.append([t, total])
        if any(v > 0 for _, v in series):
            unit = "units/min" if cat == "vasopressin" else "mcg/kg/min"
            agents[cat] = {"unit": unit, "dose": series}
    # norepinephrine equivalents
    times = sorted({t for a in agents.values() for t, _ in a["dose"]})
    nee = []
    if times:
        parts = {}
        for cat, a in agents.items():
            ts = np.array([t for t, _ in a["dose"]])
            vs = np.array([v for _, v in a["dose"]])
            idx = np.searchsorted(ts, times, side="right") - 1
            vals = np.where(idx >= 0, vs[np.clip(idx, 0, None)], 0.0)
            f = NEE_FACTOR.get(cat, 0.0)
            parts[cat] = vals * f
            a["nee"] = [[t, float(v)] for t, v in zip(times, parts[cat])]
        total = sum(parts.values())
        nee = [[t, float(v)] for t, v in zip(times, total)]
    return {"agents": agents, "nee": nee}


def pressor_hours(nee):
    h = 0.0
    for (t0, v0), (t1, _) in zip(nee, nee[1:]):
        if v0 > 0:
            h += (t1 - t0) / MS_HOUR
    return h


SUSC_CODE = {  # CLIF 2.1 susceptibility_category (plus common raw spellings, in case a site has not mapped yet)
    "susceptible": "S", "non_susceptible": "NS", "non susceptible": "NS", "non-susceptible": "NS", "indeterminate": "IND", "na": "NA",
    "sensitive": "S", "s": "S", "resistant": "NS", "r": "NS", "intermediate": "NS", "i": "NS"}


def load_susceptibility(cfg: dict):
    """CLIF microbiology_susceptibility -> {organism_id: [result, ...]}, or None if the table is absent.

    Read from clif_data_dir (clif_microbiology_susceptibility.<ext>) unless `susceptibility_file` points elsewhere.
    Columns (CLIF 2.1): organism_id, antimicrobial_name, antimicrobial_category, sensitivity_name,
    susceptibility_name, susceptibility_category (susceptible | non_susceptible | indeterminate | NA).
    """
    f = cfg.get("susceptibility_file")
    if f:
        if not f.exists():
            die(f"susceptibility_file not found: {f}")
        df = pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f, low_memory=False)
        print(f"  - microbiology_susceptibility: {len(df):,} rows ({f.name})")
    else:
        df = load_table(cfg, "microbiology_susceptibility", False)
        if df is None:
            return None
    need = {"organism_id", "antimicrobial_name", "susceptibility_category"}
    if need - set(df.columns):
        die(f"microbiology_susceptibility needs columns {sorted(need)}; missing {sorted(need - set(df.columns))}")
    out, unknown = {}, set()
    for r in df.to_dict("records"):
        oid = _oid(r.get("organism_id"))
        if oid is None:
            continue
        raw_cat = _s(r.get("susceptibility_category"))
        code = SUSC_CODE.get((raw_cat or "NA").strip().lower())
        if code is None:
            unknown.add(raw_cat); code = "NA"
        val = _s(r.get("sensitivity_name"))
        out.setdefault(oid, []).append({"a": str(r["antimicrobial_name"]).strip(), "c": _s(r.get("antimicrobial_category")), "s": code,
                                        "raw": _s(r.get("susceptibility_name")), "val": None if val in (None, "NA") else val})
    if unknown:
        print(f"    note: unmapped susceptibility_category values shown as NA: {sorted(unknown)[:8]}")
    for v in out.values():
        v.sort(key=lambda x: x["a"].lower())
    print(f"    {len(out):,} organisms with susceptibility results")
    return out


def _oid(v):
    v = _s(v)
    return v[:-2] if v and v.endswith(".0") else v


def build_micro(df: pd.DataFrame, susc=None):
    df = df.copy()
    df["t_col"] = df["collect_ms"].fillna(df["order_ms"])
    out = []
    for (t, fcat, fname, meth), g in df.groupby(["t_col", "fluid_category", "fluid_name", "method_name"], dropna=False):
        if math.isnan(t):
            continue
        orgs = [o for o in g["organism_name"].dropna().unique() if str(o).upper() != "CANCELLED"]
        cancelled = bool((g["organism_name"].astype(str).str.upper() == "CANCELLED").any()) and not orgs
        res = g["result_ms"].max()
        sus = []
        if susc and "organism_id" in g.columns:
            seen = set()
            for oid, nm in zip(g["organism_id"], g["organism_name"]):
                oid = _oid(oid)
                if oid in susc and _s(nm) and str(nm) not in seen:
                    seen.add(str(nm))
                    sus.append({"organism": str(nm), "results": susc[oid]})
        out.append({
            "susc": sus,
            "t": t,
            "result_t": None if pd.isna(res) else res,
            "order_t": None if pd.isna(g["order_ms"].min()) else g["order_ms"].min(),
            "site": SITE_GROUP.get(fcat, "Other"),
            "fluid": None if pd.isna(fname) else fname,
            "method": None if pd.isna(meth) else meth,
            "organisms": [str(o) for o in orgs],
            "positive": bool(orgs),
            "cancelled": cancelled,
        })
    return sorted(out, key=lambda r: r["t"])


# --- BAL (bronchoalveolar lavage) --------------------------------------------
BAL_BACT = ["acinetobacter calcoaceticus-baumannii complex", "enterobacter cloacae complex", "escherichia coli", "haemophilus influenzae",
            "klebsiella aerogenes", "klebsiella oxytoca", "klebsiella pneumoniae group", "moraxella catarrhalis", "proteus spp",
            "pseudomonas aeruginosa", "serratia marcescens", "staphylococcus aureus", "streptococcus agalactiae", "streptococcus pneumoniae",
            "streptococcus pyogenes", "legionella pneumophila", "chlamydia_pneumoniae_lower_resp", "chlamydia pneumoniae",
            "mycoplasma_pneumoniae_lower_resp", "mycoplasma pneumoniae", "bordetella parapertussis", "bordetella pertussis"]
BAL_VIRUS = ["adenovirus_lower_resp", "adenovirus", "adenovirus - rvpdmb", "coronavirus", "coronavirus 229e", "coronavirus hku1", "coronavirus nl63",
             "coronavirus oc43", "human_metapneumovirus_lower_resp", "human metapneumovirus", "human_rhinovirus_enterovirus_lower_resp",
             "human rhinovirus/enterovirus", "influenza a", "influenza b", "influenza a h1 (seasonal)", "influenza a h1-2009", "influenza a h3 (seasonal)",
             "influenza-a respan23", "influenza-b respan21", "parainfluenza virus", "parainfluenza virus 4", "para influ 1", "para influ 2", "para influ 3",
             "respiratory syncytial virus", "respiratory syncytial-virus respan22", "covid_19", "sars-cov-2"]
BAL_GENES = ["ctx-m", "imp", "kpc", "meca/c and mrej", "ndm", "oxa-48-like", "vim"]
BAL_ANTIGEN = ["streptococcus pneumoniae antigen,urine 1", "legionella antigen (eia) urine 1"]
BAL_DIFF = {"neutro": "bal_pct_neutro", "macro": "bal_pct_macro", "lympho": "bal_pct_lympho", "eos": "bal_pct_eos",
            "plasma": "bal_pct_plasma", "mono": "bal_pct_mono", "other": "bal_pct_other"}
_NEG_WORDS = ("not detected", "negative", "none detected", "no ", "nd", "not tested", "n/a", "na")
_INSIGNIFICANT = ("light", "rare", "few", "normal", "flora", "<10", "1,000", "scant")


def _s(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() in ("", "nan", "None") else str(v).strip()


def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _b(v) -> bool:
    return _s(v) is not None and str(v).strip().lower() in ("true", "1", "yes")


def _detected(v) -> bool:
    v = (_s(v) or "").lower()
    return bool(v) and not v.startswith(_NEG_WORDS)


def _pretty(col: str) -> str:
    n = col.replace("_lower_resp", "").replace("_", " ")
    if col == "streptococcus pneumoniae antigen,urine 1":
        return "Urine S. pneumoniae antigen"
    if col == "legionella antigen (eia) urine 1":
        return "Urine Legionella antigen"
    special = {"covid 19": "SARS-CoV-2", "sars-cov-2": "SARS-CoV-2", "meca/c and mrej": "mecA/C & MREJ (MRSA)", "ctx-m": "CTX-M (ESBL)", "kpc": "KPC", "ndm": "NDM",
               "imp": "IMP", "vim": "VIM", "oxa-48-like": "OXA-48-like", "respiratory syncytial virus": "RSV", "human rhinovirus/enterovirus": "Rhinovirus/Enterovirus",
               "human rhinovirus enterovirus": "Rhinovirus/Enterovirus", "human metapneumovirus": "hMPV"}
    if n in special:
        return special[n]
    return n[:1].upper() + n[1:] if n.islower() else n


def build_bal(df: pd.DataFrame, susc=None):
    """One dict per BAL collection. Result columns follow bal_schema.csv (wide: one row per BAL)."""
    out = []
    cols = set(df.columns)
    for r in df.sort_values("t").to_dict("records"):
        t = _num(r.get("t"))
        if t is None:
            continue
        panel = [c for c in BAL_BACT + BAL_VIRUS if c in cols and _s(r.get(c)) is not None]
        detected = [{"name": _pretty(c), "kind": "virus" if c in BAL_VIRUS else "bacteria", "result": _s(r.get(c))} for c in panel if _detected(r.get(c))]
        genes = [{"name": _pretty(c), "result": _s(r.get(c))} for c in BAL_GENES if c in cols and _detected(r.get(c))]
        genes_tested = sum(1 for c in BAL_GENES if c in cols and _s(r.get(c)) is not None)
        antigens = [{"name": _pretty(c), "result": _s(r.get(c)) if c in cols else None} for c in BAL_ANTIGEN[:2]]  # always listed; None = not tested

        orgs = []
        for i in range(1, 7):
            nm = _s(r.get(f"organism_{i}_name"))
            if nm:
                q = _s(r.get(f"organism_{i}_quantity"))
                text = f"{nm} {q or ''}".lower()
                oid = _oid(r.get(f"organism_id{i}"))
                orgs.append({"name": nm, "quantity": q, "significant": not any(w in text for w in _INSIGNIFICANT),
                             "susc": (susc or {}).get(oid) if oid else None})
        fungal = [{"name": _s(r.get(f"culture_fungal_w_smear_bal_organism_id_{i}")), "smear": _s(r.get(f"fungal_culture_stain_report_{i}"))}
                  for i in (1, 2, 3) if _s(r.get(f"culture_fungal_w_smear_bal_organism_id_{i}")) or _s(r.get(f"fungal_culture_stain_report_{i}"))]
        gm_idx = _num(r.get("pathogen_galactomannan"))
        gm_txt = _s(r.get("aspergillus galactomannan antigen(nmh/lfh)"))
        pjp = _s(r.get("pneumocystis jirovecii(carinii), dfa (nmh/lfh)"))

        cats = []
        if any(o["significant"] and not str(o["name"]).upper().startswith(("YEAST", "CANDIDA")) for o in orgs) or any(d["kind"] == "bacteria" for d in detected) or _b(r.get("pathogen_bacteria")):
            cats.append("bacterial")
        if any(d["kind"] == "virus" for d in detected) or _b(r.get("pathogen_virus")):
            cats.append("viral")
        if (gm_idx is not None and gm_idx >= 0.5) or _detected(pjp) or _b(r.get("pathogen_aspergillus")) or _b(r.get("pathogen_fungi")) or any(
                o["significant"] and str(o["name"]).upper().startswith(("YEAST", "CANDIDA")) for o in orgs):
            cats.append("fungal")
        if not cats and any(not o["significant"] and str(o["name"]).upper().startswith(("YEAST", "CANDIDA")) for o in orgs):
            cats.append("colonization")

        out.append({
            "t": t,
            "day_hosp": None if _num(r.get("day_of_hospitalization")) is None else int(_num(r.get("day_of_hospitalization"))),
            "day_intub": None if _num(r.get("day_of_intubation")) is None else int(_num(r.get("day_of_intubation"))),
            "type": _s(r.get("bal_test_type")), "procedure": _s(r.get("procedure_name")), "side": _s(r.get("side")), "bal_type": _s(r.get("bal_type")),
            "accession": _s(r.get("order_accession_num")),
            "synthetic": _b(r.get("synthetic")),
            "categories": cats, "positive": bool({"bacterial", "viral", "fungal"} & set(cats)),
            "summary": _s(r.get("pathogen_result")),
            "cells": {"wbc": _num(r.get("bal_wbc_count")), "rbc": _num(r.get("bal_rbc_count")),
                      "diff": {k: _num(r.get(c)) for k, c in BAL_DIFF.items() if _num(r.get(c)) is not None},
                      "abs": {k: _num(r.get(c)) for k, c in (("neutrophils", "abs_neutrophils"), ("lymphocytes", "abs_lymphocytes"), ("eosinophils", "abs_eosinophils")) if _num(r.get(c)) is not None}},
            "gram": {"organisms": _s(r.get("gram_stain_report_organisms")), "wbc": _s(r.get("gram_stain_report_wbc")), "rbc": _s(r.get("gram_stain_report_rbc"))},
            "culture": {"no_growth": (_s(r.get("negative_for_growth")) or "").lower().startswith(("y", "true", "1")), "organisms": orgs},
            "panel": {"tested": bool(panel), "n_tested": len(panel), "detected": detected, "genes": genes, "genes_tested": genes_tested},
            "fungal": {"culture": fungal, "galactomannan_index": gm_idx, "galactomannan": gm_txt, "pjp_dfa": pjp},
            "amylase": _num(r.get("amylase")),
            "mrsa_pcr": _s(r.get("respiratory_mrsa_pcr")), "antigens": antigens,
            "comments": [x for x in (_s(r.get("pathogen_comments")), _s(r.get("comments"))) if x],
        })
    return out


def build_abx(df: pd.DataFrame):
    df = df[df["mar_action_category"].astype(str).str.lower().isin(["given", "start", "going", "dose_change"])]
    is_abx = (df["med_group"] == ANTIBIOTIC_GROUP) | df["med_category"].isin(ANTIMICROBIAL_CATEGORIES)
    df = df[is_abx].sort_values("t")
    out = {}
    for cat, g in df.groupby("med_category"):
        out[cat] = {
            "name": str(g["med_name"].iloc[0]),
            "class": ANTIMICROBIAL_CLASS.get(cat, "antibacterial"),
            "doses": [[r.t, None if pd.isna(r.med_dose) else float(r.med_dose),
                       None if pd.isna(r.med_dose_unit) else r.med_dose_unit,
                       None if pd.isna(r.med_route_category) else r.med_route_category]
                      for r in g.itertuples() if not math.isnan(r.t)],
        }
    return out


# --- main -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.yaml"))
    args = ap.parse_args()
    cfg = load_config(Path(args.config).resolve())

    print(f"Reading CLIF {cfg['filetype']} tables from {cfg['clif_data_dir']}")
    if not cfg["clif_data_dir"].is_dir():
        die(f"clif_data_dir does not exist or is not a folder: {cfg['clif_data_dir']}")
    T = {n: load_table(cfg, n, True) for n in REQUIRED}
    T.update({n: load_table(cfg, n, False) for n in OPTIONAL})

    pat = T["patient"].set_index("patient_id")
    hosp = T["hospitalization"].copy()
    hosp["adm_ms"] = to_ms(hosp["admission_dttm"])
    hosp["dis_ms"] = to_ms(hosp["discharge_dttm"])

    adt = T["adt"].copy()
    adt["in_ms"], adt["out_ms"] = to_ms(adt["in_dttm"]), to_ms(adt["out_dttm"])

    if cfg["icu_only"]:
        keep = set(adt.loc[adt["location_category"] == "icu", "hospitalization_id"])
        hosp = hosp[hosp["hospitalization_id"].isin(keep)]
    hosp = hosp.sort_values(["patient_id", "adm_ms"])
    if cfg["max_patients"]:
        hosp = hosp.head(int(cfg["max_patients"]))
    ids = set(hosp["hospitalization_id"])
    print(f"Exporting {len(ids)} hospitalizations")

    def sub(name, extra=None):
        df = T.get(name)
        if df is None:
            return None
        df = df[df["hospitalization_id"].isin(ids)].copy()
        for col, src in (extra or {}).items():
            df[col] = to_ms(df[src])
        return df

    adt = adt[adt["hospitalization_id"].isin(ids)]
    resp = sub("respiratory_support", {"t": "recorded_dttm"})
    cont = sub("medication_admin_continuous", {"t": "admin_dttm"})
    inter = sub("medication_admin_intermittent", {"t": "admin_dttm"})
    micro = sub("microbiology_culture", {"collect_ms": "collect_dttm", "order_ms": "order_dttm", "result_ms": "result_dttm"})
    labs = sub("labs", {"t": "lab_collect_dttm", "t_res": "lab_result_dttm"})
    vit = sub("vitals", {"t": "recorded_dttm"})
    SUSC = load_susceptibility(cfg)
    bal = None
    if cfg["bal_file"]:
        bf = cfg["bal_file"]
        if not bf.exists():
            die(f"bal_file not found: {bf}")
        bal = pd.read_parquet(bf) if bf.suffix == ".parquet" else pd.read_csv(bf, low_memory=False)
        bal["hospitalization_id"] = bal["hospitalization_id"].astype(str)
        bal = bal[bal["hospitalization_id"].isin(ids)].copy()
        bal["t"] = to_ms(bal["bal_collection_dttm"])
        print(f"  - BAL file: {len(bal):,} rows for {bal['hospitalization_id'].nunique()} hospitalizations ({bf.name})")
    if labs is not None:
        labs["t"] = labs["t"].fillna(labs["t_res"])
    lo, hi = cfg["temp_valid_range_c"]
    temp_dropped = 0
    if vit is not None:
        tv = vit[vit["vital_category"] == "temp_c"].copy()
        tv["vital_value"] = pd.to_numeric(tv["vital_value"], errors="coerce")
        bad = ~tv["vital_value"].between(lo, hi)
        temp_dropped = int(bad.sum())
        vit_temp = tv[~bad]
    else:
        vit_temp = None

    g_adt = {k: v for k, v in adt.groupby("hospitalization_id")}
    g = lambda df: {k: v for k, v in df.groupby("hospitalization_id")} if df is not None else {}
    g_resp, g_cont, g_inter, g_micro, g_labs, g_temp, g_bal = map(g, (resp, cont, inter, micro, labs, vit_temp, bal))

    out_dir: Path = cfg["output_dir"]
    (out_dir / "patients").mkdir(parents=True, exist_ok=True)
    for f in (out_dir / "patients").glob("*.json"):
        f.unlink()

    wanted_labs = ["wbc"] + list(cfg["extra_labs"])
    index = []
    for h in hosp.itertuples():
        hid = h.hospitalization_id
        p = pat.loc[h.patient_id] if h.patient_id in pat.index else None
        adt_rows = build_adt(g_adt[hid]) if hid in g_adt else []
        icu_stays = merge_icu(adt_rows, cfg["icu_merge_gap_hours"])

        first_contact = min([r["start"] for r in adt_rows], default=h.adm_ms)
        axis_start = h.adm_ms if (cfg["axis_start"] == "admission" and not math.isnan(h.adm_ms)) else min(first_contact, h.adm_ms if not math.isnan(h.adm_ms) else first_contact)
        axis_end = max([x for x in [h.dis_ms] + [r["end"] for r in adt_rows] if not math.isnan(x)], default=axis_start)

        bands, fio2, peep = build_resp(g_resp[hid], cfg) if hid in g_resp else ([], [], [])
        press = build_pressors(g_cont[hid]) if hid in g_cont else {"agents": {}, "nee": []}
        mic = build_micro(g_micro[hid], SUSC) if hid in g_micro else []
        abx = build_abx(g_inter[hid]) if hid in g_inter else {}
        bal_out = build_bal(g_bal[hid], SUSC) if hid in g_bal else []

        labs_out = {}
        if hid in g_labs:
            gl = g_labs[hid]
            for cat in wanted_labs:
                x = gl[gl["lab_category"] == cat].dropna(subset=["t", "lab_value_numeric"]).sort_values("t")
                if len(x):
                    labs_out[cat] = {"unit": None if x["reference_unit"].dropna().empty else str(x["reference_unit"].dropna().iloc[0]),
                                     "values": [[t, float(v)] for t, v in zip(x["t"], x["lab_value_numeric"])]}
        temps = []
        if hid in g_temp:
            x = g_temp[hid].sort_values("t")
            temps = [[t, float(v)] for t, v in zip(x["t"], x["vital_value"])]

        doc = {
            "id": hid, "patient_id": h.patient_id,
            "axis": {"start": axis_start, "end": axis_end, "admission": h.adm_ms, "discharge": h.dis_ms},
            "demographics": {"age": None if pd.isna(h.age_at_admission) else int(h.age_at_admission),
                             "sex": None if p is None else p.get("sex_category"),
                             "discharge": None if pd.isna(h.discharge_category) else h.discharge_category},
            "adt": adt_rows, "icu_stays": icu_stays,
            "resp": {"bands": bands, "fio2": fio2, "peep": peep},
            "pressors": press, "micro": mic, "abx": abx, "bal": bal_out,
            "temp": temps, "labs": labs_out,
        }
        (out_dir / "patients" / f"{hid}.json").write_text(json.dumps(clean(doc), separators=(",", ":"), allow_nan=False))

        # ----- cohort index row -----
        devs = {b["device"] for b in bands}
        sirs = cfg["sirs"]
        wbc = [v for _, v in labs_out.get("wbc", {}).get("values", [])]
        icu_h = sum(s["end"] - s["start"] for s in icu_stays) / MS_HOUR
        orgs = sorted({o for m in mic for o in m["organisms"]})
        index.append({
            "id": hid, "patient_id": h.patient_id,
            "age": doc["demographics"]["age"], "sex": doc["demographics"]["sex"],
            "died": doc["demographics"]["discharge"] == "Expired",
            "admission": h.adm_ms, "los_days": rnd((axis_end - h.adm_ms) / MS_HOUR / 24, 1) if not math.isnan(h.adm_ms) else None,
            "icu_hours": rnd(icu_h, 1), "n_icu_stays": len(icu_stays),
            "imv": "IMV" in devs, "niv": bool(devs & {"NIPPV", "CPAP"}), "hfnc": "High Flow NC" in devs,
            "pressor": bool(press["nee"]) and max(v for _, v in press["nee"]) > 0,
            "pressor_hours": rnd(pressor_hours(press["nee"]), 1),
            "n_cultures": len(mic), "positive_culture": any(m["positive"] for m in mic),
            "blood_culture_positive": any(m["positive"] and m["site"] == "Blood" for m in mic),
            "n_bal": len(bal_out), "bal_positive": any(b["positive"] for b in bal_out),
            "organisms": orgs, "sites_positive": sorted({m["site"] for m in mic if m["positive"]}),
            "antibiotics": sorted(abx.keys()), "n_antibiotics": len(abx),
            "max_temp": rnd(max((v for _, v in temps), default=math.nan), 1),
            "fever": any(v > sirs["temp_high_c"] for _, v in temps),
            "max_wbc": rnd(max(wbc, default=math.nan), 1), "min_wbc": rnd(min(wbc, default=math.nan), 1),
            "wbc_abnormal": any(v > sirs["wbc_high"] or v < sirs["wbc_low"] for v in wbc),
        })

    meta = {
        "source": str(cfg["clif_data_dir"]), "filetype": cfg["filetype"], "timezone": cfg["timezone"],
        "n": len(index), "sirs": cfg["sirs"], "extra_labs": cfg["extra_labs"],
        "tables_present": [n for n in OPTIONAL if T.get(n) is not None],
        "temp_values_dropped": temp_dropped, "has_bal": bal is not None, "has_susceptibility": SUSC is not None, "susc_synthetic": bool(cfg.get("susceptibility_synthetic")), "bal_synthetic": bool(bal is not None and "synthetic" in bal.columns and bal["synthetic"].astype(str).str.lower().eq("true").any()),
        "pressor_nee_factors": NEE_FACTOR,
    }
    (out_dir / "index.json").write_text(json.dumps(clean({"meta": meta, "hospitalizations": index}), separators=(",", ":"), allow_nan=False))
    print(f"Wrote {len(index)} timelines to {out_dir}  (dropped {temp_dropped} implausible temperatures)")


if __name__ == "__main__":
    main()
