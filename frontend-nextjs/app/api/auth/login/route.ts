import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const backendBaseUrl =
      process.env.BACKEND_BASE_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:3000';
    const response = await fetch(`${backendBaseUrl}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      cache: 'no-store',
    });

    const responseText = await response.text();
    let parsed: unknown = {};
    try {
      parsed = responseText ? JSON.parse(responseText) : {};
    } catch {
      parsed = { detail: responseText || 'Invalid backend response' };
    }

    return NextResponse.json(parsed, { status: response.status });
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'Proxy request failed';
    return NextResponse.json({ detail }, { status: 502 });
  }
}
