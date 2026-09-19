import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.ELI_BACKEND_URL ??
  "https://eli-enhanced-learning-intelligence.onrender.com";

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const targetPath = path.join("/");
  const url = `${BACKEND_URL}/api/${targetPath}${req.nextUrl.search}`;

  // Copiar headers de la petición, quitando los que rompen el proxy
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const body =
    req.method === "GET" || req.method === "HEAD"
      ? undefined
      : await req.arrayBuffer();

  let backendRes: Response;
  try {
    backendRes = await fetch(url, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
    });
  } catch (err) {
    return NextResponse.json(
      { detail: `Backend no disponible: ${(err as Error).message}` },
      { status: 502 },
    );
  }

  // Copiar headers de respuesta, excepto los que controla Next.js
  const resHeaders = new Headers();
  backendRes.headers.forEach((value, key) => {
    const k = key.toLowerCase();
    if (
      k === "content-encoding" ||
      k === "content-length" ||
      k === "transfer-encoding" ||
      k === "set-cookie"
    ) {
      return;
    }
    resHeaders.set(key, value);
  });

  // CRÍTICO: preservar TODAS las cookies del backend.
  // Este es el bug que arreglamos: Next.js elimina set-cookie en rewrites
  // cross-domain. Aquí lo copiamos explícitamente.
  const cookies = backendRes.headers.getSetCookie?.() ?? [];
  if (cookies.length === 0) {
    const raw = backendRes.headers.get("set-cookie");
    if (raw) cookies.push(raw);
  }

  const response = new NextResponse(backendRes.body, {
    status: backendRes.status,
    headers: resHeaders,
  });

  for (const cookie of cookies) {
    response.headers.append("set-cookie", cookie);
  }

  return response;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;