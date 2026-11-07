import React from 'react';
import Link from 'next/link';
import { Shield, Lock, Activity, Heart } from 'lucide-react';

export function Footer() {
  return (
    <footer className="bg-slate-900 text-slate-400 text-xs md:text-sm py-12 border-t border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          <div>
            <div className="flex items-center gap-2 text-white font-bold text-base mb-3">
              <Heart className="w-5 h-5 text-sky-400 fill-current" />
              <span>ZENDOC 2.0</span>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed">
              Unified healthcare coordination platform connecting patients, verified clinicians, and health organizations with safety-first AI advisory systems.
            </p>
          </div>

          <div>
            <h4 className="text-white font-semibold mb-3">Care & Discovery</h4>
            <ul className="space-y-2">
              <li><Link href="/find-care" className="hover:text-white transition">Find Doctors & Clinics</Link></li>
              <li><Link href="/appointments" className="hover:text-white transition">Book Appointments</Link></li>
              <li><Link href="/pharmacy" className="hover:text-white transition">Pharmacy Requests</Link></li>
              <li><Link href="/diagnostics" className="hover:text-white transition">Diagnostic Tests</Link></li>
              <li><Link href="/transport" className="hover:text-white transition">Patient Transport</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="text-white font-semibold mb-3">Health & Memory</h4>
            <ul className="space-y-2">
              <li><Link href="/memory" className="hover:text-white transition">Health Timeline</Link></li>
              <li><Link href="/vitals" className="hover:text-white transition">Vitals & Measurements</Link></li>
              <li><Link href="/records" className="hover:text-white transition">Medical Records</Link></li>
              <li><Link href="/trust-center" className="hover:text-white transition">Consent & Trust Center</Link></li>
              <li><Link href="/family" className="hover:text-white transition">Family & Dependent Care</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="text-white font-semibold mb-3">Security & Compliance</h4>
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2 text-slate-300">
                <Shield className="w-4 h-4 text-emerald-400" />
                <span>Supabase RLS Tenant Isolation</span>
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <Lock className="w-4 h-4 text-sky-400" />
                <span>Short-Lived Private Signed URLs</span>
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <Activity className="w-4 h-4 text-amber-400" />
                <span>Deterministic Emergency-First Triage</span>
              </div>
            </div>
          </div>
        </div>

        <div className="pt-6 border-t border-slate-800 flex flex-col md:flex-row items-center justify-between gap-4 text-xs">
          <p>Â© 2026 ZENDOC Platform. All rights reserved. Branch: <code>rebuild/zendoc-2.0-vercel</code></p>
          <p className="text-slate-400 max-w-xl text-center md:text-right">
            Medical Disclaimer: ZENDOC is an educational and coordination tool. It is not an autonomous diagnostic device. In acute emergency conditions, call 102/108/112 immediately.
          </p>
        </div>
      </div>
    </footer>
  );
}
