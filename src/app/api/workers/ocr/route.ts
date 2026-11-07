import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { generateWorkerHmac } from '@/lib/security/worker-auth';

const MAX_DOC_BYTES = 25 * 1024 * 1024; // 25 MB ceiling
const ALLOWED_DOC_MIMES = new Set([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
  'application/dicom',
]);

/**
 * POST /api/workers/ocr
 * Authenticated proxy forwarding clinical documents for OCR & structured extraction.
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
      { error: 'OCR worker is not enabled in this deployment.', code: 'WORKER_DISABLED' },
      { status: 503 }
    );
  }

  const workerUrl = process.env.PYTHON_WORKER_URL;
  const workerSecret = process.env.PYTHON_WORKER_SECRET;

  if (!workerUrl || !workerSecret) {
    return NextResponse.json({ error: 'OCR worker is misconfigured.' }, { status: 503 });
  }

  // ── 3. Content Type & Size Validation ──────────────────────────────────────
  const contentType = (request.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
  if (contentType && !ALLOWED_DOC_MIMES.has(contentType)) {
    return NextResponse.json(
      { error: `Unsupported document MIME type '${contentType}'. Permitted: PDF, JPEG, PNG, WEBP, HEIC, DICOM.` },
      { status: 415 }
    );
  }

  const contentLength = parseInt(request.headers.get('content-length') || '0', 10);
  if (contentLength > MAX_DOC_BYTES) {
    return NextResponse.json(
      { error: 'Payload exceeds maximum allowable document size of 25 MB.' },
      { status: 413 }
    );
  }

  // ── 4. Forward Document Payload with HMAC-SHA256 Token ─────────────────────
  try {
    const body = await request.arrayBuffer();
    if (body.byteLength > MAX_DOC_BYTES) {
      return NextResponse.json(
        { error: 'Document buffer exceeds maximum allowable limit of 25 MB.' },
        { status: 413 }
      );
    }

    const timestamp = Date.now().toString();
    const hmac = generateWorkerHmac(workerSecret, timestamp, user.id);

    const upstream = await fetch(`${workerUrl}/api/ocr/extract`, {
      method: 'POST',
      headers: {
        'Content-Type': contentType || 'application/octet-stream',
        'X-Zendoc-Timestamp': timestamp,
        'X-Zendoc-User-Id': user.id,
        'X-Zendoc-Hmac': hmac,
      },
      body,
      signal: AbortSignal.timeout(90_000), // 90s timeout for heavy OCR
    });

    const result = await upstream.json();
    return NextResponse.json(result, { status: upstream.status });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'OCR worker unreachable.';
    console.error('[OCR Worker Proxy Error]', { userId: user.id, error: msg });
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
