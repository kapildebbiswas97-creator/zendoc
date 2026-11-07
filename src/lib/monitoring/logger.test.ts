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

  it('redacts national identity numbers (SSN & Aadhaar)', () => {
    const ssnRaw = 'Patient SSN on intake form: 123-45-6789';
    const aadhaarRaw = 'Patient Aadhaar: 1234 5678 9012 verified';

    expect(sanitizeLogMessage(ssnRaw)).toContain('[SSN_REDACTED]');
    expect(sanitizeLogMessage(ssnRaw)).not.toContain('123-45-6789');

    expect(sanitizeLogMessage(aadhaarRaw)).toContain('[AADHAAR_REDACTED]');
    expect(sanitizeLogMessage(aadhaarRaw)).not.toContain('1234 5678 9012');
  });

  it('redacts payment card numbers and session tokens', () => {
    const cardRaw = 'Card payment processed: 4111 2222 3333 4444';
    const cookieRaw = 'Session cookie: sb-abcdef123-auth-token=secret_jwt_payload_here';

    expect(sanitizeLogMessage(cardRaw)).toContain('[CARD_REDACTED]');
    expect(sanitizeLogMessage(cardRaw)).not.toContain('4111 2222 3333 4444');

    expect(sanitizeLogMessage(cookieRaw)).toContain('[TOKEN_REDACTED]');
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
