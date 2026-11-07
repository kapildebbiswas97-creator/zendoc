'use client';

import React, { useActionState } from 'react';
import Link from 'next/link';
import {
  Heart, Lock, Mail, ArrowRight, AlertCircle, Info,
} from 'lucide-react';
import { signInAction, type AuthActionResult } from '@/actions/auth';

const initialState: AuthActionResult | null = null;

export default function LoginPage() {
  const [state, formAction, isPending] = useActionState(signInAction, initialState);

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200 p-8 shadow-sm space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-sky-600 text-white flex items-center justify-center font-bold mx-auto shadow-sm">
            <Heart className="w-6 h-6 fill-current" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Sign in to ZENDOC 2.0</h1>
          <p className="text-xs text-slate-500">
            Secure, HIPAA-aligned patient &amp; provider access powered by Supabase Auth.
          </p>
        </div>

        {/* Error banner */}
        {state && !state.success && (
          <div className="flex items-start gap-2 rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{state.error}</span>
          </div>
        )}

        {/* Notice banner (e.g. check-email after register) */}
        {typeof window !== 'undefined' &&
          new URLSearchParams(window.location.search).get('notice') === 'check-email' && (
            <div className="flex items-start gap-2 rounded-xl bg-sky-50 border border-sky-200 p-3 text-sm text-sky-700">
              <Info className="w-4 h-4 mt-0.5 shrink-0" />
              <span>Account created! Please check your email to confirm before signing in.</span>
            </div>
          )}

        <form action={formAction} className="space-y-4">
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
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold text-slate-700" htmlFor="password">
                Password
              </label>
              <Link href="/forgot-password" className="text-xs text-sky-600 hover:text-sky-700 font-semibold">
                Forgot?
              </Link>
            </div>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                id="password"
                name="password"
                type="password"
                placeholder="Enter password"
                required
                autoComplete="current-password"
                className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isPending}
            className="w-full py-3 rounded-xl bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-semibold text-sm shadow-sm transition flex items-center justify-center gap-2"
          >
            <span>{isPending ? 'Authenticating…' : 'Sign In'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        <div className="pt-4 border-t border-slate-100 text-center text-xs text-slate-500">
          Don&apos;t have an account?{' '}
          <Link href="/register" className="font-semibold text-sky-600 hover:text-sky-700">
            Create Patient Account
          </Link>
        </div>
      </div>
    </div>
  );
}
