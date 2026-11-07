'use client';

import React, { useState } from 'react';
import { Activity, Flame, Droplets, CheckCircle2, Dumbbell, Play } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function FitnessPage() {
  const [waterGlasses, setWaterGlasses] = useState(6);
  const [targetGlasses] = useState(10);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Fitness, Movement & Hydration</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            General physical wellness and mobility routines designed to support cardiovascular recovery and healthy movement.
          </p>
        </div>
      </div>

      {/* Daily Progress Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: Steps */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Daily Steps</span>
            <Activity className="w-5 h-5 text-sky-600" />
          </div>
          <div className="text-3xl font-black text-slate-900">
            6,420 <span className="text-xs font-normal text-slate-400">/ 8,000 steps</span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
            <div className="bg-sky-600 h-2 rounded-full" style={{ width: '80%' }} />
          </div>
          <p className="text-xs text-slate-500">80% of daily cardiovascular walking goal achieved.</p>
        </div>

        {/* Card 2: Hydration */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Hydration Log</span>
            <Droplets className="w-5 h-5 text-sky-500" />
          </div>
          <div className="text-3xl font-black text-slate-900">
            {waterGlasses * 250} <span className="text-xs font-normal text-slate-400">/ 2,500 ml</span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
            <div className="bg-sky-500 h-2 rounded-full" style={{ width: `${(waterGlasses / targetGlasses) * 100}%` }} />
          </div>
          <div className="flex items-center justify-between pt-1">
            <span className="text-xs text-slate-500">{waterGlasses} of {targetGlasses} glasses</span>
            <button
              type="button"
              onClick={() => setWaterGlasses((prev) => Math.min(prev + 1, targetGlasses + 4))}
              className="px-2.5 py-1 rounded-lg bg-sky-50 text-sky-700 text-xs font-bold hover:bg-sky-100 transition"
            >
              + Add Glass (250ml)
            </button>
          </div>
        </div>

        {/* Card 3: Active Calories */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Active Energy</span>
            <Flame className="w-5 h-5 text-amber-500" />
          </div>
          <div className="text-3xl font-black text-slate-900">
            340 <span className="text-xs font-normal text-slate-400">kcal burned</span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
            <div className="bg-amber-500 h-2 rounded-full" style={{ width: '68%' }} />
          </div>
          <p className="text-xs text-slate-500">Based on brisk walking and stretching session.</p>
        </div>
      </div>

      {/* Recommended Mobility Workouts */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
          <Dumbbell className="w-5 h-5 text-indigo-600" />
          <span>Curated Low-Impact Clinical Mobility Routines</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-900">Gentle Spine & Core Mobility</span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-800">15 Min</span>
            </div>
            <p className="text-xs text-slate-600">Cat-cow, bird-dog, and gentle hamstring stretches to relieve lower back stiffness.</p>
            <button
              type="button"
              className="w-full py-1.5 rounded-lg bg-white border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 flex items-center justify-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Start Routine</span>
            </button>
          </div>

          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-900">Cardiovascular Brisk Walk Guide</span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-50 text-sky-800">30 Min</span>
            </div>
            <p className="text-xs text-slate-600">Paced walking protocol to maintain steady target heart rate between 110â€“125 bpm.</p>
            <button
              type="button"
              className="w-full py-1.5 rounded-lg bg-white border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 flex items-center justify-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Start Routine</span>
            </button>
          </div>

          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-900">Neck & Shoulder Posture Relief</span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-indigo-50 text-indigo-800">10 Min</span>
            </div>
            <p className="text-xs text-slate-600">Targeted isometric cervical exercises for desk professionals to relieve neck fatigue.</p>
            <button
              type="button"
              className="w-full py-1.5 rounded-lg bg-white border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 flex items-center justify-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Start Routine</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
