import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  evaluateSupabaseConfiguration,
  runStagingVerification,
} from './supabase-verifier';

describe('Phase 4A: Live Supabase Staging Verifier & Diagnostic Checks', () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    process.env = { ...originalEnv };
    vi.restoreAllMocks();
  });

  it('detects unconfigured or placeholder Supabase credentials correctly', () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://placeholder-project.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'placeholder-anon-key';

    const config = evaluateSupabaseConfiguration();
    expect(config.isConfigured).toBe(false);
  });

  it('detects validly structured Supabase credentials', () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://abcdefghijklm.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.valid-anon-key';
    process.env.SUPABASE_SERVICE_ROLE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.valid-service-key';

    const config = evaluateSupabaseConfiguration();
    expect(config.isConfigured).toBe(true);
    expect(config.hasAnonKey).toBe(true);
    expect(config.hasServiceKey).toBe(true);
  });

  it('generates CONFIG_REQUIRED report when credentials are placeholders', async () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://placeholder-project.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'placeholder-anon-key';

    const report = await runStagingVerification();
    expect(report.overallStatus).toBe('CONFIG_REQUIRED');
    expect(report.isConfigured).toBe(false);

    const credCheck = report.checks.find((c) => c.name.includes('URL & Anon Key'));
    expect(credCheck?.status).toBe('SKIPPED_CREDENTIALS_REQUIRED');
  });

  it('executes live handshake and generates READY report when endpoint is reachable', async () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://live-test.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'live-anon-token';
    process.env.SUPABASE_SERVICE_ROLE_KEY = 'live-service-token';

    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
    } as any);

    const report = await runStagingVerification();
    expect(report.overallStatus).toBe('READY');
    expect(report.isConfigured).toBe(true);

    const handshakeCheck = report.checks.find((c) => c.name.includes('Live REST'));
    expect(handshakeCheck?.status).toBe('PASSED');
  });
});
