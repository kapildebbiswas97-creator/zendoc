import React from 'react';
import Link from 'next/link';
import { Lock, ArrowLeft, ShieldCheck, Filter } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

const AUDIT_ENTRIES = [
  { id: 'aud-1', time: '2026-11-06 08:00:14 UTC', actor: 'Rahul Sharma (pat-default)', target: 'Rahul Sharma', action: 'INSERT_VITALS', resource: 'health_metrics (met-001)', scope: 'OWNER_SESSION', ip: '103.21.244.xxx' },
  { id: 'aud-2', time: '2026-10-15 09:30:22 UTC', actor: 'South Kolkata Diag System', target: 'Rahul Sharma', action: 'UPLOAD_RECORD', resource: 'medical_records (rec-101)', scope: 'DIAGNOSTIC_TOKEN', ip: '182.74.88.xxx' },
  { id: 'aud-3', time: '2026-10-10 14:15:05 UTC', actor: 'Dr. Debabrata Sen (doc-001)', target: 'Rahul Sharma', action: 'VIEW_PATIENT_RECORD', resource: 'medical_records (ALL)', scope: 'CONSENT_GRANT_cst-001', ip: '115.240.90.xxx' },
  { id: 'aud-4', time: '2026-10-10 14:00:00 UTC', actor: 'Rahul Sharma (pat-default)', target: 'Dr. Debabrata Sen', action: 'GRANT_CONSENT', resource: 'consent_grants (cst-001)', scope: 'OWNER_SESSION', ip: '103.21.244.xxx' },
  { id: 'aud-5', time: '2026-10-08 11:22:45 UTC', actor: 'ZENDOC AI Safety Engine', target: 'Anonymous User', action: 'EMERGENCY_DIVERSION_TRIGGERED', resource: 'ai_triage (RED_FLAG)', scope: 'DETERMINISTIC_GATE', ip: '49.36.120.xxx' },
];

export default function GlobalAuditPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <Link
        href="/admin/overview"
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to Admin Overview</span>
      </Link>

      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Immutable Global Audit Log</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Tamper-evident audit ledger tracking all clinical reads, writes, consent grants, and emergency escalations.
          </p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 uppercase font-semibold border-y border-slate-200">
              <tr>
                <th className="py-2.5 px-3">Audit ID</th>
                <th className="py-2.5 px-3">Timestamp (UTC)</th>
                <th className="py-2.5 px-3">Actor Identity</th>
                <th className="py-2.5 px-3">Target Patient</th>
                <th className="py-2.5 px-3">Action Type</th>
                <th className="py-2.5 px-3">Target Resource</th>
                <th className="py-2.5 px-3">Authorization Scope</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {AUDIT_ENTRIES.map((entry) => (
                <tr key={entry.id}>
                  <td className="py-2.5 px-3 font-mono text-slate-400">{entry.id}</td>
                  <td className="py-2.5 px-3 font-mono text-slate-500">{entry.time}</td>
                  <td className="py-2.5 px-3 font-semibold text-slate-900">{entry.actor}</td>
                  <td className="py-2.5 px-3">{entry.target}</td>
                  <td className="py-2.5 px-3 font-mono font-bold text-sky-700">{entry.action}</td>
                  <td className="py-2.5 px-3 text-slate-600">{entry.resource}</td>
                  <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500">{entry.scope}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
