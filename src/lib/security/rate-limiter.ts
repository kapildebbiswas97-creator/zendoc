/**
 * ZENDOC 2.0 — Distributed Serverless-Ready Rate Limiter
 * 
 * Architecture:
 * 1. Supports distributed key-value storage (Upstash Redis REST API) for multi-region Vercel Serverless.
 * 2. Automatic, graceful fallback to in-memory sliding window when Redis is unconfigured or unreachable.
 * 3. Never throws exceptions — fails open or degrades safely so transient network issues don't crash patient care.
 */

export interface RateLimitResult {
  success: boolean;
  limit: number;
  remaining: number;
  resetMs: number;
  source: 'distributed' | 'in_memory';
}

const memoryStore = new Map<string, { count: number; windowStart: number }>();
const DEFAULT_WINDOW_MS = 60_000; // 60 seconds
const DEFAULT_MAX_REQUESTS = 10;   // 10 requests per minute

/**
 * Checks rate limit for a client identifier (e.g. IP address or user ID).
 */
export async function checkDistributedRateLimit(
  identifier: string,
  maxRequests: number = DEFAULT_MAX_REQUESTS,
  windowMs: number = DEFAULT_WINDOW_MS
): Promise<RateLimitResult> {
  const upstashUrl = process.env.UPSTASH_REDIS_REST_URL;
  const upstashToken = process.env.UPSTASH_REDIS_REST_TOKEN;

  // ── Strategy 1: Distributed Redis REST API (when configured) ─────────────
  if (upstashUrl && upstashToken) {
    try {
      const key = `rate_limit:${identifier}`;
      const now = Date.now();
      const clearBefore = now - windowMs;

      // Pipeline via Upstash REST: ZREMRANGEBYSCORE, ZADD, ZCARD, EXPIRE
      const response = await fetch(`${upstashUrl}/pipeline`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${upstashToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify([
          ['ZREMRANGEBYSCORE', key, 0, clearBefore],
          ['ZADD', key, now, `${now}-${Math.random()}`],
          ['ZCARD', key],
          ['EXPIRE', key, Math.ceil(windowMs / 1000)],
        ]),
        signal: AbortSignal.timeout(2000), // Strict 2-second timeout
      });

      if (response.ok) {
        const results = await response.json();
        // ZCARD output is at index 2
        const currentCount = typeof results[2]?.result === 'number' ? results[2].result : 1;
        const allowed = currentCount <= maxRequests;

        return {
          success: allowed,
          limit: maxRequests,
          remaining: Math.max(0, maxRequests - currentCount),
          resetMs: windowMs,
          source: 'distributed',
        };
      }
    } catch (err) {
      // Log degraded state and fall through to in-memory fallback
      console.warn('[RateLimiter] Distributed store unreachable, degrading to in-memory fallback:', String(err));
    }
  }

  // ── Strategy 2: Local Sliding Window Fallback ─────────────────────────────
  const now = Date.now();
  const entry = memoryStore.get(identifier);

  // Periodic pruning if memory map exceeds size threshold
  if (memoryStore.size > 5000) {
    for (const [key, val] of memoryStore.entries()) {
      if (now - val.windowStart > windowMs) {
        memoryStore.delete(key);
      }
    }
  }

  if (!entry || now - entry.windowStart > windowMs) {
    memoryStore.set(identifier, { count: 1, windowStart: now });
    return {
      success: true,
      limit: maxRequests,
      remaining: maxRequests - 1,
      resetMs: windowMs,
      source: 'in_memory',
    };
  }

  if (entry.count >= maxRequests) {
    const elapsed = now - entry.windowStart;
    return {
      success: false,
      limit: maxRequests,
      remaining: 0,
      resetMs: Math.max(0, windowMs - elapsed),
      source: 'in_memory',
    };
  }

  entry.count += 1;
  return {
    success: true,
    limit: maxRequests,
    remaining: maxRequests - entry.count,
    resetMs: Math.max(0, windowMs - (now - entry.windowStart)),
    source: 'in_memory',
  };
}
