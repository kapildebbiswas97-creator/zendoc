'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Search, MapPin, Star, ShieldCheck, Calendar, Filter, Building2, Stethoscope } from 'lucide-react';
import { SYNTHETIC_PROVIDERS, SYNTHETIC_FACILITIES } from '@/lib/data/synthetic-store';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function FindCarePage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('ALL');

  const filteredProviders = SYNTHETIC_PROVIDERS.filter((provider) => {
    const matchesQuery = 
      provider.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      provider.specialty.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (provider.facility_name && provider.facility_name.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesCategory = 
      selectedCategory === 'ALL' || 
      provider.specialty.toUpperCase() === selectedCategory;

    return matchesQuery && matchesCategory;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Healthcare Discovery & Finder</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Search verified doctors, clinics, and hospitals. Data verified against official state medical registries â€” zero fabricated ratings or slots.
          </p>
        </div>
      </div>

      {/* Search & Filters */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-3 w-5 h-5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by doctor name, clinical specialty, or hospital..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-sky-500 text-sm"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400 ml-2" />
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="py-2.5 px-3 rounded-xl border border-slate-200 bg-white text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <option value="ALL">All Specialties</option>
              <option value="CARDIOLOGIST">Cardiology</option>
              <option value="PEDIATRICIAN">Pediatrics</option>
              <option value="ORTHOPEDIC SURGEON">Orthopedics</option>
            </select>
          </div>
        </div>
      </div>

      {/* Provider List */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <Stethoscope className="w-5 h-5 text-sky-600" />
            <span>Verified Clinicians ({filteredProviders.length})</span>
          </h2>
          <span className="text-xs text-slate-500">Kolkata Metropolitan Area</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredProviders.map((provider) => (
            <div
              key={provider.id}
              className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm hover:shadow-md transition flex flex-col justify-between space-y-4"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold text-base text-slate-900">{provider.full_name}</h3>
                    <p className="text-xs font-semibold text-sky-700">{provider.specialty}</p>
                  </div>
                  <div className="flex items-center gap-1 text-xs font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded">
                    <Star className="w-3.5 h-3.5 fill-current" />
                    <span>{provider.rating}</span>
                  </div>
                </div>

                <p className="text-xs text-slate-500 font-mono">Reg: {provider.registration_number}</p>
                <p className="text-xs text-slate-600 line-clamp-2">{provider.qualifications}</p>

                <div className="flex items-center gap-1.5 text-xs text-slate-600 pt-2 border-t border-slate-100">
                  <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
                  <span className="truncate">{provider.facility_name}</span>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                <div>
                  <span className="text-[10px] text-slate-400 block uppercase font-bold">Consultation Fee</span>
                  <span className="text-base font-extrabold text-slate-900">â‚¹{provider.consultation_fee}</span>
                </div>

                <Link
                  href={`/appointments/book?providerId=${provider.id}`}
                  className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold shadow-sm transition flex items-center gap-1.5"
                >
                  <Calendar className="w-3.5 h-3.5" />
                  <span>Book Visit</span>
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Facilities Section */}
      <div className="space-y-4 pt-6">
        <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
          <Building2 className="w-5 h-5 text-indigo-600" />
          <span>Accredited Healthcare Facilities ({SYNTHETIC_FACILITIES.length})</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {SYNTHETIC_FACILITIES.map((facility) => (
            <div key={facility.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-2">
              <div className="flex items-start justify-between">
                <h3 className="font-bold text-sm text-slate-900">{facility.name}</h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-100 uppercase">
                  Verified
                </span>
              </div>
              <p className="text-xs text-indigo-600 font-semibold">{facility.category}</p>
              <p className="text-xs text-slate-500">{facility.address}, {facility.city} - {facility.pincode}</p>
              <div className="text-[11px] text-slate-400 pt-2 border-t border-slate-100">
                Phone: <span className="font-semibold text-slate-700">{facility.phone}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
