import type { Patient, Micro, Sirs, Pt } from '../types.ts';
import {
  C, locColor, DEVICE_RANK, DEVICE_LABEL, DEVICE_SHORT, PRESSOR_LABEL, PRESSOR_ORDER, SITE_ORDER, LAB_LABEL, abxLabel,
} from './theme.ts';
import { esc, fmtClock, fmtTick, fmtOffset, fmtDuration, fmtNum, titleCase, shortOrganism } from './format.ts';

export const LEFT = 196;
export const RIGHT = 28;
const HEAD = 26;     // lane title strip above each grid
const GAP = 12;      // space below each lane
const ROW = 22;      // px per row in multi-row lanes
export const SLIDER_H = 34;
const COURSE_GAP_MS = 36 * 3_600_000; // doses further apart than this start a new antimicrobial course

export interface BuildCtx { sirs: Sirs; tz: string; labKey: string }

interface Lane {
  key: string;
  title: string;
  note?: string;           // small grey text after the title
  body: number;            // grid height in px
  yAxis: any;
  series: any[];
  legend?: string[];       // series names to list in the lane legend
  empty?: string;          // message when there is nothing to draw
}

export interface Built {
  option: any;
  height: number;
  laneCount: number;
  lanes: { key: string; top: number; body: number }[];
}

type Rect = { x: number; y: number; width: number; height: number };
function clipRect(r: Rect, b: Rect): Rect | null {
  const x1 = Math.max(r.x, b.x), y1 = Math.max(r.y, b.y);
  const x2 = Math.min(r.x + r.width, b.x + b.width), y2 = Math.min(r.y + r.height, b.y + b.height);
  if (x2 <= x1 || y2 <= y1) return null;
  return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
}

/** Horizontal bars on a category y-axis: data items are {value:[start,end,rowIdx,labelIdx], meta, itemStyle}. */
function barRenderer(heightRatio: number, labels: string[], labelColor = '#fff') {
  return (params: any, api: any) => {
    const row = api.value(2);
    const s = api.coord([api.value(0), row]);
    const e = api.coord([api.value(1), row]);
    const unit = api.size([0, 1])[1];
    const h = unit * heightRatio;
    const cs = params.coordSys;
    const rect = clipRect(
      { x: s[0], y: s[1] - h / 2, width: Math.max(e[0] - s[0], 2), height: h },
      { x: cs.x, y: cs.y, width: cs.width, height: cs.height },
    );
    if (!rect) return null;
    const text = labels[api.value(3)] ?? '';
    const children: any[] = [{
      type: 'rect', shape: { ...rect, r: 3 }, style: api.style(),
    }];
    if (text && rect.width > text.length * 6.2 + 12) {
      children.push({
        type: 'text',
        style: { text, x: rect.x + 6, y: rect.y + rect.height / 2, align: 'left', verticalAlign: 'middle', textAlign: 'left', textVerticalAlign: 'middle', fill: labelColor, fontSize: 11, fontWeight: 500 },
        silent: true,
      });
    }
    return { type: 'group', children };
  };
}

/** Thin connector from collect time to result time on a category row. */
function connectorRenderer(color: string) {
  return (params: any, api: any) => {
    const row = api.value(2);
    const s = api.coord([api.value(0), row]);
    const e = api.coord([api.value(1), row]);
    const cs = params.coordSys;
    const rect = clipRect(
      { x: s[0], y: s[1] - 1, width: Math.max(e[0] - s[0], 1), height: 2 },
      { x: cs.x, y: cs.y, width: cs.width, height: cs.height },
    );
    if (!rect) return null;
    return { type: 'rect', shape: rect, style: { fill: color }, silent: true };
  };
}

function tipBox(title: string, rows: [string, string][], accent?: string): string {
  const head = `<div style="font-weight:600;margin-bottom:4px;${accent ? `border-left:3px solid ${accent};padding-left:6px` : ''}">${title}</div>`;
  const body = rows
    .filter(([, v]) => v !== '' && v != null)
    .map(([k, v]) => `<div style="display:flex;gap:10px;justify-content:space-between"><span style="color:${C.inkMuted}">${esc(k)}</span><span style="text-align:right">${v}</span></div>`)
    .join('');
  return `<div style="min-width:190px;font-size:12px;line-height:1.5">${head}${body}</div>`;
}

