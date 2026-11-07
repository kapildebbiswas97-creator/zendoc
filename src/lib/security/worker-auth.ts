import { createHmac, timingSafeEqual } from 'crypto';

/**
 * ZENDOC 2.0 — Secure Python Worker Authentication Boundary
 * 
 * Provides cryptographic HMAC-SHA256 generation, constant-time validation,
 * and timestamp-based replay protection for internal proxy operations.
 */

const DEFAULT_MAX_AGE_MS = 60_000; // 60 seconds replay tolerance
const MAX_FUTURE_DRIFT_MS = 5_000; // 5 seconds allowable clock drift

/**
 * Computes an HMAC-SHA256 digest over the combined timestamp and user identity.
 */
export function generateWorkerHmac(secret: string, timestamp: string, userId: string): string {
  if (!secret) throw new Error('Worker secret is required for HMAC generation.');
  const payload = `${timestamp}:${userId}`;
  return createHmac('sha256', secret).update(payload).digest('hex');
}

/**
 * Validates an incoming or callback HMAC using constant-time equality comparison to prevent timing attacks.
 */
export function validateWorkerHmac(
  secret: string,
  timestamp: string,
  userId: string,
  receivedHmac: string
): boolean {
  if (!secret || !receivedHmac) return false;

  try {
    const expectedHmac = generateWorkerHmac(secret, timestamp, userId);
    const expectedBuffer = Buffer.from(expectedHmac, 'hex');
    const receivedBuffer = Buffer.from(receivedHmac, 'hex');

    if (expectedBuffer.length !== receivedBuffer.length) {
      return false;
    }

    return timingSafeEqual(expectedBuffer, receivedBuffer);
  } catch {
    return false;
  }
}

/**
 * Validates that a timestamp is fresh (not replayed from the past) and not forged in the distant future.
 */
export function isTimestampFresh(
  timestampStr: string,
  maxAgeMs: number = DEFAULT_MAX_AGE_MS
): boolean {
  const timestamp = parseInt(timestampStr, 10);
  if (isNaN(timestamp) || timestamp <= 0) return false;

  const now = Date.now();
  const age = now - timestamp;

  // Replay check: cannot be older than maxAgeMs
  if (age > maxAgeMs) return false;

  // Future check: cannot be ahead of current time by more than allowable drift
  if (timestamp - now > MAX_FUTURE_DRIFT_MS) return false;

  return true;
}
