#!/usr/bin/env python3
"""Generate SYNTHETIC antibiograms (susceptibility results) for the dashboard demo.

The public MIMIC demo has no susceptibility table. This fabricates one so the clickable
Susceptibility panel can be previewed. It covers
  * every culture row in clif_microbiology_culture with a bacterial organism (keyed by organism_id), and
  * every significant bacterial organism in the synthetic BAL file (it fills organism_id1..6 there and
    keys the antibiogram by that id, the same way real BAL data would link).
Run AFTER make_synthetic_bal.py. Nothing here is real patient data.

    python3 -I export/make_synthetic_susceptibility.py --config config.yaml

Output follows the CLIF 2.1 `microbiology_susceptibility` table (one row per organism x antimicrobial):
    organism_id             links to microbiology_culture.organism_id (and BAL organism_id1..6)
    antimicrobial_name      raw name as the lab reports it
    antimicrobial_category  CLIF mCIDE antimicrobial category (e.g. piperacillin_tazobactam)
    sensitivity_name        raw test value, here an MIC in mcg/mL (e.g. "<=0.25"), or "not reported"
    susceptibility_name     raw interpretation as reported (S / I / R / Repeat test / NA)
    susceptibility_category CLIF category: susceptible | non_susceptible | indeterminate | NA
Intermediate (I) is mapped to non_susceptible (non-susceptible = I or R); the raw I stays in susceptibility_name.
No hospitalization_id column: CLIF links susceptibility to the encounter through organism_id.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export import load_config, load_table  # noqa: E402

HERE = Path(__file__).resolve().parent
SEED = 20260614
MICS = ["<=0.25", "0.5", "1", "2", "4", "8", "16", ">=32"]

# (panel name, drugs, baseline resistance probability per drug is set in PROFILE below)
PANELS = {
    "staph": ["Oxacillin", "Cefazolin", "Clindamycin", "Erythromycin", "Gentamicin", "Levofloxacin", "Linezolid", "Tetracycline", "TMP-SMX", "Vancomycin"],
    "enterics": ["Ampicillin", "Ampicillin-sulbactam", "Piperacillin-tazobactam", "Cefazolin", "Ceftriaxone", "Cefepime", "Meropenem", "Gentamicin",
                 "Tobramycin", "Ciprofloxacin", "TMP-SMX"],
    "pseudo": ["Piperacillin-tazobactam", "Ceftazidime", "Cefepime", "Meropenem", "Gentamicin", "Tobramycin", "Amikacin", "Ciprofloxacin", "Levofloxacin"],
    "acineto": ["Ampicillin-sulbactam", "Ceftazidime", "Cefepime", "Meropenem", "Gentamicin", "Tobramycin", "Ciprofloxacin", "TMP-SMX"],
    "entero": ["Ampicillin", "Penicillin", "Vancomycin", "Linezolid", "Levofloxacin", "Gentamicin (synergy)"],
    "strep": ["Penicillin", "Ceftriaxone", "Erythromycin", "Clindamycin", "Levofloxacin", "Vancomycin"],
    "hi": ["Ampicillin", "Ampicillin-sulbactam", "Ceftriaxone", "TMP-SMX", "Levofloxacin"],
    "moraxella": ["Ampicillin", "Amoxicillin-clavulanate", "Ceftriaxone", "TMP-SMX", "Levofloxacin"],
    "anaerobe": ["Penicillin", "Ampicillin-sulbactam", "Metronidazole", "Clindamycin", "Meropenem"],
    "steno": ["TMP-SMX", "Levofloxacin", "Minocycline", "Ceftazidime"],
}


def panel_for(name: str):
    n = name.upper()
    if re.search(r"YEAST|CANDIDA|FLORA|CANCELLED|VIRUS|DIFFICILE|^POSITIVE$|GRAM (NEG|POS)|GRAM-|ANAEROBIC GRAM", n):
        return None
    if "AUREUS" in n or "COAGULASE" in n:
        return "staph"
    if re.search(r"ESCHERICHIA|KLEBSIELLA|ENTEROBACTER|CITROBACTER|PROTEUS|SERRATIA", n):
        return "enterics"
    if "PSEUDOMONAS" in n:
        return "pseudo"
    if "ACINETOBACTER" in n:
        return "acineto"
    if "ENTEROCOCCUS" in n:
        return "entero"
    if "STREPTOCOCC" in n:
        return "strep"
    if "HAEMOPHILUS" in n:
        return "hi"
    if "MORAXELLA" in n:
        return "moraxella"
    if re.search(r"BACTEROIDES|PREVOTELLA|FUSOBACTERIUM|PORPHYROMONAS|CLOSTRIDIUM PERFRINGENS", n):
        return "anaerobe"
    if "STENOTROPHOMONAS" in n:
        return "steno"
    return None


def antibiogram(name: str, oid: str):
    """Return [(drug, category, mic)] with plausible co-resistance patterns for the organism."""
    key = panel_for(name)
    if key is None:
        return []
    r = random.Random(f"{SEED}-{oid}")
    drugs = PANELS[key]
    res = {d: "susceptible" for d in drugs}

    def setr(d, cat):
        if d in res:
            res[d] = cat

    n = name.upper()
    if key == "staph":
        mrsa = "METHICILLIN RESISTANT" in n or "MRSA" in n or r.random() < 0.4
        if mrsa:
            setr("Oxacillin", "resistant"); setr("Cefazolin", "resistant")
        if r.random() < 0.55: setr("Erythromycin", "resistant")
        if r.random() < 0.35: setr("Clindamycin", "resistant")
        if mrsa and r.random() < 0.4: setr("Levofloxacin", "resistant")
        if r.random() < 0.08: setr("Tetracycline", "resistant")
    elif key == "enterics":
        if r.random() < 0.55 and "KLEBSIELLA" not in n: setr("Ampicillin", "resistant")
        if "KLEBSIELLA" in n or "ENTEROBACTER" in n or "CITROBACTER" in n or "SERRATIA" in n:
            setr("Ampicillin", "resistant")
        if r.random() < 0.3: setr("Ampicillin-sulbactam", "resistant" if r.random() < 0.7 else "intermediate")
        if r.random() < 0.3: setr("Cefazolin", "resistant")
        esbl = r.random() < 0.22
        if esbl:
            for d in ("Cefazolin", "Ceftriaxone", "Ampicillin-sulbactam"): setr(d, "resistant")
            setr("Cefepime", "resistant" if r.random() < 0.6 else "intermediate")
            if r.random() < 0.4: setr("Piperacillin-tazobactam", "intermediate")
        if r.random() < 0.25: setr("Ciprofloxacin", "resistant")
        if r.random() < 0.2: setr("TMP-SMX", "resistant")
        if r.random() < 0.1: setr("Gentamicin", "resistant")
        if r.random() < 0.04: setr("Meropenem", "resistant")
    elif key == "pseudo":
        if r.random() < 0.3: setr("Ciprofloxacin", "resistant" if r.random() < 0.6 else "intermediate")
        if r.random() < 0.25: setr("Levofloxacin", "intermediate")
        if r.random() < 0.2: setr("Piperacillin-tazobactam", "resistant")
        if r.random() < 0.15: setr("Ceftazidime", "resistant")
        if r.random() < 0.1: setr("Cefepime", "intermediate")
        if r.random() < 0.15: setr("Meropenem", "resistant")
        if r.random() < 0.12: setr("Tobramycin", "resistant")
    elif key == "acineto":
        if r.random() < 0.5:
            for d in ("Ceftazidime", "Cefepime", "Ciprofloxacin", "Ampicillin-sulbactam"): setr(d, "resistant")
        if r.random() < 0.35: setr("Meropenem", "resistant")
    elif key == "entero":
        faecium = "FAECIUM" in n
        if faecium or r.random() < 0.15:
            for d in ("Ampicillin", "Penicillin", "Levofloxacin"): setr(d, "resistant")
        if r.random() < (0.35 if faecium else 0.03): setr("Vancomycin", "resistant")
        if r.random() < 0.05: setr("Linezolid", "intermediate")
    elif key == "strep":
        if "PNEUMONIAE" in n and r.random() < 0.25: setr("Penicillin", "intermediate")
        if r.random() < 0.3: setr("Erythromycin", "resistant")
        if r.random() < 0.2: setr("Clindamycin", "resistant")
    elif key in ("hi", "moraxella"):
        if r.random() < 0.3: setr("Ampicillin", "resistant")
        if r.random() < 0.15: setr("TMP-SMX", "resistant")
    elif key == "anaerobe":
        if r.random() < 0.4: setr("Clindamycin", "resistant")
        if r.random() < 0.3: setr("Penicillin", "resistant")
    elif key == "steno":
        if r.random() < 0.2: setr("Levofloxacin", "intermediate")
    out = []
    for d in drugs:
        cat = res[d]
        i = {"susceptible": r.randint(0, 3), "intermediate": r.randint(4, 5), "resistant": r.randint(6, 7)}[cat]
        mic = MICS[i] if r.random() < 0.9 else None
        out.append((d, cat, mic))
    return out


def _category(drug: str) -> str:
    """Display name -> CLIF antimicrobial_category."""
    special = {"TMP-SMX": "trimethoprim_sulfamethoxazole", "Gentamicin (synergy)": "gentamicin"}
    if drug in special:
        return special[drug]
    return re.sub(r"[^a-z0-9]+", "_", drug.lower()).strip("_")


CLIF_ABX = {  # subset of mCIDE clif_microbiology_susceptibility_antibiotics_category.csv used here
    "amikacin", "amoxicillin_clavulanate", "ampicillin", "ampicillin_sulbactam", "cefazolin", "cefepime", "ceftazidime", "ceftriaxone",
    "ciprofloxacin", "clindamycin", "erythromycin", "gentamicin", "levofloxacin", "linezolid", "meropenem", "metronidazole", "minocycline",
    "oxacillin", "penicillin", "piperacillin_tazobactam", "tetracycline", "tobramycin", "trimethoprim_sulfamethoxazole", "vancomycin"}


def clif_rows(oid: str, ab):
    """(drug, susceptible|intermediate|resistant, mic) -> CLIF microbiology_susceptibility rows."""
    r = random.Random(f"{SEED}-na-{oid}")
    out = []
    for d, cat, mic in ab:
        c = _category(d)
        assert c in CLIF_ABX, c
        x = r.random()
        if x < 0.03:      # occasionally not reported, like the dictionary's Ertapenem example
            out.append(dict(organism_id=oid, antimicrobial_name=d, antimicrobial_category=c, sensitivity_name="not reported",
                            susceptibility_name=None, susceptibility_category="NA"))
            continue
        if x < 0.045:     # rare indeterminate result
            out.append(dict(organism_id=oid, antimicrobial_name=d, antimicrobial_category=c, sensitivity_name=mic or "not reported",
                            susceptibility_name="Repeat test", susceptibility_category="indeterminate"))
            continue
        raw = {"susceptible": "S", "intermediate": "I", "resistant": "R"}[cat]
        out.append(dict(organism_id=oid, antimicrobial_name=d, antimicrobial_category=c, sensitivity_name=mic or "not reported",
                        susceptibility_name=raw, susceptibility_category="susceptible" if cat == "susceptible" else "non_susceptible"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE.parent / "config.yaml"))
    ap.add_argument("--out", default=str(HERE.parent / "data" / "synthetic" / "clif_microbiology_susceptibility.csv"))
    a = ap.parse_args()
    cfg = load_config(Path(a.config).resolve())
    rows = []

    cult = load_table(cfg, "microbiology_culture", False)
    if cult is not None:
        c = cult.dropna(subset=["organism_name"])
        for r in c.drop_duplicates("organism_id").itertuples():
            rows += clif_rows(str(r.organism_id), antibiogram(str(r.organism_name), str(r.organism_id)))

    bal_path = cfg.get("bal_file")
    if bal_path and Path(bal_path).exists():
        bal = pd.read_csv(bal_path, low_memory=False)
        nxt = 9_000_000
        for k in range(1, 7):
            bal[f"organism_id{k}"] = bal[f"organism_id{k}"].astype("object") if f"organism_id{k}" in bal.columns else None
        for i, row in bal.iterrows():
            for k in range(1, 7):
                nm = row.get(f"organism_{k}_name")
                if not isinstance(nm, str):
                    continue
                q = str(row.get(f"organism_{k}_quantity") or "").lower()
                if any(w in q for w in ("light", "rare", "few")):
                    continue
                oid = str(nxt); nxt += 1
                ab = antibiogram(nm + (" METHICILLIN RESISTANT" if "(MRSA)" in nm else ""), oid)
                if "(MSSA)" in nm:   # keep the label consistent with the antibiogram
                    ab = [(d, "susceptible" if d in ("Oxacillin", "Cefazolin") else cat, mic) for d, cat, mic in ab]
                if not ab:
                    continue
                bal.at[i, f"organism_id{k}"] = oid
                rows += clif_rows(oid, ab)
        for k in range(1, 7):
            if f"organism_id{k}" in bal.columns:
                bal[f"organism_id{k}"] = bal[f"organism_id{k}"].astype("object")
        bal.to_csv(bal_path, index=False)
        print(f"  linked BAL organisms in {Path(bal_path).name}")

    cols = ["organism_id", "antimicrobial_name", "antimicrobial_category", "sensitivity_name", "susceptibility_name", "susceptibility_category"]
    df = pd.DataFrame(rows, columns=cols)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print(f"Wrote {len(df)} SYNTHETIC susceptibility rows for {df['organism_id'].nunique()} organisms -> {a.out}")


if __name__ == "__main__":
    main()
