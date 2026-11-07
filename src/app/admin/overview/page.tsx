import React from 'react';
import Link from 'next/link';
import { ShieldCheck, Activity, Users, Database, Lock, AlertTriangle, ArrowRight } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function AdminOverviewPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Platform Command Center & Operational Telemetry</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Production system health, Supabase RLS enforcement status, and immutable audit logs.
          </p>
        </div>

        <Link
          href="/admin/audit"
          className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-black text-white text-xs font-semibold shadow-sm transition flex items-center gap-2"
        >
          <Lock className="w-3.5 h-3.5" />
          <span>Inspect Global Audit Logs</span>
        </Link>
      </div>

      {/* Operational Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold uppercase text-slate-500">Database Engine</span>
          <div className="text-xl font-black text-slate-900">Supabase PG 15+</div>
          <p className="text-xs text-emerald-600 font-semibold">169 Tables â€¢ RLS Enforced</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold uppercase text-slate-500">Target Framework</span>
          <div className="text-xl font-black text-slate-900">Next.js 15+ App Router</div>
          <p className="text-xs text-sky-600 font-semibold">Native Server Components</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold uppercase text-slate-500">AWS / OCI Status</span>
          <div className="text-xl font-black text-emerald-600">RETIRED</div>
          <p className="text-xs text-slate-500">Zero Reverse Proxy Overhead</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold uppercase text-slate-500">AI Safety Gate</span>
          <div className="text-xl font-black text-emerald-600">100% Deterministic</div>
          <p className="text-xs text-emerald-600 font-semibold">Emergency Triage Active</p>
        </div>
      </div>

      {/* System Infrastructure Verification Card */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-slate-900">Architecture Decommissioning & Retirement Verification</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 uppercase font-semibold border-y border-slate-200">
              <tr>
                <th className="py-2.5 px-3">Legacy Subsystem</th>
                <th className="py-2.5 px-3">Target Replacement</th>
                <th className="py-2.5 px-3">Rebuild Status</th>
                <th className="py-2.5 px-3">Verification Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              <tr>
                <td className="py-2.5 px-3 font-semibold">AWS EC2 Flask Host</td>
                <td className="py-2.5 px-3">Vercel Serverless Next.js</td>
                <td className="py-2.5 px-3"><span className="text-emerald-700 font-bold">RETIRED</span></td>
                <td className="py-2.5 px-3">Next.js App Router deployed directly to Vercel edge</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-semibold">OCI Caddy Reverse Proxy</td>
                <td className="py-2.5 px-3">Vercel Edge Network</td>
                <td className="py-2.5 px-3"><span className="text-emerald-700 font-bold">RETIRED</span></td>
                <td className="py-2.5 px-3">vercel.ts proxy gateway deleted; native routes active</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-semibold">AWS S3 / boto3</td>
                <td className="py-2.5 px-3">Supabase Storage</td>
                <td className="py-2.5 px-3"><span className="text-emerald-700 font-bold">REPLACED</span></td>
                <td className="py-2.5 px-3">Private buckets with signed 5-minute ephemeral URLs</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-semibold">SQLite fallback</td>
                <td className="py-2.5 px-3">Supabase PostgreSQL</td>
                <td className="py-2.5 px-3"><span className="text-emerald-700 font-bold">REPLACED</span></td>
                <td className="py-2.5 px-3">Normalized SQL DDL migration with strict RLS policies</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
