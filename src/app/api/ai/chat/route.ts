import { NextRequest, NextResponse } from 'next/server';
import { processAIChat } from '@/lib/ai/model-router';

// In-memory sliding-window rate limiter (10 requests per minute per IP)
const rateLimitStore = new Map<string, { count: number; windowStart: number }>();
const RATE_LIMIT_WINDOW_MS = 60_000;
const MAX_REQUESTS_PER_WINDOW = 10;
const MAX_MESSAGE_LENGTH = 10_000;

function checkRateLimit(ip: string): boolean {
  const now = Date.now();
  const clientData = rateLimitStore.get(ip);

  // Periodic cleanup if store grows large
  if (rateLimitStore.size > 5000) {
    for (const [key, val] of rateLimitStore.entries()) {
      if (now - val.windowStart > RATE_LIMIT_WINDOW_MS) {
        rateLimitStore.delete(key);
      }
    }
  }

  if (!clientData || now - clientData.windowStart > RATE_LIMIT_WINDOW_MS) {
    rateLimitStore.set(ip, { count: 1, windowStart: now });
    return true;
  }

  if (clientData.count >= MAX_REQUESTS_PER_WINDOW) {
    return false;
  }

  clientData.count += 1;
  return true;
}

export async function POST(req: NextRequest) {
  // ── 1. Rate Limiting ────────────────────────────────────────────────────────
  const clientIp =
    req.headers?.get?.('x-forwarded-for')?.split(',')[0].trim() ||
    req.headers?.get?.('x-real-ip') ||
    '127.0.0.1';

  if (!checkRateLimit(clientIp)) {
    return NextResponse.json(
      { error: 'Rate limit exceeded. Maximum 10 queries per minute permitted for AI Advisory.' },
      { status: 429 }
    );
  }

  // ── 2. Safe JSON Body Parsing ───────────────────────────────────────────────
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: 'Invalid JSON body. Please provide a well-formed JSON object.' },
      { status: 400 }
    );
  }

  if (!body || typeof body !== 'object') {
    return NextResponse.json(
      { error: 'Request body must be a valid JSON object.' },
      { status: 400 }
    );
  }

  const { message, context } = body as { message?: unknown; context?: unknown };

  if (!message || typeof message !== 'string' || message.trim() === '') {
    return NextResponse.json(
      { error: 'Valid query message is required.' },
      { status: 400 }
    );
  }

  if (message.length > MAX_MESSAGE_LENGTH) {
    return NextResponse.json(
      { error: `Query exceeds maximum length of ${MAX_MESSAGE_LENGTH} characters.` },
      { status: 400 }
    );
  }

  // ── 3. Emergency Triage & Clinical Advisory Formulation ─────────────────────
  try {
    const aiResult = await processAIChat(
      message,
      context && typeof context === 'object' ? (context as any) : undefined
    );
    return NextResponse.json(aiResult);
  } catch (err: unknown) {
    const errorMessage = err instanceof Error ? err.message : 'Internal Server Error';
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    );
  }
}
