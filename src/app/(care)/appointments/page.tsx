import React from 'react';
import Link from 'next/link';
import { Calendar, Clock, Plus, Video, MapPin, CheckCircle, AlertCircle, Phone } from 'lucide-react';
import { SYNTHETIC_APPOINTMENTS } from '@/lib/data/synthetic-store';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function AppointmentsPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Appointments & Clinical Consultations</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Coordinate in-person clinic visits and encrypted browser telehealth consultations with verified medical providers.
          </p>
        </div>

        <Link
          href="/appointments/book"
          className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold shadow-sm transition flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          <span>Book New Appointment</span>
        </Link>
      </div>

      {/* Appointment Cards */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900">Your Consultations ({SYNTHETIC_APPOINTMENTS.length})</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {SYNTHETIC_APPOINTMENTS.map((apt) => (
            <div
              key={apt.id}
              className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm hover:shadow-md transition flex flex-col justify-between space-y-4"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold text-base text-slate-900">{apt.provider_name}</h3>
                    <p className="text-xs font-semibold text-sky-700">{apt.specialty}</p>
                  </div>
                  <span
                    className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider ${
                      apt.status === 'confirmed'
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {apt.status}
                  </span>
                </div>

                <div className="p-3 bg-slate-50 rounded-xl space-y-1.5 text-xs text-slate-600">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-slate-400" />
                    <span className="font-semibold text-slate-800">
                      {new Date(apt.scheduled_at).toLocaleDateString()} at {new Date(apt.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {apt.appointment_type === 'telehealth' ? (
                      <Video className="w-4 h-4 text-indigo-600" />
                    ) : (
                      <MapPin className="w-4 h-4 text-emerald-600" />
                    )}
                    <span className="capitalize font-medium">
                      {apt.appointment_type.replace('_', ' ')} Consultation
                    </span>
                  </div>
                </div>

                {apt.reason && (
                  <p className="text-xs text-slate-600">
                    <strong>Reason for visit:</strong> {apt.reason}
                  </p>
                )}
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
                {apt.appointment_type === 'telehealth' && apt.status === 'confirmed' ? (
                  <Link
                    href={`/messages?callRoom=${apt.id}`}
                    className="w-full py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold text-center transition flex items-center justify-center gap-1.5"
                  >
                    <Video className="w-4 h-4" />
                    <span>Enter Telehealth Consultation Room</span>
                  </Link>
                ) : (
                  <button
                    type="button"
                    className="w-full py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition"
                  >
                    View Appointment Details
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
