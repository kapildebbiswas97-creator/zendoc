import React from 'react';
import Link from 'next/link';
import { FileText, Activity, Calendar, ShieldCheck, Download, Plus, Clock } from 'lucide-react';
import { SYNTHETIC_RECORDS, SYNTHETIC_METRICS, SYNTHETIC_APPOINTMENTS } from '@/lib/data/synthetic-store';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function HealthMemoryPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Health Memory & Longitudinal Timeline</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Chronological, immutable record of personal medical events, clinical documents, and device-ingested biomarkers with complete data provenance.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/records/upload"
            className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold shadow-sm transition flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            <span>Upload Document</span>
          </Link>
        </div>
      </div>

      {/* Timeline Stream */}
      <div className="space-y-6">
        <h2 className="text-lg font-bold text-slate-900">Longitudinal Timeline Feed</h2>

        <div className="relative border-l-2 border-slate-200 ml-4 pl-6 space-y-8">
          {/* Event 1: Blood Pressure */}
          <div className="relative group">
            <div className="absolute -left-[35px] top-1.5 w-5 h-5 rounded-full bg-rose-500 border-4 border-white shadow-sm" />
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-rose-600 flex items-center gap-1.5">
                  <Activity className="w-4 h-4" />
                  <span>Vitals Measurement</span>
                </span>
                <span className="text-xs text-slate-400">6 November 2026, 08:00 AM</span>
              </div>
              <h3 className="font-bold text-base text-slate-900">Blood Pressure: 120/80 mmHg â€¢ Heart Rate: 72 bpm</h3>
              <p className="text-xs text-slate-600">Resting morning reading. Logged via verified patient home cuff.</p>
              <div className="flex items-center gap-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">
                <span className="font-semibold text-slate-700">Provenance:</span>
                <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-mono">USER_REPORTED</span>
                <span>â€¢</span>
                <span>Cryptographic ID: <code>met-001</code></span>
              </div>
            </div>
          </div>

          {/* Event 2: Lab Report */}
          <div className="relative group">
            <div className="absolute -left-[35px] top-1.5 w-5 h-5 rounded-full bg-sky-500 border-4 border-white shadow-sm" />
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-sky-600 flex items-center gap-1.5">
                  <FileText className="w-4 h-4" />
                  <span>Diagnostic Lab Report</span>
                </span>
                <span className="text-xs text-slate-400">15 October 2026, 09:30 AM</span>
              </div>
              <h3 className="font-bold text-base text-slate-900">Comprehensive Lipid Profile & Liver Panel</h3>
              <p className="text-xs text-slate-600">
                Total Cholesterol: 185 mg/dL. Triglycerides: 140 mg/dL. HDL: 48 mg/dL. All metabolic parameters within normal reference ranges.
              </p>
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-700">Provenance:</span>
                  <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-mono">DOCUMENT_EXTRACTED</span>
                  <span>â€¢</span>
                  <span className="font-mono">SHA256: e3b0c44298fc1c...</span>
                </div>
                <button
                  type="button"
                  className="text-xs font-semibold text-sky-600 hover:text-sky-700 flex items-center gap-1"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Request Signed Download URL</span>
                </button>
              </div>
            </div>
          </div>

          {/* Event 3: Clinical Consultation */}
          <div className="relative group">
            <div className="absolute -left-[35px] top-1.5 w-5 h-5 rounded-full bg-indigo-500 border-4 border-white shadow-sm" />
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 flex items-center gap-1.5">
                  <Calendar className="w-4 h-4" />
                  <span>Clinical Encounter Note</span>
                </span>
                <span className="text-xs text-slate-400">10 October 2026, 02:15 PM</span>
              </div>
              <h3 className="font-bold text-base text-slate-900">Consultation Summary â€” Dr. Debabrata Sen (Cardiologist)</h3>
              <p className="text-xs text-slate-600">
                Routine cardiovascular follow-up. Resting 12-lead ECG normal. Patient advised to maintain daily aerobic activity and annual lipid screening.
              </p>
              <div className="flex items-center gap-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">
                <span className="font-semibold text-slate-700">Provenance:</span>
                <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-mono">PROVIDER_RECORDED</span>
                <span>â€¢</span>
                <span>Doctor Registration: <code>WBMC-54219</code></span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
