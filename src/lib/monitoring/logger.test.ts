import { describe, it, expect, vi } from 'vitest';
import {
  sanitizeLogMessage,
  logEvent,
  startOperationTimer,
} from './logger';

describe('Phase 4F: Structured Healthcare Logging & PHI Redaction', () => {
  it('redacts email addresses from log strings', () => {
    const raw = 'User patient.rahul@hospital.org attempted to access lab report';
    const clean = sanitizeLogMessage(raw);

    expect(clean).not.toContain('patient.rahul@hospital.org');
    expect(clean).toContain('[EMAIL_REDACTED]');
  });

  it('redacts phone numbers from log strings', () => {
    const raw = 'SMS notification sent to +91 98300 12345 successfully';
    const clean = sanitizeLogMessage(raw);

    expect(clean).not.toContain('98300 12345');
    expect(clean).toContain('[PHONE_REDACTED]');
  });

  it('redacts Bearer authorization tokens from log strings', () => {
    const raw = 'Outgoing webhook with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token payload';
    const clean = sanitizeLogMessage(raw);

    expect(clean).not.toContain('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token');
    expect(clean).toContain('Bearer [TOKEN_REDACTED]');
  });

  it('formats structured JSON output with level and metadata', () => {
    const consoleSpy = vi.spyOn(console, 'info').mockImplementation(() => {});
    const entry = logEvent('INFO', 'Database connection established', { region: 'ap-south-1' });

    expect(entry.service).toBe('zendoc-app');
    expect(entry.level).toBe('INFO');
    expect(entry.metadata?.region).toBe('ap-south-1');

    consoleSpy.mockRestore();
  });

  it('measures operation elapsed latency via timer helper', async () => {
    const timer = startOperationTimer('test_db_query');
    await new Promise((resolve) => setTimeout(resolve, 20));
    const elapsed = timer.stop({ rows: 10 });

    expect(elapsed).toBeGreaterThanOrEqual(15);
  });
});
