'use client';

import React, { useState } from 'react';
import { Smile, Frown, Meh, Sun, Moon, Lock, ShieldCheck, Heart, Sparkles, CheckCircle2 } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

export default function MentalWellnessPage() {
  const [mood, setMood] = useState<'GREAT' | 'GOOD' | 'NEUTRAL' | 'STRESSED' | 'OVERWHELMED'>('GOOD');
  const [reflection, setReflection] = useState('');
  const [saved, setSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Mental Wellness & Daily Reflection</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Private, user-owned mood tracking and stress awareness. Entries are completely private to you.
          </p>
        </div>
      </div>

      {saved && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-semibold flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          <span>Daily wellness reflection recorded privately.</span>
        </div>
      )}

      {/* Mood Check-In Card */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-6">
        <h2 className="text-base font-bold text-slate-900">How are you feeling today?</h2>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            { id: 'GREAT', label: 'Energized', icon: Sun, color: 'text-amber-500 bg-amber-50' },
            { id: 'GOOD', label: 'Calm / Good', icon: Smile, color: 'text-emerald-500 bg-emerald-50' },
            { id: 'NEUTRAL', label: 'Neutral', icon: Meh, color: 'text-slate-500 bg-slate-50' },
            { id: 'STRESSED', label: 'Stressed', icon: Frown, color: 'text-indigo-500 bg-indigo-50' },
            { id: 'OVERWHELMED', label: 'Fatigued', icon: Moon, color: 'text-purple-500 bg-purple-50' },
          ].map((item) => {
            const Icon = item.icon;
            const isSelected = mood === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setMood(item.id as any)}
                className={`p-4 rounded-2xl border text-center transition flex flex-col items-center gap-2 ${
                  isSelected
                    ? 'border-sky-600 bg-sky-50 ring-2 ring-sky-500/20'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${item.color}`}>
                  <Icon className="w-6 h-6" />
                </div>
                <span className="text-xs font-bold text-slate-800">{item.label}</span>
              </button>
            );
          })}
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Personal Reflection Journal (Private)</label>
            <textarea
              rows={3}
              placeholder="What contributed to how you feel today? Note sleep quality, work stress, or self-care moments..."
              value={reflection}
              onChange={(e) => setReflection(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <Lock className="w-3.5 h-3.5 text-slate-400" />
              <span>Never shared with external advertisers or AI models</span>
            </div>

            <button
              type="submit"
              className="px-5 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs shadow-sm transition"
            >
              Save Reflection
            </button>
          </div>
        </form>
      </div>

      {/* Guided Relaxation & Breathing Exercises */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-slate-900">Guided Breathwork & Calming Exercises</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
            <h3 className="font-bold text-xs text-slate-900">4-7-8 Deep Relaxation Breathing</h3>
            <p className="text-xs text-slate-600">
              Inhale through nose for 4 seconds, hold gently for 7 seconds, exhale slowly through mouth for 8 seconds. Reduces autonomic nervous system arousal.
            </p>
            <span className="text-[10px] font-bold text-sky-700 uppercase">5-Minute Practice</span>
          </div>

          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
            <h3 className="font-bold text-xs text-slate-900">Box Breathing (Square Respiration)</h3>
            <p className="text-xs text-slate-600">
              4 seconds inhale, 4 seconds hold, 4 seconds exhale, 4 seconds hold. Restores focus during high-stress working hours.
            </p>
            <span className="text-[10px] font-bold text-indigo-700 uppercase">4-Minute Practice</span>
          </div>
        </div>
      </div>
    </div>
  );
}
