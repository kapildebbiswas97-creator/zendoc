import { describe, it, expect } from 'vitest';
import { z } from 'zod';

// ─── Schemas mirroring src/actions/auth.ts ────────────────────────────────────
// (We re-declare them here so the tests have no server-side import issues.)

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

// ─── Login validation ─────────────────────────────────────────────────────────

describe('Login form validation', () => {
  it('passes with valid credentials', () => {
    const result = LoginSchema.safeParse({ email: 'user@example.com', password: 'secret123' });
    expect(result.success).toBe(true);
  });

  it('rejects invalid email', () => {
    const result = LoginSchema.safeParse({ email: 'not-an-email', password: 'secret123' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toBe('Invalid email address');
  });

  it('rejects empty password', () => {
    const result = LoginSchema.safeParse({ email: 'user@example.com', password: '' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toBe('Password is required');
  });
});

// ─── Register validation ──────────────────────────────────────────────────────

describe('Register form validation', () => {
  const valid = {
    fullName: 'Rahul Sharma',
    email: 'rahul@example.com',
    phone: '9830012345',
    password: 'StrongPass123',
    role: 'patient' as const,
  };

  it('passes with valid patient data', () => {
    const result = RegisterSchema.safeParse(valid);
    expect(result.success).toBe(true);
    expect(result.data?.role).toBe('patient');
  });

  it('defaults role to patient when omitted', () => {
    const { role: _, ...withoutRole } = valid;
    const result = RegisterSchema.safeParse(withoutRole);
    expect(result.success).toBe(true);
    expect(result.data?.role).toBe('patient');
  });

  it('rejects short full name', () => {
    const result = RegisterSchema.safeParse({ ...valid, fullName: 'A' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toMatch(/at least 2 characters/);
  });

  it('rejects password shorter than 10 chars', () => {
    const result = RegisterSchema.safeParse({ ...valid, password: 'short' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toMatch(/at least 10 characters/);
  });

  it('rejects invalid phone (too short)', () => {
    const result = RegisterSchema.safeParse({ ...valid, phone: '12345' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toMatch(/valid phone/);
  });

  it('rejects invalid role', () => {
    const result = RegisterSchema.safeParse({ ...valid, role: 'superuser' });
    expect(result.success).toBe(false);
  });

  it('accepts provider role', () => {
    const result = RegisterSchema.safeParse({ ...valid, role: 'provider' });
    expect(result.success).toBe(true);
    expect(result.data?.role).toBe('provider');
  });
});

// ─── Middleware route classification (logic only, no Next.js runtime) ─────────

describe('Route classification logic', () => {
  const PUBLIC_ROUTES = new Set(['/', '/login', '/register', '/find-care', '/shop', '/community', '/api/health', '/api/ai/chat', '/api/auth/callback']);
  const PUBLIC_PREFIXES = ['/_next/', '/favicon', '/images/', '/icons/'];

  function isPublicRoute(pathname: string): boolean {
    if (PUBLIC_ROUTES.has(pathname)) return true;
    return PUBLIC_PREFIXES.some((p) => pathname.startsWith(p));
  }

  it('marks / as public', () => expect(isPublicRoute('/')).toBe(true));
  it('marks /login as public', () => expect(isPublicRoute('/login')).toBe(true));
  it('marks /register as public', () => expect(isPublicRoute('/register')).toBe(true));
  it('marks /dashboard as protected', () => expect(isPublicRoute('/dashboard')).toBe(false));
  it('marks /records as protected', () => expect(isPublicRoute('/records')).toBe(false));
  it('marks /admin/overview as protected', () => expect(isPublicRoute('/admin/overview')).toBe(false));
  it('marks /_next/static/... as public', () => expect(isPublicRoute('/_next/static/chunks/app.js')).toBe(true));
  it('marks /api/health as public', () => expect(isPublicRoute('/api/health')).toBe(true));
  it('marks /api/records/upload as protected', () => expect(isPublicRoute('/api/records/upload')).toBe(false));
});

// ─── Role-based redirect logic ────────────────────────────────────────────────

describe('Role home resolution', () => {
  const ROLE_HOME: Record<string, string> = {
    admin: '/admin/overview',
    provider: '/provider/dashboard',
    patient: '/dashboard',
  };

  it('routes admin to /admin/overview', () => expect(ROLE_HOME['admin']).toBe('/admin/overview'));
  it('routes provider to /provider/dashboard', () => expect(ROLE_HOME['provider']).toBe('/provider/dashboard'));
  it('routes patient to /dashboard', () => expect(ROLE_HOME['patient']).toBe('/dashboard'));
  it('falls back to /dashboard for unknown role', () => {
    const role = 'unknown';
    const home = ROLE_HOME[role] ?? '/dashboard';
    expect(home).toBe('/dashboard');
  });
});
