import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { IndexFile, IndexRow, Patient } from './types';
import { DEFAULT_FILTERS, applyFilters, type Filters } from './lib/filters';
import { icuWindow } from './lib/timeline';

/** Long hospitalizations (> 21 d) open on the ICU window; others on the full stay. */
function openWindow(p: Patient): { start: number; end: number } {
  if (p.axis.end - p.axis.start > 21 * 86_400_000 && p.icu_stays.length) {
    const [start, end] = icuWindow(p);
    return { start, end };
  }
  return { start: p.axis.start, end: p.axis.end };
}
import { LAB_LABEL } from './lib/theme';
import Sidebar from './components/Sidebar';
import PatientHeader from './components/PatientHeader';
import TimelineChart, { type ChartHandle, type ViewRequest } from './components/TimelineChart';

const base = import.meta.env.BASE_URL;
const cache = new Map<string, Patient>();

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${base}data/${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export default function App() {
  const [index, setIndex] = useState<IndexFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState<string | null>(() => window.location.hash.replace('#/', '') || null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(false);
  const [labKey, setLabKey] = useState('lactate');
  const [view, setView] = useState<ViewRequest>({ start: 0, end: 1, nonce: 0 });
  const handle = useRef<ChartHandle | null>(null);

  useEffect(() => {
    getJson<IndexFile>('index.json').then(setIndex).catch((e) => setError(String(e.message ?? e)));
  }, []);

  const rows = index?.hospitalizations ?? [];
  const visible = useMemo(() => applyFilters(rows, filters), [rows, filters]);

  // Select the first matching patient once the cohort is known.
  useEffect(() => {
    if (!index) return;
    if (!selected || !rows.some((r) => r.id === selected)) setSelected(visible[0]?.id ?? rows[0]?.id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  useEffect(() => {
    if (!selected) return;
    window.location.hash = `#/${selected}`;
    const hit = cache.get(selected);
    if (hit) { setPatient(hit); setView({ ...openWindow(hit), nonce: Date.now() }); return; }
    let live = true;
    setLoading(true);
    getJson<Patient>(`patients/${selected}.json`)
      .then((p) => {
        if (!live) return;
        cache.set(selected, p);
        setPatient(p);
        setView({ ...openWindow(p), nonce: Date.now() });
      })
      .catch((e) => live && setError(String(e.message ?? e)))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [selected]);

  const onReady = useCallback((h: ChartHandle) => { handle.current = h; }, []);
  const go = (start: number, end: number) => setView({ start, end, nonce: Date.now() });
  const row: IndexRow | undefined = rows.find((r) => r.id === selected);

  if (error) {
    return (
      <div className="state">
        <h1>Couldn’t load the timeline data</h1>
        <p><code>{error}</code></p>
        <p>Run the exporter first, from the project folder:</p>
        <pre>make export</pre>
        <p>It reads the CLIF files named in <code>config.yaml</code> and writes the JSON this page loads.</p>
      </div>
    );
  }
  if (!index) return <div className="state"><p>Loading cohort…</p></div>;

  const labs = index.meta.extra_labs;

  return (
    <div className="app">
      <header className="top">
        <div className="brand"><span className="mark" aria-hidden="true" />ICU infection timeline</div>
        <div className="src" title={index.meta.source}>
          {index.meta.n} ICU hospitalizations · CLIF {index.meta.filetype} · times in {index.meta.timezone}
        </div>
      </header>
      <div className="body">
        <Sidebar rows={rows} filters={filters} setFilters={setFilters} selected={selected} onSelect={setSelected} />
        <main className="main">
          {patient && row ? (
            <>
              <PatientHeader row={row} patient={patient} sirs={index.meta.sirs} tz={index.meta.timezone} />
              <div className="toolbar">
                <div className="seg" role="group" aria-label="Time window">
                  <button type="button" onClick={() => go(patient.axis.start, patient.axis.end)}>Full stay</button>
                  <button type="button" onClick={() => { const [a, b] = icuWindow(patient); go(a, b); }} disabled={!patient.icu_stays.length}>ICU stays</button>
                  <button type="button" onClick={() => go(patient.axis.start, Math.min(patient.axis.end, patient.axis.start + 48 * 3_600_000))}>First 48 h</button>
                </div>
                <div className="seg" role="group" aria-label="Zoom">
                  <button type="button" onClick={() => handle.current?.zoomBy(0.5)} aria-label="Zoom in">＋</button>
                  <button type="button" onClick={() => handle.current?.zoomBy(2)} aria-label="Zoom out">－</button>
                </div>
                <label className="lab-pick">Other labs lane
                  <select value={labKey} onChange={(e) => setLabKey(e.target.value)}>
                    {labs.map((k) => <option key={k} value={k}>{LAB_LABEL[k] ?? k}{patient.labs[k] ? '' : ' (none)'}</option>)}
                  </select>
                </label>
                <span className="spacer" />
                <span className="hint">Ctrl + scroll to zoom · drag to pan · hover for details</span>
                <button type="button" className="ghost" onClick={() => handle.current?.savePng()}>Save image</button>
              </div>
              <div className="chart-card">
                {loading && <div className="loading">Loading…</div>}
                <TimelineChart patient={patient} sirs={index.meta.sirs} tz={index.meta.timezone} labKey={labKey} view={view} onReady={onReady} />
              </div>
              <p className="foot">
                Shaded blue columns are ICU stays. Temperature and WBC bands use SIRS thresholds
                (temp &gt; {index.meta.sirs.temp_high_c} or &lt; {index.meta.sirs.temp_low_c} °C; WBC &gt; {index.meta.sirs.wbc_high} or &lt; {index.meta.sirs.wbc_low} ×10³/µL).
                Vasopressor total is norepinephrine-equivalent: norepinephrine + epinephrine + phenylephrine ÷ 10 + dopamine ÷ 100 + vasopressin (units/min) × 2.5.
                {index.meta.temp_values_dropped > 0 && ` ${index.meta.temp_values_dropped} implausible temperature values were excluded.`}
              </p>
            </>
          ) : (
            <div className="state"><p>{loading ? 'Loading…' : 'Select a hospitalization from the cohort.'}</p></div>
          )}
          <p className="credit">2026 Cathy Gao-Howard on behalf of the CLIF Consortium</p>
        </main>
      </div>
    </div>
  );
}
