'use client';

import React, { useState } from 'react';
import { Truck, PhoneCall, AlertTriangle, CheckCircle2, Clock, MapPin, ShieldCheck } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function TransportPage() {
  const [pickup, setPickup] = useState('');
  const [destination, setDestination] = useState('');
  const [transportType, setTransportType] = useState('non_emergency');
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
            <h1 className="text-2xl font-bold text-slate-900">Medical Transport & Patient Transfer</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Book scheduled non-emergency patient transport, stretcher vans, and inter-hospital transfers.
          </p>
        </div>
      </div>

      {/* Emergency Hotline Alert */}
      <div className="p-5 rounded-2xl bg-amber-500 text-amber-950 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm">
        <div className="flex items-center gap-3">
          <AlertTriangle className="w-6 h-6 text-amber-950 shrink-0" />
          <div>
            <h2 className="font-bold text-sm">Critical Medical Emergency? Do NOT book online.</h2>
            <p className="text-xs text-amber-950/80">
              For acute trauma, cardiac arrest, or severe stroke, dial the national emergency dispatch line immediately.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <a
            href="tel:102"
            className="px-4 py-2 rounded-xl bg-amber-950 text-white text-xs font-bold hover:bg-black transition flex items-center gap-1.5 shadow"
          >
            <PhoneCall className="w-3.5 h-3.5" />
            <span>Dial 102 (Ambulance)</span>
          </a>
          <a
            href="tel:108"
            className="px-4 py-2 rounded-xl bg-amber-950 text-white text-xs font-bold hover:bg-black transition flex items-center gap-1.5 shadow"
          >
            <PhoneCall className="w-3.5 h-3.5" />
            <span>Dial 108</span>
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Booking Form */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Truck className="w-4 h-4 text-sky-600" />
            <span>Book Non-Emergency Transport</span>
          </h2>

          {submitted ? (
            <div className="p-5 bg-emerald-50 border border-emerald-200 rounded-xl space-y-2 text-center">
              <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto" />
              <h3 className="font-bold text-xs text-emerald-950">Transport Request Recorded</h3>
              <p className="text-[11px] text-emerald-800">
                Transport Request <code>TR-55410</code> has been routed to our transport coordinator network.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Pickup Address</label>
                <input
                  type="text"
                  placeholder="Home address or hospital ward..."
                  value={pickup}
                  onChange={(e) => setPickup(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Destination Facility</label>
                <input
                  type="text"
                  placeholder="Target clinic, diagnostic center, or hospital..."
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Vehicle Specification</label>
                <select
                  value={transportType}
                  onChange={(e) => setTransportType(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="non_emergency">Basic Patient Transfer Van (Seated)</option>
                  <option value="wheelchair_accessible">Wheelchair Accessible Van with Hydraulic Lift</option>
                  <option value="stretcher">Stretcher Patient Transport with Oxygen Support</option>
                </select>
              </div>

              <button
                type="submit"
                className="w-full py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs shadow-sm transition"
              >
                Submit Transport Request
              </button>
            </form>
          )}
        </div>

        {/* Transport Operational Status */}
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900">Partner Transport Network</h2>
          <p className="text-xs text-slate-500">
            Transport request records are acknowledged only after confirmed dispatch by an authorized partner fleet.
          </p>

          <div className="p-4 rounded-xl border border-slate-100 bg-slate-50 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900">Kolkata Medical Mobility Fleet</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 uppercase">
                Active Partner
              </span>
            </div>
            <p className="text-slate-600">
              Coverage: Kolkata Municipal Corporation, Bidhannagar, New Town, and Howrah. Fleet includes BLS and ALS vehicles.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
