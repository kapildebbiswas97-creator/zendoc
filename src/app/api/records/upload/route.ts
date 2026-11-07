import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { uploadMedicalRecord } from '@/actions/records';
import { checkDistributedRateLimit } from '@/lib/security/rate-limiter';

/**
 * POST /api/records/upload
 * Accepts multipart/form-data with a medical document.
 * Authenticates via session cookie, delegates to the uploadMedicalRecord action.
 */
export async function POST(request: NextRequest) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized.' }, { status: 401 });
  }

  // Rate Limiting: 20 document uploads per minute per user
  const rateLimit = await checkDistributedRateLimit(`upload:${user.id}`, 20, 60_000);
  if (!rateLimit.success) {
    return NextResponse.json(
      { error: 'Document upload rate limit exceeded. Please wait before uploading more files.' },
      { status: 429 }
    );
  }

  try {
    const formData = await request.formData();
    const result = await uploadMedicalRecord(formData);

    if (!result.success) {
      return NextResponse.json({ error: result.error }, { status: 422 });
    }

    return NextResponse.json(
      { recordId: result.recordId, storagePath: result.storagePath },
      { status: 201 }
    );
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
