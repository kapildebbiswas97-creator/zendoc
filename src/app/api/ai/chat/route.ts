import { NextRequest, NextResponse } from 'next/server';
import { processAIChat } from '@/lib/ai/model-router';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { message, context } = body;

    if (!message || typeof message !== 'string') {
      return NextResponse.json(
        { error: 'Valid query message is required.' },
        { status: 400 }
      );
    }

    const aiResult = await processAIChat(message, context);

    return NextResponse.json(aiResult);
  } catch (err: unknown) {
    const errorMessage = err instanceof Error ? err.message : 'Internal Server Error';
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    );
  }
}
