#!/usr/bin/env python3
"""Generate SYNTHETIC bronchoalveolar lavage (BAL) rows that follow export/bal_schema.csv.

The public MIMIC demo has no BAL data, so this fabricates plausible example rows for
ventilated hospitalizations, purely so the dashboard's BAL lane and results box can be
previewed. Nothing here is real patient data. Output is flagged with synthetic=True.

    python3 -I export/make_synthetic_bal.py --config config.yaml [--out data/synthetic/bal_synthetic.csv]
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export import load_config, load_table, to_ms  # noqa: E402

HERE = Path(__file__).resolve().parent
SEED = 20260613

BACT = ["acinetobacter calcoaceticus-baumannii complex", "enterobacter cloacae complex", "escherichia coli", "haemophilus influenzae",
        "klebsiella aerogenes", "klebsiella oxytoca", "klebsiella pneumoniae group", "moraxella catarrhalis", "proteus spp",
        "pseudomonas aeruginosa", "serratia marcescens", "staphylococcus aureus", "streptococcus agalactiae",
        "streptococcus pneumoniae", "streptococcus pyogenes"]
ATYP = ["chlamydia_pneumoniae_lower_resp", "legionella pneumophila", "mycoplasma_pneumoniae_lower_resp"]
VIRAL = ["adenovirus_lower_resp", "coronavirus", "human_metapneumovirus_lower_resp", "human_rhinovirus_enterovirus_lower_resp",
         "influenza a", "influenza b", "parainfluenza virus", "respiratory syncytial virus", "covid_19"]
GENES = ["ctx-m", "imp", "kpc", "meca/c and mrej", "ndm", "oxa-48-like", "vim"]

QTY_HEAVY = [">100,000 CFU/mL", "Heavy growth", ">=10^5 CFU/mL"]


def mrn(i):  # obviously fake
    return f"SYN{i:05d}"


# ---------------------------------------------------------------- archetypes ----
def diff(r, neutro, macro, lympho, eos=(0, 2), plasma=(0, 1)):
    n, m, l, e, p = (r.uniform(*neutro), r.uniform(*macro), r.uniform(*lympho), r.uniform(*eos), r.uniform(*plasma))
    mono = r.uniform(0, 3)
    other = max(0.0, 100 - (n + m + l + e + p + mono))
    tot = n + m + l + e + p + mono + other
    f = 100 / tot
    return dict(bal_pct_neutro=round(n * f, 0), bal_pct_macro=round(m * f, 0), bal_pct_lympho=round(l * f, 0), bal_pct_eos=round(e * f, 0),
                bal_pct_plasma=round(p * f, 0), bal_pct_mono=round(mono * f, 0), bal_pct_other=round(other * f, 0))


def cells(r, wbc, **d):
    w = r.uniform(*wbc)
    out = dict(bal_wbc_count=round(w, 0), bal_rbc_count=round(r.uniform(20, 2500), 0), **d)
    out["abs_neutrophils"] = round(w * d["bal_pct_neutro"] / 100, 0)
    out["abs_lymphocytes"] = round(w * d["bal_pct_lympho"] / 100, 0)
    out["abs_eosinophils"] = round(w * d["bal_pct_eos"] / 100, 0)
    return out


def panel(r, hits=(), genes=(), tested=True):
    """Return panel columns; hits = list of (column, text)."""
    if not tested:
        return {}
    d = {c: "Not Detected" for c in BACT + ATYP + VIRAL + GENES}
    for c, v in hits:
        d[c] = v
    for g in genes:
        d[g] = "Detected"
    return d


def copies(r):
    return f"Detected (10^{r.choice([5, 6, 6, 7])} copies/mL)"


def bact_case(r, org_col, org_name, gram, genes=(), second=None, tested=True, qty=None):
    d = cells(r, (700, 5200), **diff(r, (68, 92), (4, 20), (1, 8)))
    d.update(gram_stain_report_organisms=gram, gram_stain_report_wbc=r.choice(["Many", "Moderate", "Many"]), gram_stain_report_rbc="Few",
             gram_stain_report_stain="Gram", organism_1_name=org_name, organism_1_quantity=qty or r.choice(QTY_HEAVY), negative_for_growth="No",
             pathogen_bacteria=True, pathogen_result=f"Detected: {org_name.title()}")
    hits = [(org_col, copies(r))] if org_col else []
    if second:
        d.update(organism_2_name=second[1], organism_2_quantity=second[2]); hits.append((second[0], copies(r)))
        d["pathogen_result"] += f"; {second[1].title()}"
    d.update(panel(r, hits, genes, tested))
    if genes:
        d["pathogen_resistance"] = True
        d["pathogen_comments"] = "Resistance determinant detected: " + ", ".join(genes)
    if org_col == "staphylococcus aureus" and not tested:
        d["respiratory_mrsa_pcr"] = "Positive" if genes else "Negative"
    return d


def a_mssa_mrsa(r):
    mrsa = r.random() < 0.45
    d = bact_case(r, "staphylococcus aureus", "STAPHYLOCOCCUS AUREUS" + (" (MRSA)" if mrsa else " (MSSA)"), "Gram positive cocci in clusters",
                  ["meca/c and mrej"] if mrsa else [], tested=r.random() < 0.75)
    return d


def a_pseudo(r):
    return bact_case(r, "pseudomonas aeruginosa", "PSEUDOMONAS AERUGINOSA", "Gram negative rods", [], tested=r.random() < 0.7)


def a_entero(r):
    col, nm = r.choice([("klebsiella pneumoniae group", "KLEBSIELLA PNEUMONIAE"), ("escherichia coli", "ESCHERICHIA COLI"),
                        ("enterobacter cloacae complex", "ENTEROBACTER CLOACAE COMPLEX"), ("serratia marcescens", "SERRATIA MARCESCENS")])
    genes = []
    x = r.random()
    if x < 0.3:
        genes = ["ctx-m"]
    elif x < 0.38:
        genes = ["kpc"]
    return bact_case(r, col, nm, "Gram negative rods", genes, tested=r.random() < 0.7)


def a_community(r):
    col, nm, gram = r.choice([("haemophilus influenzae", "HAEMOPHILUS INFLUENZAE", "Gram negative coccobacilli"),
                              ("streptococcus pneumoniae", "STREPTOCOCCUS PNEUMONIAE", "Gram positive diplococci"),
                              ("moraxella catarrhalis", "MORAXELLA CATARRHALIS", "Gram negative diplococci")])
    return bact_case(r, col, nm, gram, [], tested=r.random() < 0.8, qty=r.choice(["10,000-100,000 CFU/mL", ">100,000 CFU/mL", "Moderate growth"]))


def a_viral(r, virus=None):
    col, label = virus or r.choice([("covid_19", "SARS-CoV-2"), ("influenza a", "Influenza A"), ("respiratory syncytial virus", "RSV"),
                                    ("human_rhinovirus_enterovirus_lower_resp", "Rhinovirus/Enterovirus"), ("human_metapneumovirus_lower_resp", "hMPV"),
                                    ("parainfluenza virus", "Parainfluenza")])
    d = cells(r, (150, 1800), **diff(r, (18, 50), (25, 55), (12, 40)))
    d.update(gram_stain_report_organisms="No organisms seen", gram_stain_report_wbc="Few", gram_stain_report_rbc="Few", gram_stain_report_stain="Gram",
             negative_for_growth="Yes", pathogen_virus=True, pathogen_result=f"Detected: {label}")
    d.update(panel(r, [(col, "Detected")], [], True))
    return d, col, label


def a_viral_bact(r):
    d, col, label = a_viral(r)
    org = r.choice([("staphylococcus aureus", "STAPHYLOCOCCUS AUREUS"), ("streptococcus pneumoniae", "STREPTOCOCCUS PNEUMONIAE"), ("haemophilus influenzae", "HAEMOPHILUS INFLUENZAE")])
    d.update(cells(r, (900, 4000), **diff(r, (55, 80), (8, 25), (3, 12))))
    d.update(organism_1_name=org[1], organism_1_quantity=">100,000 CFU/mL", negative_for_growth="No", pathogen_bacteria=True,
             gram_stain_report_organisms="Gram positive cocci" if org[0] != "haemophilus influenzae" else "Gram negative coccobacilli", gram_stain_report_wbc="Many")
    d["pathogen_result"] += f"; {org[1].title()}"
    d[org[0]] = copies(r)
    return d


def a_aspergillus(r):
    d = cells(r, (300, 2600), **diff(r, (35, 70), (10, 35), (3, 12)))
    gm = round(r.uniform(1.1, 5.2), 2)
    d.update(gram_stain_report_organisms="No bacteria seen", gram_stain_report_wbc="Moderate", gram_stain_report_rbc="Moderate", gram_stain_report_stain="Gram",
             negative_for_growth="Yes (bacterial)", pathogen_fungi=True, pathogen_aspergillus=True, pathogen_galactomannan=gm,
             pathogen_result="Detected: Aspergillus (galactomannan positive)",
             culture_fungal_w_smear_bal_organism_id_1=r.choice(["ASPERGILLUS FUMIGATUS", "ASPERGILLUS FLAVUS", "ASPERGILLUS SPECIES"]),
             fungal_culture_stain_report_1="Septate hyphae seen on calcofluor/KOH smear")
    d["aspergillus galactomannan antigen(nmh/lfh)"] = f"Positive (index {gm})"
    d.update(panel(r, [], [], True))
    d["pathogen_comments"] = "Consider invasive pulmonary aspergillosis; correlate with imaging and serum galactomannan."
    return d


def a_pjp(r):
    d = cells(r, (250, 2200), **diff(r, (10, 35), (20, 45), (18, 42)))
    d.update(gram_stain_report_organisms="No organisms seen", gram_stain_report_wbc="Few", gram_stain_report_rbc="Few", gram_stain_report_stain="Gram",
             negative_for_growth="Yes", pathogen_fungi=True, pathogen_result="Detected: Pneumocystis jirovecii",
             fungal_culture_stain_report_1="Cysts consistent with Pneumocystis seen on silver stain")
    d["pneumocystis jirovecii(carinii), dfa (nmh/lfh)"] = "Positive"
    d.update(panel(r, [], [], True))
    d["pathogen_comments"] = "Pneumocystis DFA positive."
    return d


def a_negative(r):
    d = cells(r, (40, 480), **diff(r, (4, 28), (55, 88), (3, 14)))
    flora = r.random() < 0.45
    d.update(gram_stain_report_organisms="No organisms seen" if not flora else "Mixed oropharyngeal flora", gram_stain_report_wbc=r.choice(["Rare", "Few"]),
             gram_stain_report_rbc="Few", gram_stain_report_stain="Gram", negative_for_growth="Yes",
             pathogen_result="Not detected")
    if flora:
        d.update(organism_1_name="NORMAL RESPIRATORY FLORA", organism_1_quantity="Light growth", negative_for_growth="Yes (normal flora only)")
    d.update(panel(r, [], [], r.random() < 0.6))
    return d


def a_eos(r):
    d = cells(r, (400, 2400), **diff(r, (8, 22), (25, 45), (6, 18), eos=(18, 40)))
    d.update(gram_stain_report_organisms="No organisms seen", gram_stain_report_wbc="Moderate", gram_stain_report_rbc="Few", gram_stain_report_stain="Gram",
             negative_for_growth="Yes", pathogen_result="Not detected", pathogen_comments="Eosinophil-predominant differential (>= 15%).")
    d.update(panel(r, [], [], r.random() < 0.5))
    return d


def a_candida(r):
    d = cells(r, (120, 900), **diff(r, (15, 40), (45, 75), (5, 15)))
    d.update(gram_stain_report_organisms="Yeast seen", gram_stain_report_wbc="Few", gram_stain_report_rbc="Few", gram_stain_report_stain="Gram",
             organism_1_name="YEAST (CANDIDA SPECIES)", organism_1_quantity="Light growth", negative_for_growth="No",
             pathogen_result="Not detected", pathogen_comments="Yeast in light quantity; probable colonization.")
    d.update(panel(r, [], [], r.random() < 0.5))
    return d


ARCHETYPES = [("mssa_mrsa", a_mssa_mrsa, 5), ("pseudomonas", a_pseudo, 4), ("enterobacterales", a_entero, 4), ("community_bacterial", a_community, 2),
              ("viral", lambda r: a_viral(r)[0], 4), ("viral_bacterial", a_viral_bact, 3), ("aspergillus", a_aspergillus, 2), ("pjp", a_pjp, 2),
              ("negative", a_negative, 8), ("eosinophilic", a_eos, 1), ("candida_colonization", a_candida, 2)]
FOLLOWUP = {"mssa_mrsa": ["negative", "mssa_mrsa", "candida_colonization"], "pseudomonas": ["negative", "pseudomonas", "enterobacterales"],
            "enterobacterales": ["negative", "pseudomonas"], "community_bacterial": ["negative"], "viral": ["viral_bacterial", "negative"],
            "viral_bacterial": ["negative"], "aspergillus": ["aspergillus", "negative"], "pjp": ["negative"], "negative": ["mssa_mrsa", "pseudomonas", "viral"],
            "eosinophilic": ["negative"], "candida_colonization": ["negative", "mssa_mrsa"]}
FUN = {k: f for k, f, _ in ARCHETYPES}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE.parent / "config.yaml"))
    ap.add_argument("--out", default=str(HERE.parent / "data" / "synthetic" / "bal_synthetic.csv"))
    ap.add_argument("--n", type=int, default=40, help="number of ventilated hospitalizations to give a BAL")
    a = ap.parse_args()
    cfg = load_config(Path(a.config).resolve())
    hosp, resp, adt = (load_table(cfg, n, True if n != "respiratory_support" else False) for n in ("hospitalization", "respiratory_support", "adt"))
    if resp is None:
        sys.exit("respiratory_support table is needed to place BALs on ventilated patients")
    icu = set(adt.loc[adt["location_category"] == "icu", "hospitalization_id"])
    resp = resp[resp["device_category"] == "IMV"].copy()
    resp["t"] = to_ms(resp["recorded_dttm"])
    g = resp.groupby("hospitalization_id")["t"].agg(["min", "max"])
    hosp = hosp[hosp["hospitalization_id"].isin(set(g.index) & icu)].copy()
    hosp["adm_ms"], hosp["dis_ms"] = to_ms(hosp["admission_dttm"]), to_ms(hosp["discharge_dttm"])

    r = random.Random(SEED)
    rows_in = hosp.sort_values("hospitalization_id").to_dict("records")
    r.shuffle(rows_in)
    pool = [k for k, _, w in ARCHETYPES for _ in range(w)]
    r.shuffle(pool)
    schema = pd.read_csv(HERE / "bal_schema.csv")["column"].tolist()
    out, n_acc = [], 0
    H = 3_600_000
    chosen = 0
    for h in rows_in:
        if chosen >= a.n:
            break
        hid = h["hospitalization_id"]
        t0, t1 = g.loc[hid, "min"], g.loc[hid, "max"]
        lo, hi = t0 + 8 * H, min(t1, h["dis_ms"]) - 1 * H
        if not (hi > lo):
            continue
        chosen += 1
        kind = pool[(chosen - 1) % len(pool)]
        kinds = [kind]
        if r.random() < 0.3 and hi - lo > 5 * 24 * H:
            kinds.append(r.choice(FOLLOWUP[kind]))
        times = sorted([r.uniform(lo, min(lo + 6 * 24 * H, hi))] + ([r.uniform(lo + 3.5 * 24 * H, hi)] if len(kinds) > 1 else []))
        if len(times) > 1 and times[1] - times[0] < 48 * H:
            times, kinds = times[:1], kinds[:1]
        for t, k in zip(times, kinds):
            n_acc += 1
            d = FUN[k](r)
            ra = random.Random(SEED * 1000 + n_acc)          # separate stream so other fields stay stable
            if d.get("pathogen_galactomannan") is None and ra.random() < 0.25:   # galactomannan sent on ~25% of other lavages, negative
                gm = round(ra.uniform(0.04, 0.42), 2)
                d["pathogen_galactomannan"] = gm
                d["aspergillus galactomannan antigen(nmh/lfh)"] = f"Negative (index {gm})"
            if k == "community_bacterial" or ra.random() < 0.4:   # urine antigens: always for community-type cases, else ~40%
                pneumo = "pneumoniae" in str(d.get("organism_1_name", "")).lower() or "pneumoniae" in str(d.get("pathogen_result", "")).lower() and "strepto" in str(d.get("pathogen_result", "")).lower()
                d["streptococcus pneumoniae antigen,urine 1"] = "Positive" if pneumo and ra.random() < 0.7 else "Negative"
                d["legionella antigen (eia) urine 1"] = "Positive" if (k == "community_bacterial" and ra.random() < 0.5) else "Negative"
            if ra.random() < 0.8:                              # amylase measured on ~80% of lavages (U/L)
                d["amylase"] = round(ra.uniform(300, 2400) if ra.random() < 0.12 else ra.uniform(6, 70), 0)
            t_ts = pd.to_datetime(int(t), unit="ms").round("min")
            adm = pd.to_datetime(int(h["adm_ms"]), unit="ms")
            intub = pd.to_datetime(int(t0), unit="ms")
            bronch = r.random() < 0.7
            row = {c: None for c in schema}
            row.update(patient_id=h["patient_id"], hospitalization_id=hid, mrn=mrn(int(str(h["patient_id"])[-5:])),
                       admission_dttm=adm, discharge_dttm=pd.to_datetime(int(h["dis_ms"]), unit="ms"),
                       hosp_admission_date=adm.date().isoformat(), hosp_discharge_date=pd.to_datetime(int(h["dis_ms"]), unit="ms").date().isoformat(),
                       first_intubation_date=intub.date().isoformat(),
                       day_of_intubation=int((t - t0) // (24 * H)) + 1, day_of_hospitalization=int((t - h["adm_ms"]) // (24 * H)) + 1,
                       bal_collection_dttm=t_ts, bal_collection_date=t_ts.date().isoformat(),
                       bal_test_type="BRONCHOALVEOLAR LAVAGE" + (" (MINI-BAL)" if not bronch else ""), bal_test_type_category="bal",
                       procedure_name="BRONCHOSCOPY WITH BRONCHOALVEOLAR LAVAGE" if bronch else "NON-BRONCHOSCOPIC BAL (MINI-BAL)",
                       order_accession_num=f"SYN-{n_acc:05d}", side=r.choice(["Right", "Left", "Right", "Not specified"]),
                       bal_type="Bronchoscopic" if bronch else "Mini-BAL", has_bal=True, synthetic=True)
            row.update({k2: v for k2, v in d.items()})
            out.append(row)
    df = pd.DataFrame(out, columns=schema + ["synthetic"])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print(f"Wrote {len(df)} SYNTHETIC BAL rows for {df['hospitalization_id'].nunique()} hospitalizations -> {a.out}")


if __name__ == "__main__":
    main()