function lookup(series: Pt[], t: number): number {
  let lo = 0, hi = series.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (series[mid][0] <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans >= 0 ? series[ans][1] : 0;
}

function emptyAxis(): any {
  return { type: 'value', show: false, min: 0, max: 1 };
}

function categoryAxis(labels: string[]): any {
  return {
    type: 'category', data: labels, inverse: true,
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { color: C.inkSoft, fontSize: 11, align: 'right', margin: 10, width: LEFT - 28, overflow: 'truncate', interval: 0 },
    splitLine: { show: true, lineStyle: { color: C.grid } },
  };
}

function valueAxis(opts: { min?: number | string; max?: number | string; name?: string; split?: number; fmt?: (v: number) => string }): any {
  return {
    type: 'value', min: opts.min, max: opts.max, splitNumber: opts.split ?? 2, scale: opts.min === undefined,
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { color: C.inkMuted, fontSize: 10.5, margin: 8, formatter: opts.fmt },
    splitLine: { show: true, lineStyle: { color: C.grid } },
  };
}

// ---------------------------------------------------------------- lanes ----
function locationLane(p: Patient, tz: string): Lane {
  const stayLabels = p.icu_stays.map((s, i) => `ICU stay ${i + 1} · ${fmtDuration(s.end - s.start)}`);
  const stays = p.icu_stays.map((s, i) => ({
    value: [s.start, s.end, 0, i],
    meta: { kind: 'stay', i, s },
    itemStyle: { color: C.icu },
  }));
  const locLabels = p.adt.map((a) => (a.category === 'icu' ? '' : titleCase(a.name ?? a.category)));
  const locs = p.adt.map((a, i) => ({
    value: [a.start, a.end, 1, i],
    meta: { kind: 'loc', a },
    itemStyle: { color: locColor(a.category) },
  }));
  const fmt = (params: any) => {
    const m = params.data.meta;
    if (m.kind === 'stay') {
      const s = m.s;
      return tipBox(`ICU stay ${m.i + 1}`, [
        ['Arrived', esc(fmtClock(s.start, tz))],
        ['Left', esc(fmtClock(s.end, tz))],
        ['Duration', esc(fmtDuration(s.end - s.start))],
        ['Unit', esc(s.types.map((t: string) => titleCase(t.replace(/_/g, ' '))).join(' → ') || 'ICU')],
      ], C.icu);
    }
    const a = m.a;
    return tipBox(esc(titleCase(a.name ?? a.category)), [
      ['Category', esc(a.category)],
      ['In', esc(fmtClock(a.start, tz))],
      ['Out', esc(fmtClock(a.end, tz))],
      ['Duration', esc(fmtDuration(a.end - a.start))],
    ], locColor(a.category));
  };
  return {
    key: 'location', title: 'ICU stays & location', body: 2 * ROW + 6,
    yAxis: { ...categoryAxis(['ICU stays', 'Hospital location']) },
    series: [
      { type: 'custom', name: 'ICU stay', renderItem: barRenderer(0.74, stayLabels), encode: { x: [0, 1], y: 2 }, data: stays, tooltip: { formatter: fmt } },
      { type: 'custom', name: 'Location', renderItem: barRenderer(0.74, locLabels), encode: { x: [0, 1], y: 2 }, data: locs, tooltip: { formatter: fmt } },
    ],
  };
}

function respLane(p: Patient, tz: string): Lane {
  const devices = [...new Set(p.resp.bands.map((b) => b.device))]
    .sort((a, b) => (DEVICE_RANK[b] ?? 0) - (DEVICE_RANK[a] ?? 0));
  if (!devices.length) return { key: 'resp', title: 'Respiratory support', body: 44, yAxis: emptyAxis(), series: [], empty: 'No respiratory support recorded' };
  const KEY = ['IMV', 'NIPPV', 'CPAP', 'High Flow NC', 'Face Mask', 'Nasal Cannula', 'Other'];
  const shown = [...KEY, ...devices.filter((d) => !KEY.includes(d))]; // full colour key, even for absent devices
  const series = shown.map((dev) => ({
    type: 'custom', name: DEVICE_LABEL[dev] ?? dev,
    renderItem: barRenderer(0.86, [DEVICE_SHORT[dev] ?? dev], dev === 'Face Mask' ? '#1c2733' : '#ffffff'),
    encode: { x: [0, 1], y: 2 },
    data: p.resp.bands.filter((b) => b.device === dev).map((b) => ({
      value: [b.start, b.end, 0, 0], meta: b, itemStyle: { color: C.device[dev] ?? C.device.Other },
    })),
    tooltip: {
      formatter: (params: any) => {
        const b = params.data.meta;
        return tipBox(esc(DEVICE_LABEL[b.device] ?? b.device), [
          ['From', esc(fmtClock(b.start, tz))],
          ['To', esc(fmtClock(b.end, tz))],
          ['Duration', esc(fmtDuration(b.end - b.start))],
        ], C.device[b.device] ?? C.device.Other);
      },
    },
  }));
  return {
    key: 'resp', title: 'Respiratory support', note: 'one block per device', body: ROW + 10,
    yAxis: categoryAxis(['Support device']), series, legend: shown.map((d) => DEVICE_LABEL[d] ?? d),
  };
}

function lineLane(key: string, title: string, pts: Pt[], color: string, unit: string, tz: string, empty: string, opts: { min?: number; max?: number; step?: boolean; digits?: number } = {}): Lane {
  if (!pts.length) return { key, title, body: 44, yAxis: emptyAxis(), series: [], empty };
  return {
    key, title, note: unit, body: 62,
    yAxis: valueAxis({ min: opts.min, max: opts.max }),
    series: [{
      type: 'line', name: title, data: pts, step: opts.step ? 'end' : false, showSymbol: true, symbolSize: 4,
      lineStyle: { color, width: 1.6 }, itemStyle: { color },
      tooltip: { formatter: (pa: any) => tipBox(esc(title), [[unit || 'Value', `<b>${fmtNum(pa.value[1], opts.digits ?? 1)}</b>`], ['Time', esc(fmtClock(pa.value[0], tz))]], color) },
    }],
  };
}

function pressorLane(p: Patient, tz: string): Lane {
  const present = PRESSOR_ORDER.filter((k) => p.pressors.agents[k]);
  if (!present.length) return { key: 'pressor', title: 'Vasopressors', body: 44, yAxis: emptyAxis(), series: [], empty: 'No vasopressor infusions recorded' };
  const series: any[] = present.map((k) => ({
    type: 'line', name: PRESSOR_LABEL[k] ?? k, step: 'end', showSymbol: false, silent: true,
    data: p.pressors.agents[k].nee, lineStyle: { color: C.pressor[k], width: 1.7 }, itemStyle: { color: C.pressor[k] }, z: 3,
  }));
  const maxNee = Math.max(0.1, ...p.pressors.nee.map((x) => x[1]));
  series.push({
    type: 'line', name: 'Total (NE-equivalent)', step: 'end', showSymbol: true, symbolSize: 5, z: 4,
    data: p.pressors.nee, lineStyle: { color: C.ink, width: 2.2 }, itemStyle: { color: C.ink },
    areaStyle: { color: C.ink, opacity: 0.07 },
    tooltip: {
      formatter: (pa: any) => {
        const t = pa.value[0];
        const rows: [string, string][] = [['NE-equivalent', `<b>${fmtNum(pa.value[1], 3)}</b> mcg/kg/min`]];
        for (const k of present) {
          const a = p.pressors.agents[k];
          const d = lookup(a.dose, t);
          if (d > 0) rows.push([PRESSOR_LABEL[k] ?? k, `${fmtNum(d, 3)} ${esc(a.unit)}`]);
        }
        rows.push(['Time', esc(fmtClock(t, tz))]);
        return tipBox('Vasopressor support', rows, C.ink);
      },
    },
  });
  return {
    key: 'pressor', title: 'Vasopressors', note: 'norepinephrine-equivalent, mcg/kg/min', body: 96,
    yAxis: valueAxis({ min: 0, max: Math.ceil(maxNee * 11) / 10, split: 2, fmt: (v: number) => fmtNum(v, 2) }),
    series, legend: [...present.map((k) => PRESSOR_LABEL[k] ?? k), 'Total (NE-equivalent)'],
  };
}

function microLane(p: Patient, tz: string): Lane {
  if (!p.micro.length) return { key: 'micro', title: 'Microbiology', body: 44, yAxis: emptyAxis(), series: [], empty: 'No cultures recorded' };
  const sites = SITE_ORDER.filter((s) => p.micro.some((m) => m.site === s));
  const idx = (m: Micro) => sites.indexOf(m.site);
  const fmt = (pa: any) => {
    const m: Micro = pa.data.meta;
    const turnaround = m.result_t ? fmtDuration(m.result_t - m.t) : '';
    return tipBox(esc(m.fluid ? titleCase(m.fluid) : m.site), [
      ['Test', esc(m.method ? titleCase(m.method) : '')],
      ['Collected', esc(fmtClock(m.t, tz))],
      ['Resulted', m.result_t ? `${esc(fmtClock(m.result_t, tz))} (${esc(turnaround)})` : 'not reported'],
      ['Result', m.positive ? `<b style="color:${C.positive}">${esc(m.organisms.map(titleCase).join('; '))}</b>` : m.cancelled ? 'Cancelled' : 'No organism reported'],
    ], m.positive ? C.positive : C.negative);
  };
  const conn = p.micro.filter((m) => m.result_t && m.result_t > m.t).map((m) => ({ value: [m.t, m.result_t, idx(m), 0] }));
  const mk = (m: Micro) => ({ value: [m.t, idx(m)], meta: m });
  return {
    key: 'micro', title: 'Microbiology', note: 'marker at collection time; line runs to result', body: sites.length * ROW + 6,
    yAxis: categoryAxis(sites),
    legend: ['Organism isolated', 'No organism reported'],
    series: [
      { type: 'custom', name: 'Result turnaround', renderItem: connectorRenderer('#c8d0da'), encode: { x: [0, 1], y: 2 }, data: conn, silent: true, z: 1 },
      {
        type: 'scatter', name: 'No organism reported', symbol: 'circle', symbolSize: 9, z: 3,
        itemStyle: { color: '#ffffff', borderColor: C.negative, borderWidth: 1.6 },
        data: p.micro.filter((m) => !m.positive).map(mk), tooltip: { formatter: fmt },
      },
      {
        type: 'scatter', name: 'Organism isolated', symbol: 'circle', symbolSize: 12, z: 4,
        itemStyle: { color: C.positive, borderColor: '#ffffff', borderWidth: 2 },
        data: p.micro.filter((m) => m.positive).map(mk), tooltip: { formatter: fmt },
        label: { show: true, position: 'right', distance: 7, fontSize: 10.5, color: C.inkSoft, formatter: (pa: any) => shortOrganism(pa.data.meta.organisms[0]) + (pa.data.meta.organisms.length > 1 ? ` +${pa.data.meta.organisms.length - 1}` : '') },
        labelLayout: { hideOverlap: true },
      },
    ],
  };
}

function abxLane(p: Patient, tz: string): Lane {
  const agents = Object.entries(p.abx)
    .filter(([, a]) => a.doses.length)
    .sort((a, b) => a[1].doses[0][0] - b[1].doses[0][0]);
  if (!agents.length) return { key: 'abx', title: 'Antimicrobials', body: 44, yAxis: emptyAxis(), series: [], empty: 'No antimicrobial doses recorded' };
  const rows = agents.map(([k]) => abxLabel(k));
  const courses: any[] = [];
  const doses: Record<string, any[]> = {};
  agents.forEach(([k, a], row) => {
    const sorted = [...a.doses].sort((x, y) => x[0] - y[0]);
    let start = sorted[0][0], last = start, n = 1;
    const flush = () => {
      if (n > 1) courses.push({ value: [start, last, row, 0], meta: { name: abxLabel(k), cls: a.class, start, last, n }, itemStyle: { color: C.abx[a.class] ?? C.abx.antibacterial, opacity: 0.28 } });
    };
    for (const d of sorted) {
      (doses[a.class] ||= []).push({ value: [d[0], row], meta: { name: abxLabel(k), dose: d } });
      if (d !== sorted[0]) {
        if (d[0] - last > COURSE_GAP_MS) { flush(); start = d[0]; n = 1; } else n += 1;
        last = d[0];
      }
    }
    flush();
  });
  const classNames: Record<string, string> = { antibacterial: 'Antibacterial', antifungal: 'Antifungal', antiviral: 'Antiviral' };
  const doseTip = (pa: any) => {
    const { name, dose } = pa.data.meta;
    return tipBox(esc(name), [
      ['Dose', dose[1] != null ? `<b>${fmtNum(dose[1])}</b> ${esc(dose[2] ?? '')}` : 'not recorded'],
      ['Route', esc((dose[3] ?? '').toUpperCase())],
      ['Given', esc(fmtClock(dose[0], tz))],
    ], undefined);
  };
  const series: any[] = [{
    type: 'custom', name: 'Course', renderItem: barRenderer(0.46, ['']), encode: { x: [0, 1], y: 2 }, data: courses, z: 1,
    tooltip: {
      formatter: (pa: any) => {
        const m = pa.data.meta;
        return tipBox(`${esc(m.name)} course`, [
          ['First dose', esc(fmtClock(m.start, tz))], ['Last dose', esc(fmtClock(m.last, tz))],
          ['Doses', String(m.n)], ['Span', esc(fmtDuration(m.last - m.start))],
        ], C.abx[m.cls]);
      },
    },
  }];
  const present = Object.keys(doses);
  for (const cls of present) {
    series.push({
      type: 'scatter', name: classNames[cls] ?? cls, symbol: 'diamond', symbolSize: 9, z: 3,
      itemStyle: { color: C.abx[cls] ?? C.abx.antibacterial, borderColor: '#fff', borderWidth: 1 },
      data: doses[cls], tooltip: { formatter: doseTip },
    });
  }
  return {
    key: 'abx', title: 'Antimicrobials', note: 'diamond = dose given; band = course (doses ≤ 36 h apart)', body: rows.length * ROW + 6,
    yAxis: categoryAxis(rows), series, legend: present.map((c) => classNames[c] ?? c),
  };
}

function thresholdLane(key: string, title: string, unit: string, pts: Pt[], color: string, hi: number, lo: number, tz: string, digits: number, minFloor: number, maxCeil: number): Lane {
  if (!pts.length) return { key, title, body: 44, yAxis: emptyAxis(), series: [], empty: `No ${title.toLowerCase()} values recorded` };
  const vals = pts.map((x) => x[1]);
  const min = Math.min(minFloor, Math.floor(Math.min(...vals)) - 0.5);
  const max = Math.max(maxCeil, Math.ceil(Math.max(...vals)) + 0.5);
  const data = pts.map(([t, v]) => ({
    value: [t, v],
    itemStyle: v > hi ? { color: C.hot } : v < lo ? { color: C.cold } : { color },
    symbolSize: v > hi || v < lo ? 6 : 4,
  }));
  const state = (v: number) => (v > hi ? ` <span style="color:${C.hot}">above ${hi}</span>` : v < lo ? ` <span style="color:${C.cold}">below ${lo}</span>` : '');
  return {
    key, title, note: `${unit} · shaded = outside SIRS range (${lo}–${hi})`, body: 84,
    yAxis: valueAxis({ min, max, split: 3 }),
    series: [{
      type: 'line', name: title, data, showSymbol: true, lineStyle: { color, width: 1.6 }, itemStyle: { color },
      markArea: {
        silent: true, data: [
          [{ yAxis: hi, itemStyle: { color: C.fever } }, { yAxis: max }],
          [{ yAxis: min, itemStyle: { color: C.hypo } }, { yAxis: lo }],
        ],
      },
      markLine: {
        silent: true, symbol: 'none', animation: false,
        lineStyle: { color: '#aab4c0', type: 'dashed', width: 1 },
        label: { show: true, position: 'insideEndTop', fontSize: 10, color: C.inkMuted, formatter: (pa: any) => String(pa.value) },
        data: [{ yAxis: hi }, { yAxis: lo }],
      },
      tooltip: { formatter: (pa: any) => tipBox(esc(title), [[unit, `<b>${fmtNum(pa.value[1], digits)}</b>${state(pa.value[1])}`], ['Time', esc(fmtClock(pa.value[0], tz))]], color) },
    }],
  };
}

function otherLabLane(p: Patient, key: string, tz: string): Lane {
  const name = LAB_LABEL[key] ?? titleCase(key.replace(/_/g, ' '));
  const lab = p.labs[key];
  if (!lab || !lab.values.length) return { key: 'lab', title: `Other labs: ${name}`, body: 44, yAxis: emptyAxis(), series: [], empty: `No ${name} results for this hospitalization` };
  const unit = lab.unit ?? '';
  return {
    key: 'lab', title: `Other labs: ${name}`, note: unit, body: 70,
    yAxis: valueAxis({ split: 2 }),
    series: [{
      type: 'line', name, data: lab.values, showSymbol: true, symbolSize: 5, lineStyle: { color: C.lab, width: 1.5 }, itemStyle: { color: C.lab },
      tooltip: { formatter: (pa: any) => tipBox(esc(name), [[unit || 'Value', `<b>${fmtNum(pa.value[1], 2)}</b>`], ['Time', esc(fmtClock(pa.value[0], tz))]], C.lab) },
    }],
  };
}

// ---------------------------------------------------------------- build ----
export function buildOption(p: Patient, ctx: BuildCtx): Built {
  const { sirs, tz } = ctx;
  const lanes: Lane[] = [
    locationLane(p, tz),
    thresholdLane('temp', 'Temperature', '°C', p.temp, C.temp, sirs.temp_high_c, sirs.temp_low_c, tz, 1, 35, 39),
    thresholdLane('wbc', 'WBC', '×10³/µL', (p.labs.wbc?.values ?? []), C.wbc, sirs.wbc_high, sirs.wbc_low, tz, 1, 0, 16),
    pressorLane(p, tz),
    microLane(p, tz),
    abxLane(p, tz),
    respLane(p, tz),
    lineLane('fio2', 'FiO₂', p.resp.fio2, C.fio2, '%', tz, 'No FiO₂ recorded', { min: 20, max: 100, digits: 0 }),
    lineLane('peep', 'PEEP', p.resp.peep, C.peep, 'cmH₂O', tz, 'No PEEP recorded', { min: 0, digits: 0 }),
    otherLabLane(p, ctx.labKey, tz),
  ];

  const RULER_TOP = 26;   // room above the ruler grid for its tick labels
  const RULER_H = 2;
  let top = RULER_TOP + RULER_H + 14;

  const grids: any[] = [{ left: LEFT, right: RIGHT, top: RULER_TOP, height: RULER_H }];
  const xAxes: any[] = [];
  const yAxes: any[] = [{ gridIndex: 0, type: 'value', show: false, min: 0, max: 1 }];
  const series: any[] = [];
  const graphic: any[] = [];
  const legends: any[] = [];
  const laneInfo: Built['lanes'] = [];
  const icuAreas = p.icu_stays.map((s) => [{ xAxis: s.start }, { xAxis: s.end }]);

  const tickFmt = (v: number) => fmtTick(v, tz);
  const axisBase = (gridIndex: number, showLabels: boolean, position: 'top' | 'bottom') => ({
    gridIndex, type: 'time', min: p.axis.start, max: p.axis.end, position,
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { show: showLabels, color: C.inkSoft, fontSize: 10.5, formatter: tickFmt, hideOverlap: true, margin: 8 },
    splitLine: { show: true, lineStyle: { color: C.grid } },
    axisPointer: {
      show: true, snap: false, lineStyle: { color: '#6b7a8c', width: 1, type: 'solid' },
      label: {
        show: showLabels, backgroundColor: C.ink, color: '#fff', fontSize: 11, padding: [4, 7],
        formatter: (pa: any) => `${fmtClock(pa.value, tz)}  (${fmtOffset(pa.value, p.axis.admission)})`,
      },
    },
  });
  xAxes.push(axisBase(0, true, 'top'));

  lanes.forEach((lane, i) => {
    const gi = i + 1;
    const isLast = i === lanes.length - 1;
    grids.push({ left: LEFT, right: RIGHT, top: top + HEAD, height: lane.body, backgroundColor: '#ffffff', show: true, borderColor: C.rule, borderWidth: 1 });
    xAxes.push(axisBase(gi, isLast, 'bottom'));
    yAxes.push({ gridIndex: gi, ...lane.yAxis });
    laneInfo.push({ key: lane.key, top: top + HEAD, body: lane.body });

    graphic.push({
      type: 'text', left: 14, top: top + 5, silent: true,
      style: { text: lane.title, fill: C.ink, fontSize: 13, fontWeight: 600 },
    });
    if (lane.note) {
      graphic.push({
        type: 'text', left: 14 + Math.max(60, lane.title.length * 7.6) + 6, top: top + 7, silent: true,
        style: { text: lane.note, fill: C.inkMuted, fontSize: 11 },
      });
    }
    if (lane.empty) {
      graphic.push({
        type: 'text', left: LEFT + 14, top: top + HEAD + lane.body / 2 - 8, silent: true,
        style: { text: lane.empty, fill: C.inkMuted, fontSize: 12, fontStyle: 'italic' },
      });
    }
    for (const s of lane.series) series.push({ ...s, xAxisIndex: gi, yAxisIndex: gi });
    if (icuAreas.length) {
      series.push({
        type: 'line', data: [], silent: true, xAxisIndex: gi, yAxisIndex: gi, name: `__icu_${lane.key}`,
        markArea: { silent: true, itemStyle: { color: C.icuTint }, data: icuAreas },
      });
    }
    if (lane.legend?.length) {
      legends.push({
        data: lane.legend, top: top + 3, right: RIGHT + 4, itemWidth: 10, itemHeight: 10, itemGap: 14, icon: 'roundRect',
        textStyle: { color: C.inkSoft, fontSize: 11 }, selectedMode: true,
      });
    }
    top += HEAD + lane.body + GAP;
  });

  const total = top + SLIDER_H + 6;
  const all = xAxes.map((_, i) => i);

  const option = {
    animation: false,
    useUTC: true,              // tick positions on UTC boundaries; labels are formatted in the configured time zone
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'inherit' },
    tooltip: {
      trigger: 'item', confine: true, appendToBody: false,
      backgroundColor: '#ffffff', borderColor: C.rule, borderWidth: 1, padding: [8, 10],
      textStyle: { color: C.ink, fontSize: 12 },
      extraCssText: 'box-shadow:0 6px 20px rgba(28,39,51,.14);border-radius:6px;',
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    legend: legends,
    graphic,
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    series,
    dataZoom: [
      { type: 'inside', xAxisIndex: all, filterMode: 'none', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: 'shift', moveOnMouseMove: true, minValueSpan: 30 * 60 * 1000 },
      {
        type: 'slider', xAxisIndex: all, filterMode: 'none', bottom: 4, height: 22, left: LEFT, right: RIGHT,
        showDataShadow: false, brushSelect: false, borderColor: C.rule, fillerColor: 'rgba(36,95,168,.14)',
        handleSize: '100%', textStyle: { color: C.inkMuted, fontSize: 10.5 }, labelFormatter: (v: number) => fmtClock(v, tz),
      },
    ],
  };
  return { option, height: total, laneCount: lanes.length, lanes: laneInfo };
}

/** Time window covering all ICU stays, with a little padding; falls back to the full axis. */
export function icuWindow(p: Patient): [number, number] {
  if (!p.icu_stays.length) return [p.axis.start, p.axis.end];
  const s = Math.min(...p.icu_stays.map((x) => x.start));
  const e = Math.max(...p.icu_stays.map((x) => x.end));
  const pad = Math.max((e - s) * 0.03, 3_600_000);
  return [Math.max(p.axis.start, s - pad), Math.min(p.axis.end, e + pad)];
}
