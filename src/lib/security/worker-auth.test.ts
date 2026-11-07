import { describe, it, expect } from 'vitest';
import {
  generateWorkerHmac,
  validateWorkerHmac,
  isTimestampFresh,
} from './worker-auth';

describe('Phase 3D: Python Worker Security Boundary — HMAC & Replay Defense', () => {
  const secret = 'zendoc-worker-test-secret-999';
  const userId = 'usr-test-alice';

  describe('HMAC Generation & Consistency', () => {
    it('generates consistent deterministic HMAC-SHA256 hex digests', () => {
      const timestamp = '1762500000000';
      const hmac1 = generateWorkerHmac(secret, timestamp, userId);
      const hmac2 = generateWorkerHmac(secret, timestamp, userId);

      expect(hmac1).toBe(hmac2);
      expect(hmac1).toHaveLength(64); // 256 bits = 64 hex chars
    });

    it('produces distinct HMACs for different timestamps or users', () => {
      const hmacA = generateWorkerHmac(secret, '1000', userId);
      const hmacB = generateWorkerHmac(secret, '2000', userId);
      const hmacC = generateWorkerHmac(secret, '1000', 'usr-bob');

      expect(hmacA).not.toBe(hmacB);
      expect(hmacA).not.toBe(hmacC);
    });

    it('throws error when secret is empty', () => {
      expect(() => generateWorkerHmac('', '1000', userId)).toThrow();
    });
  });

  describe('HMAC Constant-Time Validation', () => {
    it('validates a genuine HMAC successfully', () => {
      const timestamp = Date.now().toString();
      const validHmac = generateWorkerHmac(secret, timestamp, userId);

      const isValid = validateWorkerHmac(secret, timestamp, userId, validHmac);
      expect(isValid).toBe(true);
    });

    it('rejects a tampered or invalid HMAC', () => {
      const timestamp = Date.now().toString();
      const validHmac = generateWorkerHmac(secret, timestamp, userId);
      const tamperedHmac = validHmac.slice(0, -2) + '00';

      const isValid = validateWorkerHmac(secret, timestamp, userId, tamperedHmac);
      expect(isValid).toBe(false);
    });

    it('rejects an HMAC computed with wrong secret', () => {
      const timestamp = Date.now().toString();
      const forgedHmac = generateWorkerHmac('attacker-secret', timestamp, userId);

      const isValid = validateWorkerHmac(secret, timestamp, userId, forgedHmac);
      expect(isValid).toBe(false);
    });
  });

  describe('Timestamp Freshness & Replay Attack Defense', () => {
    it('accepts current timestamp', () => {
      const now = Date.now().toString();
      expect(isTimestampFresh(now)).toBe(true);
    });

    it('accepts a timestamp 30 seconds in the past (< 60s window)', () => {
      const past30s = (Date.now() - 30_000).toString();
      expect(isTimestampFresh(past30s, 60_000)).toBe(true);
    });

    it('rejects a replayed timestamp > 60 seconds old', () => {
      const past70s = (Date.now() - 70_000).toString();
      expect(isTimestampFresh(past70s, 60_000)).toBe(false);
    });

    it('rejects a forged future timestamp > 5 seconds ahead', () => {
      const future15s = (Date.now() + 15_000).toString();
      expect(isTimestampFresh(future15s)).toBe(false);
    });

    it('rejects non-numeric or malformed timestamps', () => {
      expect(isTimestampFresh('invalid-timestamp')).toBe(false);
      expect(isTimestampFresh('-500')).toBe(false);
      expect(isTimestampFresh('')).toBe(false);
    });
  });
});
