import React from 'react';
import Link from 'next/link';
import { FileText, Download, Plus, ShieldCheck, Lock, Clock } from 'lucide-react';
import { SYNTHETIC_RECORDS } from '@/lib/data/synthetic-store';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function MedicalRecordsPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Medical Records & Clinical Documents</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Private, encrypted medical document repository. Access is strictly governed by Supabase RLS policies and temporary 5-minute signed URLs.
          </p>
        </div>

        <Link
          href="/records/upload"
          className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold shadow-sm transition flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          <span>Upload Document</span>
        </Link>
      </div>

      {/* Record Grid */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900">Encrypted Clinical Vault ({SYNTHETIC_RECORDS.length})</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {SYNTHETIC_RECORDS.map((rec) => (
            <div
              key={rec.id}
              className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm hover:shadow-md transition flex flex-col justify-between space-y-4"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold text-base text-slate-900">{rec.title}</h3>
                    <span className="text-xs font-semibold text-sky-700 uppercase">{rec.record_type}</span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-bold">
                    {(rec.file_size_bytes / 1024).toFixed(1)} KB
                  </span>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-xl border border-slate-100">
                  {rec.summary}
                </p>

                <div className="space-y-1 text-xs text-slate-500">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-700">Storage Path:</span>
                    <span className="font-mono text-slate-600 truncate">{rec.storage_path}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-700">SHA-256 Checksum:</span>
                    <span className="font-mono text-slate-400">{rec.sha256_hash.substring(0, 24)}...</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-700">Provenance:</span>
                    <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold font-mono">
                      {rec.provenance}
                    </span>
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs text-slate-400">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{new Date(rec.created_at).toLocaleDateString()}</span>
                </div>

                <button
                  type="button"
                  className="px-3.5 py-2 rounded-xl bg-sky-50 hover:bg-sky-100 text-sky-700 text-xs font-semibold transition flex items-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Generate Signed URL</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
