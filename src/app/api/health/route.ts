import { NextResponse } from 'next/server';

export async function GET() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
  const isDbConfigured =
    Boolean(supabaseUrl) &&
    !supabaseUrl.includes('placeholder') &&
    !supabaseUrl.includes('your-project-id');

  const isWorkerEnabled = process.env.PYTHON_WORKER_ENABLED === 'true';
  const isDistributedRateLimiterConfigured = Boolean(
    process.env.UPSTASH_REDIS_REST_URL && process.env.UPSTASH_REDIS_REST_TOKEN
  );

  return NextResponse.json({
    status: 'healthy',
    version: '2.0.0',
    app: 'ZENDOC 2.0 Rebuild',
    framework: 'Next.js 15+ App Router',
    environment: process.env.VERCEL_ENV || process.env.NODE_ENV || 'production',
    git: {
      branch: process.env.VERCEL_GIT_COMMIT_REF || 'rebuild/zendoc-2.0-vercel',
      commit: process.env.VERCEL_GIT_COMMIT_SHA || 'ba6a790',
    },
    integrations: {
      supabase_database: isDbConfigured ? 'CONNECTED' : 'STANDBY_CONFIGURATION_PENDING',
      supabase_auth: isDbConfigured ? 'CONNECTED' : 'STANDBY_CONFIGURATION_PENDING',
      python_worker: isWorkerEnabled ? 'ENABLED' : 'DISABLED_FEATURE_FLAG',
      distributed_rate_limiter: isDistributedRateLimiterConfigured ? 'DISTRIBUTED_REDIS' : 'LOCAL_SLIDING_WINDOW_FALLBACK',
    },
    system: {
      uptime_seconds: Math.floor(process.uptime()),
      memory_usage_mb: Math.round(process.memoryUsage().rss / 1024 / 1024),
    },
    timestamp: new Date().toISOString(),
  });
}
