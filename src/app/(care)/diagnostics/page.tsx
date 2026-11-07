'use client';

import React, { useState } from 'react';
import { Activity, Plus, CheckCircle2, Clock, MapPin, Home, ShieldCheck } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

const DIAGNOSTIC_TESTS = [
  { id: 't1', code: 'CBC-01', name: 'Complete Blood Count (CBC) with ESR', category: 'Hematology', price: 350, turnaround: '12 Hours' },
  { id: 't2', code: 'LIPID-02', name: 'Comprehensive Lipid Profile', category: 'Biochemistry', price: 650, turnaround: '24 Hours' },
  { id: 't3', code: 'HBA1C-03', name: 'Glycated Hemoglobin (HbA1c)', category: 'Diabetology', price: 450, turnaround: '6 Hours' },
  { id: 't4', code: 'THYROID-04', name: 'Thyroid Function Panel (T3, T4, TSH)', category: 'Endocrinology', price: 550, turnaround: '24 Hours' },
  { id: 't5', code: 'LFT-05', name: 'Liver Function Test (LFT)', category: 'Biochemistry', price: 700, turnaround: '18 Hours' },
];

export default function DiagnosticsPage() {
  const [selectedTest, setSelectedTest] = useState(DIAGNOSTIC_TESTS[0].id);
  const [collectionType, setCollectionType] = useState<'home_collection' | 'lab_visit'>('home_collection');
  const [booked, setBooked] = useState(false);

  const testInfo = DIAGNOSTIC_TESTS.find(t => t.id === selectedTest) || DIAGNOSTIC_TESTS[0];

  const handleBook = (e: React.FormEvent) => {
    e.preventDefault();
    setBooked(true);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Diagnostic Laboratory Workflows</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Book certified pathology and radiology testing with automatic report extraction linked to your Health Memory.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Booking Form */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900">Schedule Diagnostic Investigation</h2>

          {booked ? (
            <div className="p-5 bg-emerald-50 border border-emerald-200 rounded-xl space-y-2 text-center">
              <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto" />
              <h3 className="font-bold text-xs text-emerald-950">Diagnostic Request Confirmed!</h3>
              <p className="text-[11px] text-emerald-800">
                A phlebotomist will arrive for sample collection on the requested date. Results will automatically sync to your medical vault.
              </p>
            </div>
          ) : (
            <form onSubmit={handleBook} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Select Diagnostic Investigation</label>
                <select
                  value={selectedTest}
                  onChange={(e) => setSelectedTest(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  {DIAGNOSTIC_TESTS.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} â€” â‚¹{t.price}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Collection Preference</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setCollectionType('home_collection')}
                    className={`p-2.5 rounded-xl border text-[11px] font-semibold flex items-center justify-center gap-1.5 transition ${
                      collectionType === 'home_collection'
                        ? 'border-sky-600 bg-sky-50 text-sky-700'
                        : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <Home className="w-3.5 h-3.5" />
                    <span>Home Collection</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setCollectionType('lab_visit')}
                    className={`p-2.5 rounded-xl border text-[11px] font-semibold flex items-center justify-center gap-1.5 transition ${
                      collectionType === 'lab_visit'
                        ? 'border-indigo-600 bg-indigo-50 text-indigo-700'
                        : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <MapPin className="w-3.5 h-3.5" />
                    <span>Lab Visit</span>
                  </button>
                </div>
              </div>

              <div className="p-3 bg-slate-50 rounded-xl space-y-1 text-slate-600">
                <div className="flex justify-between">
                  <span>Standard Price:</span>
                  <span className="font-bold text-slate-900">â‚¹{testInfo.price}</span>
                </div>
                <div className="flex justify-between">
                  <span>Turnaround Time:</span>
                  <span>{testInfo.turnaround}</span>
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs shadow-sm transition"
              >
                Schedule Diagnostic Test
              </button>
            </form>
          )}
        </div>

        {/* Catalog Table */}
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900">Standardized Pathology & Radiology Catalog</h2>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 uppercase font-semibold border-y border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Test Code</th>
                  <th className="py-2.5 px-3">Investigation Name</th>
                  <th className="py-2.5 px-3">Department</th>
                  <th className="py-2.5 px-3">Price</th>
                  <th className="py-2.5 px-3">Turnaround</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {DIAGNOSTIC_TESTS.map((t) => (
                  <tr key={t.id}>
                    <td className="py-2.5 px-3 font-mono text-slate-500">{t.code}</td>
                    <td className="py-2.5 px-3 font-semibold text-slate-900">{t.name}</td>
                    <td className="py-2.5 px-3">{t.category}</td>
                    <td className="py-2.5 px-3 font-bold text-slate-900">â‚¹{t.price}</td>
                    <td className="py-2.5 px-3 text-slate-500">{t.turnaround}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
