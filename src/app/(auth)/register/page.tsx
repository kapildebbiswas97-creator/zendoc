'use client';

import React, { useActionState } from 'react';
import Link from 'next/link';
import {
  Heart, Lock, Mail, User, Phone, ArrowRight, AlertCircle, ShieldCheck,
} from 'lucide-react';
import { signUpAction, type AuthActionResult } from '@/actions/auth';

const initialState: AuthActionResult | null = null;

export default function RegisterPage() {
  const [state, formAction, isPending] = useActionState(signUpAction, initialState);

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200 p-8 shadow-sm space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-sky-600 text-white flex items-center justify-center font-bold mx-auto shadow-sm">
            <Heart className="w-6 h-6 fill-current" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Create Patient Account</h1>
          <p className="text-xs text-slate-500">
            Join ZENDOC 2.0 to manage your longitudinal health memory and access verified healthcare.
          </p>
        </div>

        {/* Error banner */}
        {state && !state.success && (
          <div className="flex items-start gap-2 rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{state.error}</span>
          </div>
        )}

        <form action={formAction} className="space-y-4">
          {/* Hidden role field — patient by default */}
          <input type="hidden" name="role" value="patient" />

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="fullName">
              Full Name
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                id="fullName"
                name="fullName"
                type="text"
                placeholder="Rahul Sharma"
                required
                autoComplete="name"
                className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="email">
              Email Address
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                id="email"
                name="email"
                type="email"
                placeholder="you@example.com"
                required
                autoComplete="email"
                className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="phone">
              Phone Number
            </label>
            <div className="relative">
              <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                id="phone"
                name="phone"
                type="tel"
                placeholder="+91 98301 23456"
                required
                autoComplete="tel"
                className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="password">
              Password <span className="text-slate-400 font-normal">(min 10 characters)</span>
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                id="password"
                name="password"
                type="password"
                placeholder="Choose a strong password"
                required
                minLength={10}
                autoComplete="new-password"
                className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isPending}
            className="w-full py-3 rounded-xl bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-semibold text-sm shadow-sm transition flex items-center justify-center gap-2"
          >
            <span>{isPending ? 'Creating Account…' : 'Create Account'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          <div className="flex items-center gap-2 rounded-xl bg-slate-50 border border-slate-100 p-3 text-xs text-slate-500">
            <ShieldCheck className="w-4 h-4 text-sky-500 shrink-0" />
            <span>Your data is encrypted at rest. HIPAA-aligned access controls apply.</span>
          </div>
        </form>

        <div className="pt-4 border-t border-slate-100 text-center text-xs text-slate-500">
          Already have an account?{' '}
          <Link href="/login" className="font-semibold text-sky-600 hover:text-sky-700">
            Sign In
          </Link>
        </div>
      </div>
    </div>
  );
}
