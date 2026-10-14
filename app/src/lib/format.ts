export function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const cache = new Map<string, Intl.DateTimeFormat>();
function dtf(tz: string, opts: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = tz + JSON.stringify(opts);
  let f = cache.get(key);
  if (!f) {
    try { f = new Intl.DateTimeFormat('en-US', { timeZone: tz, hourCycle: 'h23', ...opts }); }
    catch { f = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', hourCycle: 'h23', ...opts }); }
    cache.set(key, f);
  }
  return f;
}

/** "Nov 14, 2111, 05:20" */
export function fmtClock(ms: number, tz: string): string {
  return dtf(tz, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(ms);
}

/** Axis tick: "HH:mm", or "Nov 14" at local midnight. */
export function fmtTick(ms: number, tz: string): string {
  const parts = dtf(tz, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).formatToParts(ms);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  if (get('hour') === '00' && get('minute') === '00') return `${get('month')} ${get('day')}`;
  return `${get('hour')}:${get('minute')}`;
}

/** Hours since hospital admission, e.g. "+17.4 h" or "+3.2 d". */
export function fmtOffset(ms: number, admission: number): string {
  const h = (ms - admission) / 3_600_000;
  const sign = h < 0 ? '-' : '+';
  const a = Math.abs(h);
  return a >= 72 ? `${sign}${(a / 24).toFixed(1)} d` : `${sign}${a.toFixed(1)} h`;
}

export function fmtDuration(ms: number): string {
  const h = ms / 3_600_000;
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${h.toFixed(h < 10 ? 1 : 0)} h`;
  return `${(h / 24).toFixed(1)} d`;
}

export function fmtNum(v: number, digits = 2): string {
  if (!Number.isFinite(v)) return '';
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  return parseFloat(v.toFixed(digits)).toString();
}

export function titleCase(s: string): string {
  return s.toLowerCase().replace(/(^|[\s(\/-])([a-z])/g, (_, a, b) => a + b.toUpperCase());
}

const GENERA = new Set([
  'escherichia', 'klebsiella', 'pseudomonas', 'staphylococcus', 'enterococcus', 'proteus', 'serratia',
  'acinetobacter', 'enterobacter', 'citrobacter', 'stenotrophomonas', 'bacteroides', 'clostridium',
  'clostridioides', 'candida', 'streptococcus', 'prevotella', 'morganella', 'haemophilus',
]);
const NOT_SPECIES = new Set(['sp', 'species', 'complex', 'group']);

/** "ESCHERICHIA COLI" -> "E. coli"; otherwise a trimmed Title Case. */
export function shortOrganism(name: string): string {
  const low = name.toLowerCase().trim();
  if (/^staph\w*\s+aureus/.test(low)) return 'S. aureus';
  const m = low.match(/^([a-z]+)\s+([a-z]+)\b/);
  if (m && GENERA.has(m[1]) && !NOT_SPECIES.has(m[2])) return `${m[1][0].toUpperCase()}. ${m[2]}`;
  const t = titleCase(name);
  return t.length > 18 ? t.slice(0, 17) + '…' : t;
}
