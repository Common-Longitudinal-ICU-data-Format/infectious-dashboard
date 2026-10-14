// Colours live here because ECharts draws on <canvas> and cannot read CSS variables.
// Categorical hues follow the validated reference palette (fixed order, never cycled);
// support level uses ONE blue ramp light -> dark; red is reserved for "positive/abnormal".
export const C = {
  surface: '#ffffff',
  ink: '#1c2733',
  inkSoft: '#52606d',
  inkMuted: '#7b8794',
  grid: '#e6ebf1',
  rule: '#d5dce5',
  icuTint: 'rgba(36, 95, 168, 0.06)',

  // location
  icu: '#245fa8',
  stepdown: '#7ea6d8',
  ward: '#d3dce8',
  ed: '#ecd3ac',
  otherLoc: '#e3e6ea',

  // respiratory support: one hue per device (blocks on a single row)
  device: {
    IMV: '#2a78d6',
    NIPPV: '#6250d6',
    CPAP: '#e87ba4',
    'High Flow NC': '#1baf7a',
    'Face Mask': '#eda100',
    'Nasal Cannula': '#eb6834',
    'Room Air': '#8a95a3',
    Other: '#8a95a3',
  } as Record<string, string>,

  fio2: '#0e7c86',
  peep: '#6250d6',

  // vasopressors (categorical slots 1,7,8,3,4 of the reference palette)
  pressor: {
    norepinephrine: '#2a78d6',
    vasopressin: '#6250d6',
    epinephrine: '#e34948',
    phenylephrine: '#1baf7a',
    dopamine: '#eda100',
    angiotensin: '#e87ba4',
  } as Record<string, string>,

  // microbiology
  positive: '#c92a2a',
  negative: '#8a95a3',

  // antimicrobials by class
  abx: { antibacterial: '#0f766e', antifungal: '#7c5cbf', antiviral: '#b45f06' } as Record<string, string>,

  temp: '#d9480f',
  hot: '#c92a2a',
  cold: '#2563a8',
  fever: 'rgba(201, 42, 42, 0.07)',
  hypo: 'rgba(37, 99, 168, 0.07)',
  wbc: '#a8326b',
  lab: '#4f46b8',
};

export function locColor(category: string): string {
  switch (category) {
    case 'icu': return C.icu;
    case 'stepdown': return C.stepdown;
    case 'ward': return C.ward;
    case 'ed': return C.ed;
    default: return C.otherLoc;
  }
}

export const DEVICE_RANK: Record<string, number> = {
  IMV: 6, NIPPV: 5, CPAP: 4, 'High Flow NC': 3, 'Face Mask': 2, 'Nasal Cannula': 1, 'Room Air': 0, Other: 0,
};

export const DEVICE_LABEL: Record<string, string> = {
  IMV: 'Invasive ventilation', NIPPV: 'BiPAP / NIPPV', CPAP: 'CPAP', 'High Flow NC': 'High-flow nasal',
  'Face Mask': 'Face mask', 'Nasal Cannula': 'Nasal cannula', 'Room Air': 'Room air', Other: 'Other device',
};

export const DEVICE_SHORT: Record<string, string> = {
  IMV: 'Ventilator', NIPPV: 'BiPAP', CPAP: 'CPAP', 'High Flow NC': 'High-flow', 'Face Mask': 'Face mask',
  'Nasal Cannula': 'Nasal cannula', 'Room Air': 'Room air', Other: 'Other',
};

export const PRESSOR_LABEL: Record<string, string> = {
  norepinephrine: 'Norepinephrine', vasopressin: 'Vasopressin', epinephrine: 'Epinephrine',
  phenylephrine: 'Phenylephrine', dopamine: 'Dopamine', angiotensin: 'Angiotensin II',
};
export const PRESSOR_ORDER = ['norepinephrine', 'vasopressin', 'epinephrine', 'phenylephrine', 'dopamine', 'angiotensin'];

export const SITE_ORDER = ['Blood', 'Respiratory', 'Urine', 'Sterile fluid', 'CSF', 'Wound / line', 'Stool', 'Other'];

export const LAB_LABEL: Record<string, string> = {
  lactate: 'Lactate', crp: 'CRP', creatinine: 'Creatinine', neutrophils_absolute: 'Neutrophils (abs)',
  platelet_count: 'Platelets', procalcitonin: 'Procalcitonin', wbc: 'WBC',
};

const ABX_SHORT: Record<string, string> = {
  piperacillin_tazobactam: 'Pip / tazo', ampicillin_sulbactam: 'Amp / sulbactam',
  trimethoprim_sulfamethoxazole: 'TMP / SMX',
};
export function abxLabel(cat: string): string {
  if (ABX_SHORT[cat]) return ABX_SHORT[cat];
  const s = cat.replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}
