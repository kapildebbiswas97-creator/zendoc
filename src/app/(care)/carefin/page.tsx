import React from 'react';
import { ShieldCheck, CheckCircle2, AlertCircle, FileText, IndianRupee, HelpCircle } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

const SCHEMES = [
  {
    id: 'pmjay',
    title: 'Ayushman Bharat PM-JAY',
    sponsor: 'National Health Authority (Government of India)',
    coverage: 'â‚¹5,00,000 per family/year',
    category: 'Secondary & Tertiary Inpatient Care',
    eligibility: 'SECC Database / Ration Card Holders',
    status: 'ELIGIBLE_NEEDS_VERIFICATION',
  },
  {
    id: 'wbhs',
    title: 'Swasthya Sathi / State Health Scheme',
    sponsor: 'Government of West Bengal',
    coverage: 'â‚¹5,00,000 per family/year',
    category: 'Cashless Secondary & Tertiary Hospitalization',
    eligibility: 'All Residents of West Bengal via Smart Card',
    status: 'ACTIVE_PROFILE_MATCH',
  },
  {
    id: 'cghs',
    title: 'Central Government Health Scheme (CGHS)',
    sponsor: 'Ministry of Health & Family Welfare',
    coverage: 'Comprehensive Outpatient & Inpatient Coverage',
    category: 'Central Employees & Pensioners',
    eligibility: 'Eligible Central Govt Beneficiaries',
    status: 'NOT_ENROLLED',
  },
];

export default function CareFinPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">CareFin â€” Health Financing & Scheme Discovery</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Deterministic matching of patient profiles against public health welfare programs and insurance policies.
          </p>
        </div>
      </div>

      {/* Truth Boundary Note */}
      <div className="p-4 rounded-xl bg-slate-100 border border-slate-300 text-slate-800 text-xs leading-relaxed space-y-1">
        <div className="flex items-center gap-2 font-bold text-slate-900">
          <ShieldCheck className="w-4 h-4 text-sky-600" />
          <span>Operational Boundary Specification</span>
        </div>
        <p>
          ZENDOC provides educational scheme eligibility discovery. Official cashless pre-authorization requires hospital TPA submission and government registry authentication.
        </p>
      </div>

      {/* Schemes Grid */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900">Discovered Health Benefit Schemes</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {SCHEMES.map((s) => (
            <div
              key={s.id}
              className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm hover:shadow-md transition flex flex-col justify-between space-y-4"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <h3 className="font-bold text-base text-slate-900">{s.title}</h3>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                      s.status === 'ACTIVE_PROFILE_MATCH'
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {s.status.replace(/_/g, ' ')}
                  </span>
                </div>

                <p className="text-xs text-sky-700 font-medium">{s.sponsor}</p>
                <div className="p-3 bg-slate-50 rounded-xl space-y-1 text-xs text-slate-600">
                  <div className="flex justify-between">
                    <span className="font-semibold text-slate-700">Annual Limit:</span>
                    <span className="font-bold text-slate-900">{s.coverage}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-semibold text-slate-700">Scope:</span>
                    <span className="text-slate-600">{s.category}</span>
                  </div>
                </div>

                <div className="text-xs text-slate-500">
                  <strong>Eligibility:</strong> {s.eligibility}
                </div>
              </div>

              <div className="pt-3 border-t border-slate-100">
                <button
                  type="button"
                  className="w-full py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition"
                >
                  View Required Documents
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
