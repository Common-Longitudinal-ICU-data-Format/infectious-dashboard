# ICU infection timeline (CLIF)

A local dashboard that lays one hospitalization's ICU course out as stacked, time-aligned lanes so you can
see how infection, organ support and inflammatory markers relate:

| Lane | CLIF table | Notes |
|---|---|---|
| ICU stays & hospital location | `adt` | ICU arrivals/departures drawn as bars; ICU time is also tinted across every lane |
| Respiratory support | `respiratory_support` | Device bands (invasive vent, BiPAP, CPAP, high-flow, mask, nasal cannula), darker = more support |
| FiO₂, PEEP | `respiratory_support` | Separate lanes (one axis per lane) |
| Vasopressors | `medication_admin_continuous` | Per-agent step lines plus a norepinephrine-equivalent total; tooltip shows raw dose and units |
| Microbiology | `microbiology_culture` | Marker at collection time, line to result time; red = organism isolated; organism names on the marker |
| Antimicrobials | `medication_admin_intermittent` | One row per agent; diamond = dose given, band = course (doses ≤ 36 h apart); coloured by antibacterial / antifungal / antiviral |
| Temperature | `vitals` | SIRS bands (> 38 or < 36 °C); implausible values dropped |
| WBC | `labs` | SIRS bands (> 12 or < 4 ×10³/µL) |
| Other labs | `labs` | Pick lactate, CRP, creatinine, neutrophils, platelets, procalcitonin |

The x-axis starts at hospital admission and shows clock time; hover shows hours since admission.
Cohort filters (positive culture, blood culture, ventilated, NIV/high-flow, pressors, antimicrobials, fever, died,
organism, ICU time) are in the left panel.

## Quick start

```bash
make setup                 # pip + npm dependencies (once)
# put your CLIF folder in config.yaml (clif_data_dir, filetype)
make export                # reads CLIF files, writes dashboard JSON
make dev                   # http://localhost:5173
```

`app/public/data` already contains an export of the public MIMIC demo, so `cd app && npm install && npm run dev`
shows something immediately, before you run the exporter yourself.

## Pointing at your data (`config.yaml`)

```yaml
clif_data_dir: ./data/mimic-clif-demo   # folder with clif_<table>.parquet / .csv
filetype: parquet                       # parquet | csv
timezone: UTC                           # display time zone (CLIF stores UTC)
icu_only: true                          # only hospitalizations with an ICU ADT row
max_patients: null                      # e.g. 25 for a quick trial
axis_start: admission                   # or first_contact (ED arrival)
tables: {}                              # per-table file name overrides
```

Required tables: `patient`, `hospitalization`, `adt`. Every other table is optional: if it is missing its lane shows
"nothing recorded" and the export still succeeds. All data stay on your machine; the page makes no network calls.

## Definitions (change them in `config.yaml` / `export/export.py`)

* **ICU stay**: consecutive ICU `adt` rows within `icu_merge_gap_hours` (6 h) are one stay.
* **Respiratory bands**: device carried forward until the next device record; a gap longer than
  `resp_carry_forward_hours` (12 h) closes the band.
* **Norepinephrine-equivalent** (mcg/kg/min): norepinephrine + epinephrine + phenylephrine ÷ 10 + dopamine ÷ 100 +
  vasopressin (units/min) × 2.5. Dobutamine and milrinone are inotropes and are not included. Doses given
  in units the exporter can't convert (for example mcg/min with no weight) are skipped.
* **Positive culture**: an organism is reported and the result is not "CANCELLED". The demo data has no
  susceptibility table, so no resistance information is shown.
* **Antimicrobials**: `med_group == CMS_sepsis_qualifying_antibiotics`, plus a list of anti-infective
  `med_category` values (includes antifungals and acyclovir).

## Tests

```bash
make test
```
* `export/test_export.py` recomputes counts (doses, cultures, temperatures, WBC, pressor and vent
  hospitalizations) from the raw CLIF files, checks unit conversion and the NE-equivalent maths against a hand
  calculation, and checks that bad configs fail with a clear message.
* `app/tests/option.test.ts` builds the chart for every exported patient and checks lane layout and tooltips.

## Layout

```
config.yaml            where your CLIF data lives
export/export.py       CLIF tables -> app/public/data/{index.json,patients/*.json}
app/src/lib/timeline.ts  builds the stacked-lane chart (pure TypeScript, unit tested)
app/src/App.tsx, components/   React UI (cohort list, filters, header, chart)
```

Built with React, Vite, TypeScript and Apache ECharts.

## BAL results (optional)
Set `bal_file` in `config.yaml` to a wide table with one row per lavage (columns in `export/bal_schema.csv`).
The public MIMIC demo has none, so `python3 export/make_synthetic_bal.py` writes SYNTHETIC examples to
`data/synthetic/bal_synthetic.csv`. The exporter adds a `bal` block to each patient JSON; the artifact page shows a
BAL lane and a results box (cells + differential, Gram stain, culture, molecular panel, resistance genes,
galactomannan / PJP DFA). The React app does not render BAL yet.

## Susceptibilities (CLIF microbiology_susceptibility)
The exporter reads the CLIF 2.1 `microbiology_susceptibility` table from `clif_data_dir`
(`clif_microbiology_susceptibility.<ext>`) when it exists, or from `susceptibility_file` if set. It uses these columns:
`organism_id, antimicrobial_name, antimicrobial_category, sensitivity_name, susceptibility_name, susceptibility_category`,
where `susceptibility_category` is susceptible | non_susceptible | indeterminate | NA. `organism_id` links each row to
`microbiology_culture.organism_id` and to BAL `organism_id1..6`. Clicking a positive culture dot or a BAL organism
opens the antibiogram panel, which shows the category, the raw `susceptibility_name` and the `sensitivity_name` value.
The public demo has no such table, so the shipped config points at SYNTHETIC data: run `make_synthetic_bal.py`, then
`make_synthetic_susceptibility.py`. For real data, remove `susceptibility_file` / `susceptibility_synthetic` from the config.
