// Runs the option builder against every exported patient (no browser, no echarts needed).
//   node --experimental-strip-types tests/option.test.ts
import { readFileSync, readdirSync } from 'node:fs';
import { buildOption, icuWindow } from '../src/lib/timeline.ts';
import { fmtNum, shortOrganism, fmtOffset, fmtDuration, fmtTick, titleCase } from '../src/lib/format.ts';
import { applyFilters, DEFAULT_FILTERS } from '../src/lib/filters.ts';

const dir = new URL('../public/data/', import.meta.url).pathname;
const index = JSON.parse(readFileSync(dir + 'index.json', 'utf8'));
const sirs = index.meta.sirs;
const files = readdirSync(dir + 'patients');
let n = 0, series = 0, minH = 1e9, maxH = 0;
const fail = (m: string): never => { throw new Error(m); };
const eq = (a: unknown, b: unknown, what: string) => { if (a !== b) fail(`${what}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); };

// ---- formatter unit checks ----
eq(fmtNum(0.5, 2), '0.5', 'fmtNum 0.5'); eq(fmtNum(2, 2), '2', 'fmtNum 2'); eq(fmtNum(0.1701, 3), '0.17', 'fmtNum 0.1701');
eq(fmtNum(37.04, 1), '37.0', 'fmtNum 37.04'); eq(fmtNum(182.6, 1), '183', 'fmtNum 182.6');
eq(shortOrganism('ESCHERICHIA COLI'), 'E. coli', 'E. coli'); eq(shortOrganism('STAPH AUREUS COAG +'), 'S. aureus', 'S. aureus');
eq(shortOrganism('KLEBSIELLA PNEUMONIAE'), 'K. pneumoniae', 'Klebsiella'); eq(shortOrganism('YEAST'), 'Yeast', 'Yeast');
eq(shortOrganism('ENTEROCOCCUS SP.'), 'Enterococcus Sp.', 'Enterococcus sp');
eq(titleCase('PIPERACILLIN/TAZOBACTAM'), 'Piperacillin/Tazobactam', 'titleCase slash');
eq(fmtOffset(3_600_000 * 17.4, 0), '+17.4 h', 'offset h'); eq(fmtOffset(3_600_000 * 96, 0), '+4.0 d', 'offset d');
eq(fmtDuration(90 * 60_000), '1.5 h', 'duration'); eq(fmtTick(Date.UTC(2111, 10, 14, 0, 0), 'UTC'), 'Nov 14', 'tick midnight');
eq(fmtTick(Date.UTC(2111, 10, 14, 5, 20), 'UTC'), '05:20', 'tick hour');
// ---- filter checks ----
{
  const rows = index.hospitalizations;
  const pos = applyFilters(rows, { ...DEFAULT_FILTERS, positive: true });
  eq(pos.length, rows.filter((r: any) => r.positive_culture).length, 'filter positive');
  const both = applyFilters(rows, { ...DEFAULT_FILTERS, positive: true, imv: true, pressor: true });
  if (both.some((r: any) => !(r.positive_culture && r.imv && r.pressor))) fail('combined filter leaked rows');
  const sorted = applyFilters(rows, DEFAULT_FILTERS);
  for (let i = 1; i < sorted.length; i++) if ((sorted[i - 1].icu_hours ?? -1) < (sorted[i].icu_hours ?? -1)) fail('sort order wrong');
}

for (const f of files) {
  const p = JSON.parse(readFileSync(dir + 'patients/' + f, 'utf8'));
  for (const labKey of ['lactate', 'crp', 'creatinine', 'procalcitonin']) {
    const b = buildOption(p, { sirs, tz: index.meta.timezone, labKey });
    const o = b.option;
    const g = o.grid.length;
    if (o.xAxis.length !== g || o.yAxis.length !== g) fail(`${f}: axis/grid count mismatch`);
    for (const s of o.series) {
      if (s.xAxisIndex >= g || s.yAxisIndex >= g || s.xAxisIndex < 1) fail(`${f}: bad axis index on series ${s.name}`);
      series++;
      if (s.type === 'custom') for (const d of s.data) {
        const v = d.value;
        if (!(v[1] >= v[0])) fail(`${f}: bar ends before it starts in ${s.name}`);
        if (!Number.isFinite(v[2])) fail(`${f}: non-numeric row in ${s.name}`);
      }
    }
    // grids must not overlap and must fit in the canvas
    for (let i = 2; i < g; i++) if (o.grid[i].top < o.grid[i - 1].top + o.grid[i - 1].height) fail(`${f}: grids overlap`);
    const last = o.grid[g - 1]; if (last.top + last.height > b.height) fail(`${f}: grid exceeds canvas`);
    // formatter smoke test: every series tooltip must render for its first datum
    for (const s of o.series) {
      const fmt = s.tooltip?.formatter; const d = s.data?.[0];
      if (fmt && d) {
        const html = fmt({ data: d, value: d.value ?? d, name: s.name });
        if (typeof html !== 'string' || html.includes('undefined') || html.includes('NaN')) fail(`${f}: bad tooltip in ${s.name}: ${html}`);
      }
    }
    minH = Math.min(minH, b.height); maxH = Math.max(maxH, b.height);
  }
  const [a, z] = icuWindow(p); if (!(z > a)) fail(`${f}: bad ICU window`);
  n++;
}
console.log(`OK  ${n} patients x 4 lab selections, ${series} series built; canvas height ${minH}-${maxH}px`);
