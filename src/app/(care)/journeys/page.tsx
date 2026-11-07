import React from 'react';
import { Calendar, CheckCircle2, Clock, Activity, ArrowRight, ShieldCheck } from 'lucide-react';
import { SYNTHETIC_CARE_JOURNEYS } from '@/lib/data/synthetic-store';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function CareJourneysPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Care Journeys & Episode Roadmaps</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Deterministic milestone-based longitudinal care journeys connecting patient adherence, follow-ups, and clinical outcomes.
          </p>
        </div>
      </div>

      {/* Journeys List */}
      <div className="space-y-6">
        {SYNTHETIC_CARE_JOURNEYS.map((journey) => (
          <div key={journey.id} className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900">{journey.journey_title}</h2>
                <span className="text-xs font-semibold text-sky-700">{journey.category}</span>
              </div>
              <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 uppercase w-fit">
                {journey.status}
              </span>
            </div>

            {/* Milestones Steps */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {journey.milestones?.map((m, idx) => (
                <div
                  key={m.id}
                  className={`p-4 rounded-xl border space-y-2 flex flex-col justify-between ${
                    m.is_completed
                      ? 'bg-emerald-50/60 border-emerald-200'
                      : idx === 2
                      ? 'bg-sky-50 border-sky-300 ring-2 ring-sky-500/20'
                      : 'bg-slate-50 border-slate-200 opacity-75'
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                        Step {idx + 1}
                      </span>
                      {m.is_completed ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      ) : (
                        <Clock className="w-4 h-4 text-sky-600" />
                      )}
                    </div>
                    <h3 className="font-bold text-xs text-slate-900">{m.name}</h3>
                  </div>

                  <div className="text-[10px] text-slate-500">
                    {m.is_completed ? (
                      <span className="text-emerald-700 font-semibold">Completed ({m.completed_at})</span>
                    ) : (
                      <span className="text-slate-600 font-medium">Due: {m.due_date}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
