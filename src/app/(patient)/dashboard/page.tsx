import React from 'react';
import Link from 'next/link';
import { 
  Heart, 
  Activity, 
  Calendar, 
  FileText, 
  ShieldCheck, 
  Bot, 
  ArrowRight, 
  Clock, 
  CheckCircle2, 
  AlertCircle 
} from 'lucide-react';
import { SYNTHETIC_METRICS, SYNTHETIC_APPOINTMENTS, SYNTHETIC_RECORDS, SYNTHETIC_CARE_JOURNEYS } from '@/lib/data/synthetic-store';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function PatientDashboard() {
  const latestBP = SYNTHETIC_METRICS.find(m => m.metric_type === 'blood_pressure');
  const latestHR = SYNTHETIC_METRICS.find(m => m.metric_type === 'heart_rate');
  const latestGlucose = SYNTHETIC_METRICS.find(m => m.metric_type === 'blood_glucose');
  const latestSpO2 = SYNTHETIC_METRICS.find(m => m.metric_type === 'spo2');

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Patient Header */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Welcome back, Rahul Sharma</h1>
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">Verified Patient</span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            ZENDOC ID: <code>ZEN-PAT-700098-992</code> â€¢ Primary Health Profile: Blood Group O+ â€¢ Age 38
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/vitals"
            className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-sm font-semibold transition"
          >
            Log New Vitals
          </Link>
          <Link
            href="/appointments/book"
            className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold shadow-sm transition"
          >
            Book Appointment
          </Link>
        </div>
      </div>

      {/* Vital Metrics Grid */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <Activity className="w-5 h-5 text-sky-600" />
            <span>Recent Health Vitals</span>
          </h2>
          <Link href="/vitals" className="text-sm font-semibold text-sky-600 hover:text-sky-700 flex items-center gap-1">
            <span>View All</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* BP */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-xs font-semibold uppercase text-slate-500">Blood Pressure</span>
            <div className="text-2xl font-black text-slate-900">
              {latestBP ? `${latestBP.value}/${latestBP.secondary_value}` : 'â€”'}
              <span className="text-xs font-normal text-slate-500 ml-1">mmHg</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Optimal Range</span>
            </div>
          </div>

          {/* Pulse */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-xs font-semibold uppercase text-slate-500">Heart Rate</span>
            <div className="text-2xl font-black text-slate-900">
              {latestHR ? latestHR.value : 'â€”'}
              <span className="text-xs font-normal text-slate-500 ml-1">bpm</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Normal Resting</span>
            </div>
          </div>

          {/* Glucose */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-xs font-semibold uppercase text-slate-500">Blood Glucose (Fasting)</span>
            <div className="text-2xl font-black text-slate-900">
              {latestGlucose ? latestGlucose.value : 'â€”'}
              <span className="text-xs font-normal text-slate-500 ml-1">mg/dL</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Normal Glycemia</span>
            </div>
          </div>

          {/* SpO2 */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-xs font-semibold uppercase text-slate-500">Oxygen Saturation</span>
            <div className="text-2xl font-black text-slate-900">
              {latestSpO2 ? latestSpO2.value : 'â€”'}
              <span className="text-xs font-normal text-slate-500 ml-1">%</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Room Air SpO2</span>
            </div>
          </div>
        </div>
      </section>

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Appointments & Care Journey */}
        <div className="lg:col-span-2 space-y-8">
          {/* Upcoming Appointments */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                <Calendar className="w-5 h-5 text-indigo-600" />
                <span>Upcoming Appointments</span>
              </h3>
              <Link href="/appointments" className="text-xs font-semibold text-indigo-600 hover:text-indigo-700">
                Manage
              </Link>
            </div>

            <div className="space-y-3">
              {SYNTHETIC_APPOINTMENTS.map((apt) => (
                <div key={apt.id} className="p-4 rounded-xl border border-slate-100 bg-slate-50 flex items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-slate-900">{apt.provider_name}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 capitalize font-medium">{apt.specialty}</span>
                    </div>
                    <p className="text-xs text-slate-600">{apt.reason}</p>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <Clock className="w-3.5 h-3.5" />
                      <span>{new Date(apt.scheduled_at).toLocaleDateString()} at {new Date(apt.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      <span className="capitalize font-semibold text-sky-700">({apt.appointment_type.replace('_', ' ')})</span>
                    </div>
                  </div>
                  <div>
                    <span className="text-xs font-bold uppercase px-2.5 py-1 rounded bg-sky-100 text-sky-800">
                      {apt.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Active Care Journey */}
          {SYNTHETIC_CARE_JOURNEYS.map((journey) => (
            <div key={journey.id} className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-slate-900 text-base">{journey.journey_title}</h3>
                  <p className="text-xs text-slate-500">{journey.category} â€¢ Milestone Tracker</p>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 uppercase">
                  {journey.status}
                </span>
              </div>

              <div className="space-y-3 pt-2">
                {journey.milestones?.map((m, idx) => (
                  <div key={m.id} className="flex items-center gap-3 text-xs">
                    <div className="w-6 h-6 rounded-full flex items-center justify-center font-bold shrink-0">
                      {m.is_completed ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                      ) : (
                        <div className="w-5 h-5 rounded-full border-2 border-slate-300 text-slate-400 flex items-center justify-center text-[10px]">
                          {idx + 1}
                        </div>
                      )}
                    </div>
                    <div className="flex-1">
                      <span className={m.is_completed ? 'line-through text-slate-400' : 'font-semibold text-slate-800'}>
                        {m.name}
                      </span>
                      {m.due_date && <span className="text-slate-400 ml-2">(Due: {m.due_date})</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Right Column: Health Memory Quick View & Trust Center */}
        <div className="space-y-8">
          {/* Recent Records */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                <FileText className="w-5 h-5 text-sky-600" />
                <span>Recent Documents</span>
              </h3>
              <Link href="/records" className="text-xs font-semibold text-sky-600 hover:text-sky-700">
                View All
              </Link>
            </div>

            <div className="space-y-3">
              {SYNTHETIC_RECORDS.map((rec) => (
                <div key={rec.id} className="p-3 rounded-xl border border-slate-100 bg-slate-50 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs text-slate-900 truncate max-w-[180px]">{rec.title}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 text-slate-600 font-medium">{rec.record_type}</span>
                  </div>
                  <p className="text-[11px] text-slate-500 line-clamp-2">{rec.summary}</p>
                  <div className="text-[10px] text-slate-400 font-mono">
                    SHA256: {rec.sha256_hash.substring(0, 12)}...
                  </div>
                </div>
              ))}
            </div>

            <Link
              href="/records/upload"
              className="block w-full py-2.5 rounded-xl border border-dashed border-sky-300 text-sky-700 text-center text-xs font-semibold hover:bg-sky-50 transition"
            >
              + Upload Medical Record (Private Signed Storage)
            </Link>
          </div>

          {/* Trust Center Glance */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              <h3 className="font-bold text-slate-900 text-base">Consent & Trust Status</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              You maintain 1 active clinical consent grant with Dr. Debabrata Sen. You may inspect or instantly revoke access in the Trust Center.
            </p>
            <Link
              href="/trust-center"
              className="block w-full text-center py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition"
            >
              Open Trust Center & Permissions
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
