import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { createHmac } from 'crypto';

/**
 * POST /api/workers/ocr
 * Forwards a document (PDF or image) to the Python OCR/extraction worker.
 * Returns structured text extraction result.
 */
export async function POST(request: NextRequest) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized.' }, { status: 401 });
  }

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

  try {
    const body = await request.arrayBuffer();
    const timestamp = Date.now().toString();
    const hmac = createHmac('sha256', workerSecret)
      .update(`${timestamp}:${user.id}`)
      .digest('hex');

    const upstream = await fetch(`${workerUrl}/api/ocr/extract`, {
      method: 'POST',
      headers: {
        'Content-Type': request.headers.get('content-type') ?? 'application/octet-stream',
        'X-Zendoc-Timestamp': timestamp,
        'X-Zendoc-User-Id': user.id,
        'X-Zendoc-Hmac': hmac,
      },
      body,
      signal: AbortSignal.timeout(90_000),
    });

    const result = await upstream.json();
    return NextResponse.json(result, { status: upstream.status });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'OCR worker unreachable.';
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
