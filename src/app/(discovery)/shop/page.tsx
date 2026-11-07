import React from 'react';
import { ShoppingBag, ExternalLink, ShieldCheck, CheckCircle2 } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

const SHOP_ITEMS = [
  {
    id: 'shp-1',
    title: 'Omron Upper Arm Digital Blood Pressure Monitor (HEM-7120)',
    category: 'Diagnostic Monitors',
    merchant: 'Apollo Pharmacy / Amazon India',
    description: 'Validated oscillometric home BP monitor with irregular heartbeat detection and cuff wrapping guide.',
    url: 'https://www.apollopharmacy.in',
  },
  {
    id: 'shp-2',
    title: 'Dr. Morepen Fingertip Pulse Oximeter (PO-09)',
    category: 'Respiratory Monitoring',
    merchant: 'Tata 1mg',
    description: 'Non-invasive pulse oximeter tracking arterial hemoglobin SpO2 and pulse rate with OLED multi-directional display.',
    url: 'https://www.1mg.com',
  },
  {
    id: 'shp-3',
    title: 'Accu-Chek Active Blood Glucose Glucometer Kit',
    category: 'Diabetic Supplies',
    merchant: 'Netmeds',
    description: 'Easy-to-operate blood glucose meter delivering accurate glycemic readings in 5 seconds with 10 test strips.',
    url: 'https://www.netmeds.com',
  },
  {
    id: 'shp-4',
    title: 'Ergonomic Memory Foam Lumbar Support Cushion',
    category: 'Orthopedic Rehabilitation',
    merchant: 'HealthKart',
    description: 'High-density orthopedic backrest designed to support natural lumbar lordosis during prolonged seated work.',
    url: 'https://www.healthkart.com',
  },
];

export default function HealthShopPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Health Shop & Medical Equipment Discovery</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Curated clinical equipment, monitors, and rehabilitation aids with verified merchant referral links.
          </p>
        </div>
      </div>

      {/* Commerce Truth Invariant */}
      <div className="p-4 rounded-xl bg-slate-100 border border-slate-300 text-slate-800 text-xs leading-relaxed space-y-1">
        <div className="flex items-center gap-2 font-bold text-slate-900">
          <ShieldCheck className="w-4 h-4 text-sky-600" />
          <span>Commerce Invariant</span>
        </div>
        <p>
          ZENDOC provides discovery and direct merchant referral. We never fabricate stock availability, artificial discount percentages, or settlement commissions. Final transaction occurs on the verified merchant platform.
        </p>
      </div>

      {/* Products Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {SHOP_ITEMS.map((item) => (
          <div
            key={item.id}
            className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm hover:shadow-md transition flex flex-col justify-between space-y-4"
          >
            <div className="space-y-2">
              <div className="flex items-start justify-between">
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-50 text-sky-700 uppercase">
                  {item.category}
                </span>
                <span className="text-xs text-slate-400 font-medium">Merchant: {item.merchant}</span>
              </div>
              <h2 className="text-base font-bold text-slate-900">{item.title}</h2>
              <p className="text-xs text-slate-600 leading-relaxed">{item.description}</p>
            </div>

            <div className="pt-4 border-t border-slate-100 flex items-center justify-end">
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-black text-white text-xs font-semibold shadow-sm transition flex items-center gap-1.5"
              >
                <span>View on Merchant Store</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
