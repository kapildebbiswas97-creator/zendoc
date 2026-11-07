import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { generateWorkerHmac } from '@/lib/security/worker-auth';

const MAX_AUDIO_BYTES = 25 * 1024 * 1024; // 25 MB ceiling
const ALLOWED_AUDIO_MIMES = new Set([
  'audio/webm',
  'audio/wav',
  'audio/x-wav',
  'audio/mpeg',
  'audio/mp4',
  'audio/ogg',
  'video/webm',
]);

/**
 * POST /api/workers/asr
 * Authenticated proxy for speech-to-text audio processing via internal Whisper worker.
 */
export async function POST(request: NextRequest) {
  // ── 1. Auth Guard ──────────────────────────────────────────────────────────
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized.' }, { status: 401 });
  }

  // ── 2. Feature Flag Guard ──────────────────────────────────────────────────
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

  // ── 3. Content Type & Size Validation ──────────────────────────────────────
  const contentType = (request.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
  if (contentType && !ALLOWED_AUDIO_MIMES.has(contentType) && !contentType.startsWith('audio/')) {
    return NextResponse.json(
      { error: `Unsupported audio MIME type '${contentType}'. Permitted: audio/webm, audio/wav, audio/mpeg, audio/mp4, audio/ogg.` },
      { status: 415 }
    );
  }

  const contentLength = parseInt(request.headers.get('content-length') || '0', 10);
  if (contentLength > MAX_AUDIO_BYTES) {
    return NextResponse.json(
      { error: 'Payload exceeds maximum allowable audio size of 25 MB.' },
      { status: 413 }
    );
  }

  // ── 4. Forward Multipart Payload with HMAC-SHA256 Token ────────────────────
  try {
    const body = await request.arrayBuffer();
    if (body.byteLength > MAX_AUDIO_BYTES) {
      return NextResponse.json(
        { error: 'Audio buffer exceeds maximum allowable limit of 25 MB.' },
        { status: 413 }
      );
    }

    const timestamp = Date.now().toString();
    const hmac = generateWorkerHmac(workerSecret, timestamp, user.id);

    const upstream = await fetch(`${workerUrl}/api/asr/transcribe`, {
      method: 'POST',
      headers: {
        'Content-Type': contentType || 'application/octet-stream',
        'X-Zendoc-Timestamp': timestamp,
        'X-Zendoc-User-Id': user.id,
        'X-Zendoc-Hmac': hmac,
      },
      body,
      signal: AbortSignal.timeout(60_000), // 60s timeout
    });

    const result = await upstream.json();
    return NextResponse.json(result, { status: upstream.status });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'ASR worker unreachable.';
    console.error('[ASR Worker Proxy Error]', { userId: user.id, error: msg });
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
