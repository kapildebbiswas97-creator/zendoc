import React from 'react';
import Link from 'next/link';
import { 
  Heart, 
  Search, 
  Calendar, 
  FileText, 
  Bot, 
  ShieldCheck, 
  Activity, 
  Clock, 
  ArrowRight,
  Shield,
  Layers,
  Sparkles
} from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function HomePage() {
  return (
    <div className="space-y-16 pb-20">
      {/* Hero Section */}
      <section className="relative overflow-hidden bg-gradient-to-b from-sky-50/60 via-white to-slate-50 border-b border-slate-200 py-16 lg:py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto space-y-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-sky-100 border border-sky-200 text-sky-800 text-xs font-semibold">
              <Sparkles className="w-3.5 h-3.5 text-sky-600" />
              <span>ZENDOC 2.0 Production Rebuild</span>
              <span className="text-sky-400">â€¢</span>
              <span>Next.js + Supabase</span>
            </div>

            <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 tracking-tight leading-tight">
              AI-Powered Healthcare Coordination. <br className="hidden sm:inline" />
              <span className="text-sky-600">Grounded in Safety and Provenance.</span>
            </h1>

            <p className="text-base sm:text-lg text-slate-600 leading-relaxed">
              ZENDOC coordinates care across patients, families, and verified clinicians. 
              Manage longitudinal health memory, book verified care, and access safety-gated AI guidance without compromising privacy.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
              <Link
                href="/dashboard"
                className="px-6 py-3 rounded-xl bg-sky-600 text-white font-semibold shadow-md hover:bg-sky-700 hover:shadow-lg transition flex items-center gap-2"
              >
                <span>Open Patient Dashboard</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/find-care"
                className="px-6 py-3 rounded-xl bg-white border border-slate-300 text-slate-800 font-semibold hover:bg-slate-50 transition flex items-center gap-2"
              >
                <Search className="w-4 h-4 text-slate-500" />
                <span>Find Providers & Clinics</span>
              </Link>
              <Link
                href="/ai"
                className="px-6 py-3 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-700 font-semibold hover:bg-indigo-100 transition flex items-center gap-2"
              >
                <Bot className="w-4 h-4 text-indigo-600" />
                <span>ZENDOC AI Advisor</span>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Target Architecture Highlights */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 shadow-sm">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-6 border-b border-slate-100 gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Layers className="w-5 h-5 text-sky-600" />
                <h2 className="text-xl font-bold text-slate-900">ZENDOC 2.0 Target Architecture</h2>
              </div>
              <p className="text-sm text-slate-500">
                Full-stack Next.js App Router on Vercel with native Supabase PostgreSQL, Auth, and Storage.
              </p>
            </div>
            <TruthStatusBadge status="WORKING" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 pt-6">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 space-y-2">
              <div className="w-8 h-8 rounded-lg bg-sky-100 text-sky-700 flex items-center justify-center font-bold">1</div>
              <h3 className="font-semibold text-slate-900 text-sm">Next.js App Router</h3>
              <p className="text-xs text-slate-600">TypeScript strict mode, React Server Components, zero reverse-proxy gateway bottlenecks.</p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 space-y-2">
              <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold">2</div>
              <h3 className="font-semibold text-slate-900 text-sm">Supabase PostgreSQL</h3>
              <p className="text-xs text-slate-600">169 normalized relational tables with Row Level Security (RLS) enforcing strict tenant and consent boundaries.</p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 space-y-2">
              <div className="w-8 h-8 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center font-bold">3</div>
              <h3 className="font-semibold text-slate-900 text-sm">Deterministic Safety Gate</h3>
              <p className="text-xs text-slate-600">Emergency red-flag symptom diversion precedes all AI inference. Autonomous prescribing strictly disabled.</p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 space-y-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold">4</div>
              <h3 className="font-semibold text-slate-900 text-sm">Zero AWS / OCI Lock-in</h3>
              <p className="text-xs text-slate-600">Complete retirement of EC2/OCI origin servers, Caddy proxies, and legacy boto3 wrappers in favor of modern cloud native services.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Core Platform Modules */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Production Healthcare Modules</h2>
          <p className="text-sm text-slate-500 mt-1">Directly accessible workflows preserving all core capabilities.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Card 1: Health Memory */}
          <Link
            href="/memory"
            className="group p-6 rounded-2xl bg-white border border-slate-200 hover:border-sky-300 hover:shadow-md transition space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-sky-100 text-sky-700 flex items-center justify-center group-hover:scale-105 transition">
              <FileText className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-900 group-hover:text-sky-600 transition flex items-center justify-between">
              <span>Health Memory & Timeline</span>
              <TruthStatusBadge status="WORKING" showIcon={false} />
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Longitudinal chronological health history tracking vitals, laboratory tests, clinical notes, and medication timelines with strict provenance tags.
            </p>
          </Link>

          {/* Card 2: Discovery */}
          <Link
            href="/find-care"
            className="group p-6 rounded-2xl bg-white border border-slate-200 hover:border-sky-300 hover:shadow-md transition space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center group-hover:scale-105 transition">
              <Search className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-900 group-hover:text-emerald-600 transition flex items-center justify-between">
              <span>Provider & Clinic Finder</span>
              <TruthStatusBadge status="WORKING" showIcon={false} />
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Discover verified clinicians, diagnostic centers, and hospitals. Grounded in official registry data without fabricated ratings or artificial slots.
            </p>
          </Link>

          {/* Card 3: Care Coordination */}
          <Link
            href="/appointments"
            className="group p-6 rounded-2xl bg-white border border-slate-200 hover:border-sky-300 hover:shadow-md transition space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center group-hover:scale-105 transition">
              <Calendar className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-900 group-hover:text-indigo-600 transition flex items-center justify-between">
              <span>Care & Appointments</span>
              <TruthStatusBadge status="WORKING" showIcon={false} />
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Coordinate in-person visits, telehealth video consultations, home health care, and non-emergency medical transport requests.
            </p>
          </Link>

          {/* Card 4: ZENDOC AI */}
          <Link
            href="/ai"
            className="group p-6 rounded-2xl bg-white border border-slate-200 hover:border-sky-300 hover:shadow-md transition space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-purple-100 text-purple-700 flex items-center justify-center group-hover:scale-105 transition">
              <Bot className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-900 group-hover:text-purple-600 transition flex items-center justify-between">
              <span>ZENDOC AI Advisory</span>
              <TruthStatusBadge status="WORKING" showIcon={false} />
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Curated medical knowledge retrieval and educational guidance with deterministic triage and human-in-the-loop plan confirmation.
            </p>
          </Link>

          {/* Card 5: Trust Center */}
          <Link
            href="/trust-center"
            className="group p-6 rounded-2xl bg-white border border-slate-200 hover:border-sky-300 hover:shadow-md transition space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center group-hover:scale-105 transition">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-900 group-hover:text-amber-600 transition flex items-center justify-between">
              <span>Consent & Trust Center</span>
              <TruthStatusBadge status="WORKING" showIcon={false} />
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Review active consent grants, inspect data access audit logs, manage family caregiver permissions, and execute instant consent revocations.
            </p>
          </Link>

          {/* Card 6: Vitals & IoT */}
          <Link
            href="/vitals"
            className="group p-6 rounded-2xl bg-white border border-slate-200 hover:border-sky-300 hover:shadow-md transition space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-rose-100 text-rose-700 flex items-center justify-center group-hover:scale-105 transition">
              <Activity className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-900 group-hover:text-rose-600 transition flex items-center justify-between">
              <span>Vitals & Biomarkers</span>
              <TruthStatusBadge status="WORKING" showIcon={false} />
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Record blood pressure, glucose, heart rate, and SpO2 with clinical reference boundaries and device ingestion provenance.
            </p>
          </Link>
        </div>
      </section>
    </div>
  );
}
