'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Calendar, Clock, Video, MapPin, CheckCircle2, ArrowLeft } from 'lucide-react';
import { SYNTHETIC_PROVIDERS } from '@/lib/data/synthetic-store';

export default function BookAppointmentPage() {
  const router = useRouter();
  const [providerId, setProviderId] = useState(SYNTHETIC_PROVIDERS[0].id);
  const [aptType, setAptType] = useState<'in_person' | 'telehealth'>('in_person');
  const [date, setDate] = useState('2026-11-20');
  const [timeSlot, setTimeSlot] = useState('11:00 AM');
  const [reason, setReason] = useState('');
  const [booked, setBooked] = useState(false);

  const selectedProvider = SYNTHETIC_PROVIDERS.find((p) => p.id === providerId) || SYNTHETIC_PROVIDERS[0];

  const handleBook = (e: React.FormEvent) => {
    e.preventDefault();
    setBooked(true);
    setTimeout(() => {
      router.push('/appointments');
    }, 2000);
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Link
        href="/appointments"
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to Appointments</span>
      </Link>

      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-6">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Book Clinical Consultation</h1>
          <p className="text-xs text-slate-500 mt-1">Select your preferred clinician, consultation mode, and scheduled slot.</p>
        </div>

        {booked ? (
          <div className="p-6 bg-emerald-50 border border-emerald-200 rounded-xl text-center space-y-3">
            <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto" />
            <h3 className="font-bold text-base text-emerald-950">Appointment Requested Successfully!</h3>
            <p className="text-xs text-emerald-800">
              Your request with {selectedProvider.full_name} for {date} at {timeSlot} has been submitted. Redirecting to your consultations list...
            </p>
          </div>
        ) : (
          <form onSubmit={handleBook} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Select Clinician</label>
              <select
                value={providerId}
                onChange={(e) => setProviderId(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                {SYNTHETIC_PROVIDERS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.full_name} ({p.specialty} â€” â‚¹{p.consultation_fee})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Consultation Mode</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setAptType('in_person')}
                  className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition ${
                    aptType === 'in_person'
                      ? 'border-sky-600 bg-sky-50 text-sky-700'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <MapPin className="w-4 h-4" />
                  <span>In-Person Clinic Visit</span>
                </button>

                <button
                  type="button"
                  onClick={() => setAptType('telehealth')}
                  className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition ${
                    aptType === 'telehealth'
                      ? 'border-indigo-600 bg-indigo-50 text-indigo-700'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <Video className="w-4 h-4" />
                  <span>Telehealth Video Call</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Date</label>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Time Slot</label>
                <select
                  value={timeSlot}
                  onChange={(e) => setTimeSlot(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="09:30 AM">09:30 AM</option>
                  <option value="11:00 AM">11:00 AM</option>
                  <option value="02:30 PM">02:30 PM</option>
                  <option value="04:00 PM">04:00 PM</option>
                  <option value="06:30 PM">06:30 PM</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Chief Complaint / Reason for Consultation</label>
              <textarea
                placeholder="Briefly describe your symptoms or reason for this consultation..."
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                required
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div className="p-4 bg-slate-50 rounded-xl space-y-1 text-xs text-slate-600">
              <div className="flex justify-between">
                <span>Clinician Fee:</span>
                <span className="font-bold text-slate-900">â‚¹{selectedProvider.consultation_fee}</span>
              </div>
              <div className="flex justify-between">
                <span>Facility:</span>
                <span>{selectedProvider.facility_name}</span>
              </div>
              <p className="text-[10px] text-slate-400 pt-1">
                Notice: Slot reservations are confirmed based on real doctor availability. No payment is charged until confirmed.
              </p>
            </div>

            <button
              type="submit"
              className="w-full py-3 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-semibold text-sm shadow-sm transition"
            >
              Confirm Consultation Request
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
