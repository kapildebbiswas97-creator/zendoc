import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    status: 'healthy',
    version: '2.0.0',
    app: 'ZENDOC 2.0 Rebuild',
    framework: 'Next.js 15+ App Router',
    runtime: 'Vercel Edge / Serverless',
    database: 'Supabase PostgreSQL (RLS Enforced)',
    auth: 'Supabase Auth SSR',
    storage: 'Supabase Storage (Private Buckets)',
    aws_origin_proxy: 'RETIRED (Zero Origin Rewrite)',
    oci_compute: 'RETIRED',
    timestamp: new Date().toISOString(),
  });
}
