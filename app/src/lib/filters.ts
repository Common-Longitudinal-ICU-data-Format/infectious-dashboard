import type { IndexRow } from '../types.ts';

export type SortKey = 'icu_hours' | 'los' | 'age' | 'cultures' | 'id';

export interface Filters {
  q: string;
  positive: boolean;      // any positive culture
  blood: boolean;         // positive blood culture
  imv: boolean;
  niv: boolean;           // NIV or high-flow
  pressor: boolean;
  abx: boolean;
  fever: boolean;
  died: boolean;
  organism: string;       // '' = any
  minIcuHours: number;
  sort: SortKey;
}

export const DEFAULT_FILTERS: Filters = {
  q: '', positive: false, blood: false, imv: false, niv: false, pressor: false, abx: false, fever: false,
  died: false, organism: '', minIcuHours: 0, sort: 'icu_hours',
};

export function applyFilters(rows: IndexRow[], f: Filters): IndexRow[] {
  const q = f.q.trim().toLowerCase();
  const out = rows.filter((r) =>
    (!q || r.id.includes(q) || r.patient_id.includes(q)) &&
    (!f.positive || r.positive_culture) &&
    (!f.blood || r.blood_culture_positive) &&
    (!f.imv || r.imv) &&
    (!f.niv || r.niv || r.hfnc) &&
    (!f.pressor || r.pressor) &&
    (!f.abx || r.n_antibiotics > 0) &&
    (!f.fever || r.fever) &&
    (!f.died || r.died) &&
    (!f.organism || r.organisms.includes(f.organism)) &&
    (r.icu_hours ?? 0) >= f.minIcuHours,
  );
  const num = (v: number | null) => v ?? -1;
  const key: Record<SortKey, (r: IndexRow) => number | string> = {
    icu_hours: (r) => num(r.icu_hours), los: (r) => num(r.los_days), age: (r) => num(r.age),
    cultures: (r) => r.n_cultures, id: (r) => r.id,
  };
  const k = key[f.sort];
  return out.sort((a, b) => {
    const x = k(a), y = k(b);
    if (f.sort === 'id') return String(x).localeCompare(String(y));
    return (y as number) - (x as number);
  });
}

export function activeFilterCount(f: Filters): number {
  return (['positive', 'blood', 'imv', 'niv', 'pressor', 'abx', 'fever', 'died'] as const).filter((k) => f[k]).length
    + (f.organism ? 1 : 0) + (f.minIcuHours > 0 ? 1 : 0) + (f.q.trim() ? 1 : 0);
}
