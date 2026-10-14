import type { IndexRow } from '../types';
import { applyFilters, activeFilterCount, DEFAULT_FILTERS, type Filters, type SortKey } from '../lib/filters';
import { useMemo } from 'react';

interface Props {
  rows: IndexRow[];
  filters: Filters;
  setFilters: (f: Filters) => void;
  selected: string | null;
  onSelect: (id: string) => void;
}

const TOGGLES: { key: keyof Filters; label: string; hint: string }[] = [
  { key: 'positive', label: 'Positive culture', hint: 'Any culture with an organism reported' },
  { key: 'blood', label: 'Positive blood culture', hint: 'Organism reported from a blood specimen' },
  { key: 'imv', label: 'Ventilated', hint: 'Invasive mechanical ventilation at any time' },
  { key: 'niv', label: 'NIV / high-flow', hint: 'BiPAP, CPAP or high-flow nasal cannula' },
  { key: 'pressor', label: 'Vasopressors', hint: 'Any vasopressor infusion' },
  { key: 'abx', label: 'Antimicrobials', hint: 'At least one antibiotic/antifungal/antiviral dose' },
  { key: 'fever', label: 'Fever > 38 °C', hint: 'Any temperature above the SIRS threshold' },
  { key: 'died', label: 'Died in hospital', hint: 'Discharge disposition is Expired' },
];

export default function Sidebar({ rows, filters, setFilters, selected, onSelect }: Props) {
  const shown = useMemo(() => applyFilters(rows, filters), [rows, filters]);
  const organisms = useMemo(() => {
    const m = new Map<string, number>();
    rows.forEach((r) => r.organisms.forEach((o) => m.set(o, (m.get(o) ?? 0) + 1)));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters({ ...filters, [k]: v });
  const n = activeFilterCount(filters);

  return (
    <aside className="sidebar" aria-label="Cohort">
      <div className="side-head">
        <h2>Cohort</h2>
        <span className="count"><b>{shown.length}</b> of {rows.length} ICU hospitalizations</span>
      </div>

      <div className="filters">
        <input
          className="search" type="search" placeholder="Search hospitalization or patient ID"
          value={filters.q} onChange={(e) => set('q', e.target.value)} aria-label="Search by ID"
        />
        <div className="chips" role="group" aria-label="Filters">
          {TOGGLES.map((t) => (
            <button
              key={t.key} type="button" title={t.hint}
              className={'chip' + (filters[t.key] ? ' on' : '')} aria-pressed={!!filters[t.key]}
              onClick={() => set(t.key, !filters[t.key] as never)}
            >{t.label}</button>
          ))}
        </div>
        <div className="selects">
          <label>Organism
            <select value={filters.organism} onChange={(e) => set('organism', e.target.value)}>
              <option value="">Any</option>
              {organisms.map(([o, c]) => <option key={o} value={o}>{o.toLowerCase()} ({c})</option>)}
            </select>
          </label>
          <label>ICU time
            <select value={filters.minIcuHours} onChange={(e) => set('minIcuHours', Number(e.target.value))}>
              <option value={0}>Any</option><option value={24}>≥ 24 h</option><option value={48}>≥ 48 h</option>
              <option value={96}>≥ 4 days</option><option value={168}>≥ 7 days</option>
            </select>
          </label>
          <label>Sort by
            <select value={filters.sort} onChange={(e) => set('sort', e.target.value as SortKey)}>
              <option value="icu_hours">ICU time</option><option value="los">Hospital stay</option>
              <option value="cultures">Cultures</option><option value="age">Age</option><option value="id">ID</option>
            </select>
          </label>
        </div>
        {n > 0 && <button type="button" className="link" onClick={() => setFilters({ ...DEFAULT_FILTERS, sort: filters.sort })}>Clear {n} filter{n > 1 ? 's' : ''}</button>}
      </div>

      <ul className="plist">
        {shown.map((r) => (
          <li key={r.id}>
            <button type="button" className={'prow' + (r.id === selected ? ' sel' : '')} onClick={() => onSelect(r.id)} aria-current={r.id === selected}>
              <span className="prow-top">
                <span className="pid">{r.id}</span>
                <span className="tags">
                  {r.imv && <i className="tag t-imv" title="Ventilated">Vent</i>}
                  {r.pressor && <i className="tag t-pressor" title="Vasopressors">Press</i>}
                  {r.positive_culture && <i className="tag t-cx" title={r.organisms.join(', ').toLowerCase()}>Cx+</i>}
                  {r.died && <i className="tag t-died" title="Died in hospital">†</i>}
                </span>
              </span>
              <span className="prow-sub">
                {r.age ?? '?'} {r.sex?.[0] ?? ''} · ICU {r.icu_hours != null ? (r.icu_hours >= 48 ? `${(r.icu_hours / 24).toFixed(1)} d` : `${Math.round(r.icu_hours)} h`) : '—'}
                {r.n_icu_stays > 1 ? ` (${r.n_icu_stays} stays)` : ''} · stay {r.los_days ?? '—'} d
              </span>
            </button>
          </li>
        ))}
        {!shown.length && <li className="none">No hospitalizations match these filters.</li>}
      </ul>
    </aside>
  );
}
