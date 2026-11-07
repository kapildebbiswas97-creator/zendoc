import { createServerClient } from '@supabase/ssr';
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

/**
 * Auth Callback Route
 * Handles:
 *  - Email confirmation links (type=signup)
 *  - Password reset links    (type=recovery)
 *  - Magic link logins       (type=magiclink)
 *
 * Supabase sends the user here after they click a link in email.
 * We exchange the one-time `code` for a session cookie, then redirect.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get('code');
  const type = searchParams.get('type') ?? 'signup';
  const next = searchParams.get('next') ?? '/dashboard';

  if (!code) {
    // No code means the link was malformed or already consumed
    return NextResponse.redirect(`${origin}/login?error=invalid-link`);
  }

  const cookieStore = await cookies();

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet: Array<{ name: string; value: string; options?: Record<string, unknown> }>) {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options as Parameters<typeof cookieStore.set>[2]);
          });
        },
      },
    }
  );

  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    console.error('[auth/callback] exchangeCodeForSession error:', error.message);
    return NextResponse.redirect(
      `${origin}/login?error=auth-callback-failed&msg=${encodeURIComponent(error.message)}`
    );
  }

  // Redirect based on flow type
  if (type === 'recovery') {
    return NextResponse.redirect(`${origin}/reset-password`);
  }

  return NextResponse.redirect(`${origin}${next}`);
}
