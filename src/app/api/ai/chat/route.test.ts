import { describe, it, expect, vi, beforeEach } from 'vitest';

// ─── Mock next/server so the test runner doesn't need Next.js ─────────────────
vi.mock('next/server', () => {
  const json = (body: unknown, init?: { status?: number }) =>
    ({ _body: body, _status: init?.status ?? 200, json: async () => body });
  return { NextRequest: class {}, NextResponse: { json } };
});

// ─── Mock the AI module ───────────────────────────────────────────────────────
vi.mock('@/lib/ai/model-router', () => ({
  processAIChat: vi.fn(async (message: string) => ({
    response: `Mock advisory for: ${message}`,
    is_emergency: false,
    disclaimer: 'ZENDOC AI is for educational purposes only.',
    provider: 'mock',
  })),
}));

// ─── Import after mocks ───────────────────────────────────────────────────────
import { POST } from '@/app/api/ai/chat/route';
import { processAIChat } from '@/lib/ai/model-router';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeRequest(body: unknown) {
  return { json: async () => body } as any;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('POST /api/ai/chat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns 400 when message field is missing', async () => {
    const req = makeRequest({ context: {} });
    const res = await POST(req);
    expect(res._status).toBe(400);
    const data = await res.json();
    expect(data.error).toMatch(/message/i);
  });

  it('returns 400 when message is not a string', async () => {
    const req = makeRequest({ message: 42 });
    const res = await POST(req);
    expect(res._status).toBe(400);
  });

  it('returns 400 when message is empty string', async () => {
    const req = makeRequest({ message: '' });
    const res = await POST(req);
    expect(res._status).toBe(400);
  });

  it('calls processAIChat with valid message', async () => {
    const req = makeRequest({ message: 'What are symptoms of diabetes?' });
    await POST(req);
    expect(processAIChat).toHaveBeenCalledWith(
      'What are symptoms of diabetes?',
      undefined
    );
  });

  it('returns AI response body on success', async () => {
    const req = makeRequest({ message: 'How do I manage hypertension?' });
    const res = await POST(req);
    expect(res._status).toBe(200);
    const data = await res.json();
    expect(data.disclaimer).toContain('ZENDOC AI');
  });

  it('passes context to processAIChat when provided', async () => {
    const ctx = { patientId: 'test-123', conditions: ['diabetes'] };
    const req = makeRequest({ message: 'How much metformin?', context: ctx });
    await POST(req);
    expect(processAIChat).toHaveBeenCalledWith('How much metformin?', ctx);
  });
});
