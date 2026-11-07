import { NextRequest, NextResponse } from 'next/server';
import { processAIChat } from '@/lib/ai/model-router';
import { evaluateEmergencyTriage } from '@/lib/ai/emergency-triage';
import { checkDistributedRateLimit } from '@/lib/security/rate-limiter';

const MAX_MESSAGE_LENGTH = 10_000;

export async function POST(req: NextRequest) {
  // ── 1. Safe JSON Body Parsing ───────────────────────────────────────────────
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

  // ── 2. Immediate Emergency Triage Check (NEVER Blocked by Rate Limiting) ────
  // Life-safety invariant: Critical clinical emergencies must NEVER be silenced
  // by IP or user rate limits. They require 0 external tokens and evaluate locally.
  const emergencyCheck = evaluateEmergencyTriage(message);
  if (emergencyCheck.is_emergency) {
    return NextResponse.json({
      success: false,
      is_emergency: true,
      triage: emergencyCheck,
      content: `${emergencyCheck.action_advice}\n\nEmergency Numbers: ${emergencyCheck.emergency_numbers.join(', ')}`,
      suggested_actions: [
        {
          title: 'Call Emergency Ambulance (102/108/112)',
          action_type: 'emergency_call',
          payload: { numbers: emergencyCheck.emergency_numbers },
        },
      ],
      disclaimer: 'CRITICAL CLINICAL ALERT: Immediate emergency medical evaluation required.',
      provider: 'emergency_rules_engine',
    });
  }

  // ── 3. Distributed Rate Limiting for Non-Emergency Queries ──────────────────
  const clientIp =
    req.headers?.get?.('x-forwarded-for')?.split(',')[0].trim() ||
    req.headers?.get?.('x-real-ip') ||
    '127.0.0.1';

  const rateLimit = await checkDistributedRateLimit(clientIp, 10, 60_000);
  if (!rateLimit.success) {
    return NextResponse.json(
      { error: 'Rate limit exceeded. Maximum 10 queries per minute permitted for AI Advisory.' },
      {
        status: 429,
        headers: {
          'Retry-After': Math.ceil(rateLimit.resetMs / 1000).toString(),
          'X-RateLimit-Limit': rateLimit.limit.toString(),
          'X-RateLimit-Remaining': rateLimit.remaining.toString(),
        },
      }
    );
  }

  // ── 4. Clinical Advisory Formulation ────────────────────────────────────────
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
