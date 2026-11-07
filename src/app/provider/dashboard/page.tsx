import React from 'react';
import Link from 'next/link';
import { Stethoscope, Calendar, Clock, User, CheckCircle2, Video, BedDouble, ShieldCheck } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function ProviderDashboard() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Provider Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Dr. Debabrata Sen â€” Clinician Portal</h1>
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">Verified Specialist</span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Registration: <code>WBMC-54219</code> â€¢ Specialty: Cardiology â€¢ Facility: Kolkata Apex Multispeciality Hospital
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/provider/beds"
            className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition flex items-center gap-1.5"
          >
            <BedDouble className="w-4 h-4 text-slate-600" />
            <span>Ward & Bed Board</span>
          </Link>
        </div>
      </div>

      {/* Consultations Queue */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
          <Calendar className="w-5 h-5 text-sky-600" />
          <span>Todayâ€™s Scheduled Patient Consultations (2)</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-bold text-base text-slate-900">Rahul Sharma</h3>
                <p className="text-xs text-slate-500">Age 38 â€¢ Blood Pressure Follow-up</p>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 uppercase">
                Consent Active
              </span>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl text-xs space-y-1 text-slate-600">
              <p><strong>Scheduled Slot:</strong> Today, 10:00 AM (In-Person)</p>
              <p><strong>Recent Vitals:</strong> BP 120/80 mmHg, HR 72 bpm</p>
              <p><strong>Lab Report:</strong> Lipid Profile uploaded on 15 Oct 2026</p>
            </div>

            <div className="flex gap-2 pt-2 border-t border-slate-100">
              <Link
                href="/messages"
                className="flex-1 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold text-center transition"
              >
                Open Clinical Encounter
              </Link>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-bold text-base text-slate-900">Priya Sengupta</h3>
                <p className="text-xs text-slate-500">Age 45 â€¢ Palpitation Review</p>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 uppercase">
                Consent Active
              </span>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl text-xs space-y-1 text-slate-600">
              <p><strong>Scheduled Slot:</strong> Today, 11:30 AM (Telehealth Video)</p>
              <p><strong>Recent Vitals:</strong> BP 128/84 mmHg, HR 88 bpm</p>
              <p><strong>ECG:</strong> Sinus Tachycardia noted on 2 Nov 2026</p>
            </div>

            <div className="flex gap-2 pt-2 border-t border-slate-100">
              <Link
                href="/messages"
                className="flex-1 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold text-center transition flex items-center justify-center gap-1.5"
              >
                <Video className="w-3.5 h-3.5" />
                <span>Join Telehealth Session</span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
