import type { IndexRow, Patient, Sirs } from '../types';
import { fmtClock, titleCase } from '../lib/format';

interface Props { row: IndexRow; patient: Patient; sirs: Sirs; tz: string }

export default function PatientHeader({ row, patient, sirs, tz }: Props) {
  const d = patient.demographics;
  const orgs = row.organisms.map(titleCase);
  const stat = (label: string, value: string, sub?: string, tone?: 'alert') => (
    <div className={'stat' + (tone ? ' ' + tone : '')}>
      <span className="stat-v">{value}</span>
      <span className="stat-l">{label}</span>
      {sub && <span className="stat-s">{sub}</span>}
    </div>
  );
  return (
    <section className="phead">
      <div className="phead-id">
        <h1>Hospitalization {row.id}</h1>
        <p>
          Patient {row.patient_id} · {d.age ?? '?'} y {d.sex ?? ''} · admitted {fmtClock(patient.axis.admission, tz)}
          {d.discharge ? ` · discharged: ${d.discharge}` : ''}
        </p>
      </div>
      <div className="stats">
        {stat('ICU time', row.icu_hours != null ? `${row.icu_hours >= 48 ? (row.icu_hours / 24).toFixed(1) + ' d' : Math.round(row.icu_hours) + ' h'}` : '—', `${row.n_icu_stays} ICU stay${row.n_icu_stays === 1 ? '' : 's'}`)}
        {stat('Cultures', String(row.n_cultures), row.positive_culture ? `positive: ${orgs.slice(0, 2).join(', ')}${orgs.length > 2 ? ` +${orgs.length - 2}` : ''}` : 'none positive', row.positive_culture ? 'alert' : undefined)}
        {stat('Antimicrobials', String(row.n_antibiotics), row.n_antibiotics ? 'distinct agents' : 'none given')}
        {stat('Max temp', row.max_temp != null ? `${row.max_temp} °C` : '—', row.fever ? `above ${sirs.temp_high_c}` : 'within SIRS range', row.fever ? 'alert' : undefined)}
        {stat('WBC range', row.min_wbc != null ? `${row.min_wbc}–${row.max_wbc}` : '—', row.wbc_abnormal ? `outside ${sirs.wbc_low}–${sirs.wbc_high}` : '×10³/µL', row.wbc_abnormal ? 'alert' : undefined)}
        {stat('Vasopressors', row.pressor ? `${Math.round(row.pressor_hours ?? 0)} h` : 'none', row.imv ? 'ventilated' : row.niv || row.hfnc ? 'NIV / high-flow' : 'no ventilation')}
      </div>
    </section>
  );
}
