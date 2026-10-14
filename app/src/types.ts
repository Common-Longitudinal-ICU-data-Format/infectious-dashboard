export type Pt = [number, number];

export interface AdtRow { start: number; end: number; category: string; type: string | null; name: string | null }
export interface IcuStay { start: number; end: number; types: string[] }
export interface RespBand { device: string; start: number; end: number }
export interface PressorAgent { unit: string; dose: Pt[]; nee: Pt[] }
export interface Micro {
  t: number; result_t: number | null; order_t: number | null;
  site: string; fluid: string | null; method: string | null;
  organisms: string[]; positive: boolean; cancelled: boolean;
}
export type AbxDose = [number, number | null, string | null, string | null];
export interface AbxAgent { name: string; class: string; doses: AbxDose[] }
export interface LabSeries { unit: string | null; values: Pt[] }

export interface Patient {
  id: string;
  patient_id: string;
  axis: { start: number; end: number; admission: number; discharge: number | null };
  demographics: { age: number | null; sex: string | null; discharge: string | null };
  adt: AdtRow[];
  icu_stays: IcuStay[];
  resp: { bands: RespBand[]; fio2: Pt[]; peep: Pt[] };
  pressors: { agents: Record<string, PressorAgent>; nee: Pt[] };
  micro: Micro[];
  abx: Record<string, AbxAgent>;
  temp: Pt[];
  labs: Record<string, LabSeries>;
}

export interface Sirs { temp_high_c: number; temp_low_c: number; wbc_high: number; wbc_low: number }

export interface IndexRow {
  id: string; patient_id: string; age: number | null; sex: string | null; died: boolean;
  admission: number; los_days: number | null; icu_hours: number | null; n_icu_stays: number;
  imv: boolean; niv: boolean; hfnc: boolean; pressor: boolean; pressor_hours: number | null;
  n_cultures: number; positive_culture: boolean; blood_culture_positive: boolean;
  organisms: string[]; sites_positive: string[];
  antibiotics: string[]; n_antibiotics: number;
  max_temp: number | null; fever: boolean; max_wbc: number | null; min_wbc: number | null; wbc_abnormal: boolean;
}

export interface IndexFile {
  meta: {
    source: string; filetype: string; timezone: string; n: number; sirs: Sirs;
    extra_labs: string[]; tables_present: string[]; temp_values_dropped: number;
  };
  hospitalizations: IndexRow[];
}
