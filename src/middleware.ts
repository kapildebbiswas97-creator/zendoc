import { createServerClient } from '@supabase/ssr';
import { NextRequest, NextResponse } from 'next/server';

// Routes that never require authentication
const PUBLIC_ROUTES = new Set([
  '/',
  '/login',
  '/register',
  '/find-care',
  '/shop',
  '/community',
  '/api/health',
  '/api/ai/chat',
  '/api/auth/callback',
]);

// Routes that are public by prefix
const PUBLIC_PREFIXES = [
  '/_next/',
  '/favicon',
  '/images/',
  '/icons/',
];

function isPublicRoute(pathname: string): boolean {
  if (PUBLIC_ROUTES.has(pathname)) return true;
  return PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

// Role → canonical home path
const ROLE_HOME: Record<string, string> = {
  admin: '/admin/overview',
  provider: '/provider/dashboard',
  patient: '/dashboard',
};

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip middleware for static assets fast
  if (PUBLIC_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  // If Supabase is not configured (placeholder URLs), allow everything to pass
  // through so the app renders its synthetic-data UI without crashing.
  const supabaseConfigured =
    supabaseUrl &&
    supabaseAnonKey &&
    !supabaseUrl.includes('placeholder') &&
    !supabaseAnonKey.includes('placeholder');

  if (!supabaseConfigured) {
    return NextResponse.next();
  }

  let response = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl!, supabaseAnonKey!, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: Array<{ name: string; value: string; options?: Record<string, unknown> }>) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value)
        );
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options as Parameters<typeof response.cookies.set>[2])
        );
      },
    },
  });

  // Refresh session — MUST be called before checking user
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // ── Unauthenticated access to protected route ─────────────────────────────
  if (!user && !isPublicRoute(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    url.searchParams.set('redirectTo', pathname);
    return NextResponse.redirect(url);
  }

  // ── Authenticated user hitting /login or /register ────────────────────────
  if (user && (pathname === '/login' || pathname === '/register')) {
    const role =
      (user.user_metadata?.role as string | undefined) ?? 'patient';
    const home = ROLE_HOME[role] ?? '/dashboard';
    const url = request.nextUrl.clone();
    url.pathname = home;
    return NextResponse.redirect(url);
  }

  // ── Role-based guarding ───────────────────────────────────────────────────
  if (user) {
    const role =
      (user.user_metadata?.role as string | undefined) ?? 'patient';

    // Only admins can access /admin/*
    if (pathname.startsWith('/admin') && role !== 'admin') {
      const url = request.nextUrl.clone();
      url.pathname = ROLE_HOME[role] ?? '/dashboard';
      return NextResponse.redirect(url);
    }

    // Only providers/admins can access /provider/*
    if (
      pathname.startsWith('/provider') &&
      role !== 'provider' &&
      role !== 'admin'
    ) {
      const url = request.nextUrl.clone();
      url.pathname = ROLE_HOME[role] ?? '/dashboard';
      return NextResponse.redirect(url);
    }
  }

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths EXCEPT:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
