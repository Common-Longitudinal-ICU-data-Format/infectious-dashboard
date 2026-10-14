import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart, ScatterChart, CustomChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkAreaComponent,
  MarkLineComponent, GraphicComponent, AxisPointerComponent,
} from 'echarts/components';
import { LabelLayout } from 'echarts/features';
import { CanvasRenderer } from 'echarts/renderers';
import type { Patient, Sirs } from '../types';
import { buildOption } from '../lib/timeline';

echarts.use([
  LineChart, ScatterChart, CustomChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent,
  MarkAreaComponent, MarkLineComponent, GraphicComponent, AxisPointerComponent, LabelLayout, CanvasRenderer,
]);

export interface ViewRequest { start: number; end: number; nonce: number }
export interface ChartHandle { zoomBy: (factor: number) => void; savePng: () => void }

interface Props {
  patient: Patient;
  sirs: Sirs;
  tz: string;
  labKey: string;
  view: ViewRequest;
  onReady: (h: ChartHandle) => void;
}

export default function TimelineChart({ patient, sirs, tz, labKey, view, onReady }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const built = useMemo(() => buildOption(patient, { sirs, tz, labKey }), [patient, sirs, tz, labKey]);

  useEffect(() => {
    const c = echarts.init(el.current!, undefined, { renderer: 'canvas' });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current!);
    return () => { ro.disconnect(); c.dispose(); chart.current = null; };
  }, []);

  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    c.resize({ height: built.height });
    c.setOption(built.option, true);
    c.dispatchAction({ type: 'dataZoom', startValue: view.start, endValue: view.end });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [built]);

  useEffect(() => {
    chart.current?.dispatchAction({ type: 'dataZoom', startValue: view.start, endValue: view.end });
  }, [view]);

  useEffect(() => {
    onReady({
      zoomBy: (factor) => {
        const c = chart.current;
        if (!c) return;
        const dz = (c.getOption() as any).dataZoom?.[0];
        if (!dz) return;
        const a = patient.axis.start, b = patient.axis.end;
        const s = a + ((b - a) * dz.start) / 100, e = a + ((b - a) * dz.end) / 100;
        const mid = (s + e) / 2, half = ((e - s) / 2) * factor;
        c.dispatchAction({ type: 'dataZoom', startValue: Math.max(a, mid - half), endValue: Math.min(b, mid + half) });
      },
      savePng: () => {
        const c = chart.current;
        if (!c) return;
        const url = c.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#ffffff' });
        const a = document.createElement('a');
        a.href = url;
        a.download = `timeline_${patient.id}.png`;
        a.click();
      },
    });
  }, [patient, onReady]);

  return <div ref={el} className="chart" style={{ height: built.height }} role="img" aria-label={`ICU infection timeline for hospitalization ${patient.id}`} />;
}
