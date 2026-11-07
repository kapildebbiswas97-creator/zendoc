'use server';

import { redirect } from 'next/navigation';
import { createClient } from '@/lib/supabase/server';
import { z } from 'zod';

// ─── Schemas ──────────────────────────────────────────────────────────────────

const LoginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(1, 'Password is required'),
});

const RegisterSchema = z.object({
  fullName: z.string().min(2, 'Full name must be at least 2 characters'),
  email: z.string().email('Invalid email address'),
  phone: z.string().min(10, 'Enter a valid phone number'),
  password: z.string().min(10, 'Password must be at least 10 characters'),
  role: z.enum(['patient', 'provider', 'admin']).default('patient'),
});

// ─── Types ────────────────────────────────────────────────────────────────────

export type AuthActionResult =
  | { success: true; redirectTo: string }
  | { success: false; error: string };

// ─── Login ────────────────────────────────────────────────────────────────────

export async function signInAction(
  _prevState: AuthActionResult | null,
  formData: FormData
): Promise<AuthActionResult> {
  const raw = {
    email: formData.get('email') as string,
    password: formData.get('password') as string,
  };

  const parsed = LoginSchema.safeParse(raw);
  if (!parsed.success) {
    return {
      success: false,
      error: parsed.error.issues[0]?.message ?? 'Invalid input.',
    };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithPassword({
    email: parsed.data.email,
    password: parsed.data.password,
  });

  if (error || !data.user) {
    return {
      success: false,
      error:
        error?.message === 'Invalid login credentials'
          ? 'Incorrect email or password.'
          : (error?.message ?? 'Sign in failed. Please try again.'),
    };
  }

  const role =
    (data.user.user_metadata?.role as string | undefined) ?? 'patient';
  const home =
    role === 'admin'
      ? '/admin/overview'
      : role === 'provider'
        ? '/provider/dashboard'
        : '/dashboard';

  redirect(home);
}

// ─── Register ────────────────────────────────────────────────────────────────

export async function signUpAction(
  _prevState: AuthActionResult | null,
  formData: FormData
): Promise<AuthActionResult> {
  const raw = {
    fullName: formData.get('fullName') as string,
    email: formData.get('email') as string,
    phone: formData.get('phone') as string,
    password: formData.get('password') as string,
    role: (formData.get('role') as string | null) ?? 'patient',
  };

  const parsed = RegisterSchema.safeParse(raw);
  if (!parsed.success) {
    return {
      success: false,
      error: parsed.error.issues[0]?.message ?? 'Invalid input.',
    };
  }

  const supabase = await createClient();

  const { data, error } = await supabase.auth.signUp({
    email: parsed.data.email,
    password: parsed.data.password,
    options: {
      data: {
        full_name: parsed.data.fullName,
        phone: parsed.data.phone,
        role: parsed.data.role,
      },
    },
  });

  if (error) {
    return {
      success: false,
      error: error.message,
    };
  }

  // Insert profile row — the trigger in the migration should handle this, but
  // we insert here as a belt-and-suspenders measure; ON CONFLICT DO NOTHING.
  if (data.user) {
    await supabase.from('profiles').upsert(
      {
        id: data.user.id,
        full_name: parsed.data.fullName,
        phone: parsed.data.phone,
        role: parsed.data.role,
        email: parsed.data.email,
      },
      { onConflict: 'id', ignoreDuplicates: true }
    );
  }

  // If email confirmation is required, Supabase sends the email and
  // data.session will be null — redirect to a confirmation page.
  if (!data.session) {
    redirect('/login?notice=check-email');
  }

  redirect('/dashboard');
}

// ─── Sign Out ────────────────────────────────────────────────────────────────

export async function signOutAction(): Promise<void> {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect('/login');
}

// ─── Get current user (Server Component helper) ───────────────────────────────

export async function getCurrentUser() {
  const supabase = await createClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();
  if (error || !user) return null;
  return user;
}
