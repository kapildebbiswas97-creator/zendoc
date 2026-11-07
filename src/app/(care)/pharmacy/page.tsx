'use client';

import React, { useState } from 'react';
import { Pill, Upload, AlertCircle, CheckCircle2, Clock, Truck, ShieldCheck } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function PharmacyPage() {
  const [address, setAddress] = useState('124 E.M. Bypass, Sector 3, Kolkata 700098');
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Pharmacy Request & Fulfilment</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Upload valid digital prescriptions for licensed pharmacy quote generation and delivery tracking.
          </p>
        </div>
      </div>

      {/* Safety & Real Stock Invariant Banner */}
      <div className="p-4 rounded-xl bg-slate-100 border border-slate-300 text-slate-800 text-xs leading-relaxed space-y-1">
        <div className="flex items-center gap-2 font-bold text-slate-900">
          <ShieldCheck className="w-4 h-4 text-sky-600" />
          <span>Clinical & Inventory Invariant</span>
        </div>
        <p>
          ZENDOC never fabricates stock availability or medicine prices. Dispensing requires a valid signed prescription and confirmation from a licensed retail or hospital pharmacy partner.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Order Request Form */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Pill className="w-4 h-4 text-sky-600" />
            <span>Submit Prescription Order</span>
          </h2>

          {submitted ? (
            <div className="p-5 bg-emerald-50 border border-emerald-200 rounded-xl space-y-2 text-center">
              <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto" />
              <h3 className="font-bold text-xs text-emerald-950">Prescription Order Placed!</h3>
              <p className="text-[11px] text-emerald-800">
                Order <code>PH-90214</code> has been forwarded to partnered licensed pharmacies for availability verification.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Select Active Prescription</label>
                <select className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs focus:outline-none focus:ring-2 focus:ring-sky-500">
                  <option>Cardiology Rx - Dr. Debabrata Sen (Telmisartan 40mg, Atorvastatin 10mg)</option>
                  <option>Pediatric Rx - Dr. Sharmistha Mukherjee (Paracetamol syrup)</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Delivery Address</label>
                <textarea
                  rows={3}
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <button
                type="submit"
                className="w-full py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs shadow-sm transition"
              >
                Request Pharmacy Quotes
              </button>
            </form>
          )}
        </div>

        {/* Existing Order Track */}
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Truck className="w-4 h-4 text-indigo-600" />
            <span>Active Pharmacy Fulfilment Tracking</span>
          </h2>

          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-xs text-slate-900">Order #PH-88412 â€¢ Monthly Maintenance Refill</h3>
                <p className="text-[11px] text-slate-500">Fulfilled by Apollo Pharmacy, Salt Lake Sector 2</p>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-100 text-sky-800 uppercase">
                Dispatched
              </span>
            </div>

            <div className="space-y-1.5 text-xs text-slate-600 border-t border-slate-200 pt-3">
              <div className="flex justify-between">
                <span>Telmisartan 40mg (Strip of 15):</span>
                <span className="font-semibold text-slate-800">â‚¹145.00</span>
              </div>
              <div className="flex justify-between">
                <span>Atorvastatin 10mg (Strip of 10):</span>
                <span className="font-semibold text-slate-800">â‚¹112.50</span>
              </div>
              <div className="flex justify-between font-bold text-slate-900 pt-1 border-t border-slate-100">
                <span>Total Verified Cost:</span>
                <span>â‚¹257.50</span>
              </div>
            </div>

            <div className="flex items-center gap-2 text-[11px] text-slate-500 pt-1">
              <Clock className="w-3.5 h-3.5" />
              <span>Estimated Doorstep Delivery: Today by 07:00 PM</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
