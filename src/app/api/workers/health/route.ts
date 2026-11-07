import { NextResponse } from 'next/server';

/**
 * GET /api/workers/health
 * Polls the Python worker health endpoint.
 * Returns combined status for the Next.js → Python worker boundary.
 */
export async function GET() {
  const workerEnabled = process.env.PYTHON_WORKER_ENABLED === 'true';
  const workerUrl = process.env.PYTHON_WORKER_URL;

  if (!workerEnabled || !workerUrl) {
    return NextResponse.json({
      worker: { enabled: false, status: 'disabled', message: 'Python worker is feature-flagged off.' },
      nextjs: { status: 'ok' },
    });
  }

  try {
    const upstream = await fetch(`${workerUrl}/api/health`, {
      signal: AbortSignal.timeout(5_000),
    });
    const data = await upstream.json();
    return NextResponse.json({
      worker: { enabled: true, status: upstream.ok ? 'ok' : 'degraded', upstreamResponse: data },
      nextjs: { status: 'ok' },
    });
  } catch (err) {
    return NextResponse.json(
      {
        worker: { enabled: true, status: 'unreachable', error: String(err) },
        nextjs: { status: 'ok' },
      },
      { status: 502 }
    );
  }
}
