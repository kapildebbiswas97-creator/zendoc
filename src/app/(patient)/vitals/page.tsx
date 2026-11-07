'use client';

import React, { useState } from 'react';
import { Activity, Plus, CheckCircle2, AlertCircle, Clock, Heart, Droplets } from 'lucide-react';
import { SYNTHETIC_METRICS } from '@/lib/data/synthetic-store';
import { HealthMetric } from '@/lib/types/healthcare';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function VitalsPage() {
  const [metrics, setMetrics] = useState<HealthMetric[]>(SYNTHETIC_METRICS);
  const [metricType, setMetricType] = useState<'blood_pressure' | 'heart_rate' | 'blood_glucose' | 'spo2'>('blood_pressure');
  const [val1, setVal1] = useState('');
  const [val2, setVal2] = useState('');
  const [notes, setNotes] = useState('');
  const [successMsg, setSuccessMsg] = useState(false);

  const handleAddMetric = (e: React.FormEvent) => {
    e.preventDefault();
    if (!val1) return;

    const newMetric: HealthMetric = {
      id: `met-${Date.now()}`,
      patient_id: 'pat-default',
      metric_type: metricType,
      value: parseFloat(val1),
      secondary_value: val2 ? parseFloat(val2) : undefined,
      unit: metricType === 'blood_pressure' ? 'mmHg' : metricType === 'heart_rate' ? 'bpm' : metricType === 'spo2' ? '%' : 'mg/dL',
      notes: notes || undefined,
      provenance: 'USER_REPORTED',
      recorded_at: new Date().toISOString(),
    };

    setMetrics([newMetric, ...metrics]);
    setVal1('');
    setVal2('');
    setNotes('');
    setSuccessMsg(true);
    setTimeout(() => setSuccessMsg(false), 4000);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Vitals & Health Biomarkers</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Track resting biomarkers against standardized clinical reference boundaries with verified source provenance.
          </p>
        </div>
      </div>

      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-semibold flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          <span>New health measurement successfully recorded and added to your Health Memory timeline.</span>
        </div>
      )}

      {/* Main Grid: Entry Form + History */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Entry Form */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Plus className="w-4 h-4 text-sky-600" />
            <span>Record New Measurement</span>
          </h2>

          <form onSubmit={handleAddMetric} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Metric Type</label>
              <select
                value={metricType}
                onChange={(e) => setMetricType(e.target.value as any)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                <option value="blood_pressure">Blood Pressure (Systolic / Diastolic)</option>
                <option value="heart_rate">Heart Rate (Pulse - bpm)</option>
                <option value="blood_glucose">Blood Glucose (Fasting / Post-prandial)</option>
                <option value="spo2">Oxygen Saturation (SpO2 %)</option>
              </select>
            </div>

            {metricType === 'blood_pressure' ? (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Systolic (mmHg)</label>
                  <input
                    type="number"
                    placeholder="e.g. 120"
                    value={val1}
                    onChange={(e) => setVal1(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Diastolic (mmHg)</label>
                  <input
                    type="number"
                    placeholder="e.g. 80"
                    value={val2}
                    onChange={(e) => setVal2(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </div>
            ) : (
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Value ({metricType === 'heart_rate' ? 'bpm' : metricType === 'spo2' ? '%' : 'mg/dL'})
                </label>
                <input
                  type="number"
                  placeholder="Enter reading value"
                  value={val1}
                  onChange={(e) => setVal1(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Clinical Context / Notes</label>
              <input
                type="text"
                placeholder="e.g. Morning fasting, after 10 min rest"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <button
              type="submit"
              className="w-full py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-semibold text-sm shadow-sm transition"
            >
              Save Vital Reading
            </button>
          </form>

          {/* Reference Boundaries Guidance */}
          <div className="pt-4 border-t border-slate-100 text-xs text-slate-500 space-y-1">
            <span className="font-semibold text-slate-700 block">Clinical Reference Thresholds:</span>
            <p>â€¢ <strong>BP:</strong> Normal &lt; 120/80 mmHg</p>
            <p>â€¢ <strong>Resting HR:</strong> 60â€“100 bpm</p>
            <p>â€¢ <strong>Fasting Glucose:</strong> 70â€“99 mg/dL</p>
            <p>â€¢ <strong>SpO2:</strong> 95â€“100% on room air</p>
          </div>
        </div>

        {/* History Stream */}
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Activity className="w-5 h-5 text-indigo-600" />
              <span>Recorded Vitals Stream ({metrics.length})</span>
            </h2>
          </div>

          <div className="space-y-3">
            {metrics.map((m) => (
              <div
                key={m.id}
                className="p-4 rounded-xl border border-slate-100 bg-slate-50 flex items-center justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-slate-900 capitalize">
                      {m.metric_type.replace('_', ' ')}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-slate-200 text-slate-700 font-semibold">
                      {m.provenance}
                    </span>
                  </div>
                  <div className="text-xs text-slate-600 font-medium">
                    {m.notes || 'No additional clinical remarks.'}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <Clock className="w-3.5 h-3.5" />
                    <span>{new Date(m.recorded_at).toLocaleDateString()} at {new Date(m.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-2xl font-black text-slate-900">
                    {m.value}{m.secondary_value ? `/${m.secondary_value}` : ''}
                    <span className="text-xs font-normal text-slate-500 ml-1">{m.unit}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
