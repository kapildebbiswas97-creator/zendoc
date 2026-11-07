'use client';

import React, { useState } from 'react';
import { BedDouble, CheckCircle2, Clock, AlertTriangle, ShieldCheck, RefreshCw } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

interface Bed {
  id: string;
  ward: string;
  number: string;
  type: 'general' | 'icu' | 'hdu';
  status: 'available' | 'occupied' | 'cleaning';
}

const INITIAL_BEDS: Bed[] = [
  { id: 'b1', ward: 'Cardiology Ward 3A', number: 'Bed 301', type: 'general', status: 'available' },
  { id: 'b2', ward: 'Cardiology Ward 3A', number: 'Bed 302', type: 'general', status: 'occupied' },
  { id: 'b3', ward: 'Coronary Care Unit (CCU)', number: 'CCU-01', type: 'icu', status: 'occupied' },
  { id: 'b4', ward: 'Coronary Care Unit (CCU)', number: 'CCU-02', type: 'icu', status: 'available' },
  { id: 'b5', ward: 'Step-Down HDU', number: 'HDU-04', type: 'hdu', status: 'cleaning' },
];

export default function HospitalBedsPage() {
  const [beds, setBeds] = useState<Bed[]>(INITIAL_BEDS);

  const toggleStatus = (id: string) => {
    setBeds((prev) =>
      prev.map((b) => {
        if (b.id !== id) return b;
        const nextStatus = b.status === 'available' ? 'occupied' : b.status === 'occupied' ? 'cleaning' : 'available';
        return { ...b, status: nextStatus };
      })
    );
  };

  const availableCount = beds.filter((b) => b.status === 'available').length;
  const occupiedCount = beds.filter((b) => b.status === 'occupied').length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Hospital IPD Ward & Bed Board</h1>
            <TruthStatusBadge status="BETA" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Real-time internal census tracking bed occupancy, cleaning cycles, and ICU availability for Kolkata Apex Multispeciality Hospital.
          </p>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold uppercase text-slate-500">Total Census Beds</span>
          <div className="text-2xl font-black text-slate-900">{beds.length}</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold uppercase text-emerald-600">Available Beds</span>
          <div className="text-2xl font-black text-emerald-600">{availableCount}</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold uppercase text-slate-700">Occupied Beds</span>
          <div className="text-2xl font-black text-slate-900">{occupiedCount}</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold uppercase text-amber-600">Cleaning / Turnover</span>
          <div className="text-2xl font-black text-amber-600">
            {beds.filter((b) => b.status === 'cleaning').length}
          </div>
        </div>
      </div>

      {/* Bed Grid */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <h2 className="text-base font-bold text-slate-900">Bed Allocation Matrix</h2>
          <span className="text-xs text-slate-400">Click a bed card to cycle status</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {beds.map((bed) => {
            const isAvail = bed.status === 'available';
            const isOcc = bed.status === 'occupied';
            return (
              <div
                key={bed.id}
                onClick={() => toggleStatus(bed.id)}
                className={`p-4 rounded-xl border cursor-pointer select-none transition space-y-3 ${
                  isAvail
                    ? 'border-emerald-300 bg-emerald-50/50 hover:bg-emerald-50'
                    : isOcc
                    ? 'border-slate-300 bg-slate-50 hover:bg-slate-100'
                    : 'border-amber-300 bg-amber-50/50 hover:bg-amber-50'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold text-sm text-slate-900">{bed.number}</h3>
                    <p className="text-xs text-slate-500">{bed.ward}</p>
                  </div>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                      isAvail
                        ? 'bg-emerald-100 text-emerald-800'
                        : isOcc
                        ? 'bg-slate-200 text-slate-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {bed.status}
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-200/50 text-slate-600">
                  <span className="font-semibold uppercase tracking-wider text-[10px]">{bed.type} Unit</span>
                  <span className="text-[10px] text-slate-400">Tap to toggle</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
