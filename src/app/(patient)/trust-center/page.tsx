'use client';

import React, { useState } from 'react';
import { ShieldCheck, ShieldAlert, Lock, UserCheck, Eye, Trash2, Clock, CheckCircle } from 'lucide-react';
import { SYNTHETIC_CONSENTS } from '@/lib/data/synthetic-store';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function TrustCenterPage() {
  const [consents, setConsents] = useState(SYNTHETIC_CONSENTS);
  const [message, setMessage] = useState<string | null>(null);

  const handleRevoke = (id: string, name: string) => {
    setConsents((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: 'REVOKED' } : c))
    );
    setMessage(`Consent for ${name} was immediately revoked. Ongoing data access has been terminated.`);
    setTimeout(() => setMessage(null), 6000);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Privacy, Consent & Trust Center</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Auditable consent governance. You hold complete ownership of your health records with granular, time-bounded, and instantly revocable access.
          </p>
        </div>
      </div>

      {/* Revocation Alert Message */}
      {message && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-semibold flex items-center gap-2">
          <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0" />
          <span>{message}</span>
        </div>
      )}

      {/* Active Consent Grants */}
      <section className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-6">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <UserCheck className="w-5 h-5 text-emerald-600" />
              <span>Active & Historical Consent Grants</span>
            </h2>
            <p className="text-xs text-slate-500">Clinicians, caregivers, and services authorized to access your health data.</p>
          </div>
        </div>

        <div className="space-y-4">
          {consents.map((grant) => (
            <div
              key={grant.id}
              className="p-5 rounded-xl border border-slate-200 bg-slate-50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
            >
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-slate-900 text-sm">{grant.grantee_name}</span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                      grant.status === 'ACTIVE'
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {grant.status}
                  </span>
                </div>
                <div className="text-xs text-slate-600 space-y-0.5">
                  <p><strong>Purpose:</strong> {grant.purpose.replace('_', ' ')}</p>
                  <p><strong>Permitted Scope:</strong> {grant.scope.replace('_', ' ')}</p>
                  <p className="text-slate-400"><strong>Valid Until:</strong> {new Date(grant.valid_until).toLocaleDateString()}</p>
                </div>
              </div>

              {grant.status === 'ACTIVE' && (
                <button
                  type="button"
                  onClick={() => handleRevoke(grant.id, grant.grantee_name || 'Provider')}
                  className="px-3.5 py-2 rounded-xl bg-red-50 hover:bg-red-100 border border-red-200 text-red-700 text-xs font-semibold transition flex items-center gap-1.5"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Revoke Consent Immediately</span>
                </button>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Immutable Audit Log Inspection */}
      <section className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <Lock className="w-5 h-5 text-sky-600" />
            <span>Health Record Access Provenance & Audit Ledger</span>
          </h2>
          <p className="text-xs text-slate-500">Immutable ledger recording every read and update event regarding your medical file.</p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 uppercase font-semibold border-y border-slate-200">
              <tr>
                <th className="py-2.5 px-3">Timestamp</th>
                <th className="py-2.5 px-3">Actor</th>
                <th className="py-2.5 px-3">Action</th>
                <th className="py-2.5 px-3">Resource</th>
                <th className="py-2.5 px-3">Authorization Basis</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              <tr>
                <td className="py-2.5 px-3 font-mono text-slate-400">2026-11-06 08:00 UTC</td>
                <td className="py-2.5 px-3 font-semibold">Rahul Sharma (You)</td>
                <td className="py-2.5 px-3 font-mono text-sky-700">INSERT_VITALS</td>
                <td className="py-2.5 px-3">Blood Pressure (120/80)</td>
                <td className="py-2.5 px-3">Owner Session (auth.uid)</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-mono text-slate-400">2026-10-15 09:30 UTC</td>
                <td className="py-2.5 px-3 font-semibold">Diagnostic Lab Bridge</td>
                <td className="py-2.5 px-3 font-mono text-indigo-700">UPLOAD_REPORT</td>
                <td className="py-2.5 px-3">Lipid Profile PDF (rec-101)</td>
                <td className="py-2.5 px-3">Signed Booking Token</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-mono text-slate-400">2026-10-10 14:15 UTC</td>
                <td className="py-2.5 px-3 font-semibold">Dr. Debabrata Sen</td>
                <td className="py-2.5 px-3 font-mono text-emerald-700">VIEW_RECORD</td>
                <td className="py-2.5 px-3">Full Health Memory</td>
                <td className="py-2.5 px-3">Consent Grant <code>cst-001</code></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
