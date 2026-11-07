import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { createHmac } from 'crypto';

/**
 * POST /api/workers/asr
 * Authenticated endpoint that forwards audio to the Python Whisper ASR worker.
 * Guards:
 *  1. Supabase session required (401 if not authenticated)
 *  2. HMAC token added to outgoing request so the Python worker can verify origin
 *  3. Python worker feature-flagged via PYTHON_WORKER_ENABLED
 */
export async function POST(request: NextRequest) {
  // ── Auth guard ────────────────────────────────────────────────────────────
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized.' }, { status: 401 });
  }

  // ── Feature flag ──────────────────────────────────────────────────────────
  if (process.env.PYTHON_WORKER_ENABLED !== 'true') {
    return NextResponse.json(
      { error: 'ASR worker is not enabled in this deployment.', code: 'WORKER_DISABLED' },
      { status: 503 }
    );
  }

  const workerUrl = process.env.PYTHON_WORKER_URL;
  const workerSecret = process.env.PYTHON_WORKER_SECRET;

  if (!workerUrl || !workerSecret) {
    return NextResponse.json(
      { error: 'ASR worker is misconfigured.' },
      { status: 503 }
    );
  }

  // ── Forward multipart audio to Python worker ──────────────────────────────
  try {
    const body = await request.arrayBuffer();
    const timestamp = Date.now().toString();
    const hmac = createHmac('sha256', workerSecret)
      .update(`${timestamp}:${user.id}`)
      .digest('hex');

    const upstream = await fetch(`${workerUrl}/api/asr/transcribe`, {
      method: 'POST',
      headers: {
        'Content-Type': request.headers.get('content-type') ?? 'application/octet-stream',
        'X-Zendoc-Timestamp': timestamp,
        'X-Zendoc-User-Id': user.id,
        'X-Zendoc-Hmac': hmac,
      },
      body,
      signal: AbortSignal.timeout(60_000), // Whisper can be slow
    });

    const result = await upstream.json();
    return NextResponse.json(result, { status: upstream.status });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'ASR worker unreachable.';
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
