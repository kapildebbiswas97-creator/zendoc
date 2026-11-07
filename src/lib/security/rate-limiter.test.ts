import { describe, it, expect, vi, beforeEach } from 'vitest';
import { checkDistributedRateLimit } from './rate-limiter';

describe('Phase 4D: Distributed Rate Limiter & Serverless Abuse Protection', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('allows requests within the defined threshold using in-memory mode', async () => {
    const clientId = 'test-client-allowed';
    const result1 = await checkDistributedRateLimit(clientId, 5, 60_000);

    expect(result1.success).toBe(true);
    expect(result1.remaining).toBe(4);
    expect(result1.source).toBe('in_memory');

    const result2 = await checkDistributedRateLimit(clientId, 5, 60_000);
    expect(result2.success).toBe(true);
    expect(result2.remaining).toBe(3);
  });

  it('blocks requests when threshold is exceeded', async () => {
    const clientId = 'test-client-blocked';
    const limit = 3;

    for (let i = 0; i < limit; i++) {
      const res = await checkDistributedRateLimit(clientId, limit, 60_000);
      expect(res.success).toBe(true);
    }

    // 4th request must be blocked
    const blockedRes = await checkDistributedRateLimit(clientId, limit, 60_000);
    expect(blockedRes.success).toBe(false);
    expect(blockedRes.remaining).toBe(0);
  });

  it('connects to Upstash Redis REST API when configured and parses pipeline output', async () => {
    process.env.UPSTASH_REDIS_REST_URL = 'https://fake-redis.upstash.io';
    process.env.UPSTASH_REDIS_REST_TOKEN = 'mock-token';

    const mockFetch = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => [
        { result: 0 },
        { result: 1 },
        { result: 2 }, // ZCARD = 2
        { result: 1 },
      ],
    } as any);

    const result = await checkDistributedRateLimit('redis-client', 5, 60_000);

    expect(mockFetch).toHaveBeenCalled();
    expect(result.source).toBe('distributed');
    expect(result.success).toBe(true);
    expect(result.remaining).toBe(3);

    delete process.env.UPSTASH_REDIS_REST_URL;
    delete process.env.UPSTASH_REDIS_REST_TOKEN;
  });

  it('gracefully degrades to in-memory mode if Upstash Redis call fails or times out', async () => {
    process.env.UPSTASH_REDIS_REST_URL = 'https://broken-redis.upstash.io';
    process.env.UPSTASH_REDIS_REST_TOKEN = 'mock-token';

    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Network timeout'));

    const result = await checkDistributedRateLimit('failing-redis-client', 5, 60_000);

    expect(result.source).toBe('in_memory');
    expect(result.success).toBe(true);

    delete process.env.UPSTASH_REDIS_REST_URL;
    delete process.env.UPSTASH_REDIS_REST_TOKEN;
  });
});
