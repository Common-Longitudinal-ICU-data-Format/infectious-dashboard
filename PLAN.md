# CLIF Infection Timeline Dashboard: Planning Document

Status: v1 BUILT. Export pipeline verified against the MIMIC demo; React UI type-checked but not yet viewed in a browser (see section 11)

## 1. Goal
A local, polished dashboard that shows a single patient's ICU course as a stack of time-aligned lanes, so a clinician can see how infection, organ support and inflammatory markers relate. Built on CLIF data and the official `clifpy` package.

## 2. Decisions so far
| Topic | Decision |
|---|---|
| First dataset | Public MIMIC-IV demo in CLIF format (user will upload) |
| Architecture | Precompute to JSON: a Python export step, then a static React app |
| v1 extras | Other infectious labs; cohort filters |
| Look and feel | Clean clinical light theme |
| Data path | `config.yaml` entry pointing at a local CLIF folder |
| X-axis | Starts at hospital admission; tick labels show clock time |
| Temperature / WBC bands | Standard SIRS (temp >38.0 or <36.0 C; WBC >12 or <4 x10^3/uL) |
| Multiple ICU stays | One continuous hospitalization timeline; each ICU stay drawn as a bar from ICU arrival to departure |
| PHI display | No special rules |
| Antibiotics | Added to v1: a lane from `medication_admin_intermittent`, one bar/marker row per agent |
| Dataset | Public MIMIC demo in CLIF 2.1.0 (uploaded; points `clif_data_dir` there for now) |

## 3. Architecture
```
config.yaml ──► export/ (Python + clifpy) ──► public/data/
                                                 ├─ index.json            (one row per hospitalization, for filters)
                                                 └─ patients/<hosp_id>.json  (full timeline per patient)
                                                         │
                                          React + Vite + TypeScript app (static, local)
```
- `make export` reads `config.yaml`, loads and validates the CLIF tables with clifpy, and writes the JSON.
- `make dev` serves the React app. `make build` produces a static bundle.
- No server and no network calls at runtime. Data never leaves the machine.

## 4. Config (`config.yaml`)
```yaml
clif_data_dir: /path/to/clif/files   # folder containing clif_<table>.parquet (or .csv)
filetype: parquet                    # parquet | csv
timezone: America/Chicago            # display timezone; CLIF stores UTC
output_dir: app/public/data
tables:                              # optional overrides
  microbiology_culture: clif_microbiology_culture.parquet
icu_only: true                       # clip timelines to ICU location_category windows
max_patients: null                   # set a number for quick test exports
```
The export fails fast with a readable message if the path is missing or a required table is absent. Optional tables (microbiology, intermittent meds) degrade gracefully.

## 5. Timeline lanes
All lanes share one x-axis (hours since ICU admit, with a toggle for clock time) and a synced hover cursor.

| # | Lane | Source tables | Rendering |
|---|---|---|---|
| 1 | Location / ICU stays | `adt` | Continuous timeline with ICU stays as bars (arrive/leave); ward time shown as muted band |
| 2 | Respiratory support | `respiratory_support` | Device bands (IMV, NIV, HFNC, NC, room air), with FiO2 and PEEP sparklines |
| 3 | Vasopressors | `medication_admin_continuous` | Dose line per agent, plus norepinephrine-equivalent total |
| 4 | Microbiology | `microbiology_culture` (+ susceptibility, non-culture if present) | Markers at collection time with detail popover: site, organism, result |
| 5 | Antibiotics | `medication_admin_intermittent` | One row per agent, dose markers at administration time, with drug and dose in tooltip |
| 6 | Temperature | `vitals` | Line with fever and hypothermia threshold bands |
| 7 | WBC | `labs` | Points and line with threshold bands |
| 8 | Other infectious labs (v1) | `labs` | Lactate, procalcitonin, CRP, creatinine as small multiples or a selectable lane |

Candidate later additions: SOFA overlay, ASE-style infection event flags.

## 6. Cohort filters (v1)
Driven by `index.json`, computed at export time:
- Has a positive culture, by site and by organism
- Ever on IMV, NIV or HFNC
- Ever on vasopressors
- ICU length of stay range
- Age range and in-hospital mortality
Patient list is searchable and sortable. Selecting a row opens its timeline.

## 7. Reusing existing CLIF code
Read for definitions before implementing, and reuse via clifpy where possible:
- `clifpy`: table loading, validation, unit conversion helpers, wide/hourly format
- `CLIF-epi-of-vaso`, `021_vasoactive-epi`: vasopressor handling and dose-equivalent logic
- `ASE_revised_thresholds_wbc_temp`: WBC and temperature thresholds for the threshold bands
- `CLIF-Project-Template`: config and project structure conventions

## 8. Risks and open issues
1. **Microbiology and intermittent meds are present** in the uploaded demo (`clif_microbiology_culture.parquet`, `clif_medication_admin_intermittent.parquet`), so both lanes can be built on real data. Column names and category values still need confirming against the files. Lanes still show an empty state if a table is absent on other sites' data.
2. **Vasopressor units** vary (mcg/kg/min, mcg/min, units/min). Dose normalization needs care and the tooltip should show original units.
3. **Respiratory device ordering and gaps**: need rules for turning point-in-time rows into continuous bands (carry-forward limit).
4. **CLIF version drift** (2.0 to 2.2): the export should read the version-specific column names through clifpy rather than hard-coding them.
5. **Timezones**: all CLIF datetimes are UTC; display conversion is done in the app.

## 9. Milestones
1. Scaffold repo, `config.yaml` loader and validation, synthetic fixture
2. Export pipeline: index.json plus per-patient JSON for lanes 1 to 6
3. React shell: patient list, cohort filters, theme
4. Timeline component with shared axis and synced cursor
5. Lane polish, tooltips, microbiology detail popover, other labs lane
6. Test against MIMIC demo files, fix mapping issues
7. README with setup and config instructions

## 10. Resolved questions
Chart library (ECharts by default), x-axis, SIRS bands, ICU stay display and PHI rules are settled; see section 2.

## 11. Build status
* **Export pipeline** (`export/export.py`): done and verified against the raw CSVs (dose, culture, lab, vitals and cohort counts match; unit conversion and NE-equivalent checked by hand; bad-config errors tested).
* **React app**: written and type-checked; the chart builder runs against all 133 exported patients. It has **not been rendered in a browser** because this build session could not install npm packages. First `npm install && npm run dev` is the real visual test.
* **Parquet input**: implemented but not run here (pyarrow could not be installed); the demo was exercised via CSV.
* Findings from the data: microbiology and intermittent medication tables are present; no susceptibility table; temperature has implausible values (dropped, range 30-45 C); 133 of 310 hospitalizations have an ICU stay, 33 of them with more than one.

## 12. Earlier open questions (resolved)
- Chart library preference? Default proposal is Apache ECharts (good multi-lane zoom and sync). Plotly or visx are alternatives.
- Should the x-axis default to hours from ICU admission or to clock time?
- Which temperature and WBC thresholds should the bands use (ASE-revised values vs. standard SIRS)?
- Should an ICU stay with multiple ICU episodes be shown as one continuous timeline or separately?
- Any de-identification or PHI display rules to respect (e.g. hide dates, show relative time only)?
