import React from 'react';
import { Users, Plus, ShieldCheck, Heart, User, Calendar, FileText } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

const FAMILY_MEMBERS = [
  {
    id: 'fam-1',
    name: 'Aarav Sharma',
    relationship: 'Son (Minor Dependent)',
    dob: '2020-04-12',
    blood_group: 'O+',
    records_count: 4,
    vaccination_status: 'Up to Date',
  },
  {
    id: 'fam-2',
    name: 'Kamala Sharma',
    relationship: 'Mother (Senior Dependent)',
    dob: '1952-09-18',
    blood_group: 'B+',
    records_count: 12,
    chronic_conditions: ['Type 2 Diabetes', 'Osteoarthritis'],
  },
];

export default function FamilyCarePage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Family & Dependent Care Circle</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Manage authorized surrogate health access for children, spouses, and elderly parents under auditable guardian consent.
          </p>
        </div>

        <button
          type="button"
          className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold shadow-sm transition flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          <span>Add Dependent</span>
        </button>
      </div>

      {/* Dependents Grid */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900">Registered Dependents ({FAMILY_MEMBERS.length})</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {FAMILY_MEMBERS.map((dep) => (
            <div
              key={dep.id}
              className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold text-base text-slate-900">{dep.name}</h3>
                  <span className="text-xs font-semibold text-sky-700">{dep.relationship}</span>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                  Guardian Proxy Active
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-xl text-xs text-slate-600">
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">Date of Birth</span>
                  <span className="font-semibold text-slate-800">{dep.dob}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">Blood Group</span>
                  <span className="font-semibold text-slate-800">{dep.blood_group}</span>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100">
                <span className="text-slate-500">{dep.records_count} Clinical Documents</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="px-3 py-1.5 rounded-lg bg-sky-50 text-sky-700 font-semibold hover:bg-sky-100 transition"
                  >
                    View Timeline
                  </button>
                  <button
                    type="button"
                    className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 font-semibold hover:bg-slate-200 transition"
                  >
                    Permissions
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
