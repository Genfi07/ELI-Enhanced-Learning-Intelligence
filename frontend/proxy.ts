import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Middleware global: protege rutas privadas verificando la existencia de
 * la cookie `eli_session`.
 *
 * Solo comprueba EXISTENCIA, no validez — la validez se verifica siempre
 * en el backend. La cookie es httpOnly, así que JS del cliente no la ve,
 * pero el middleware corre en el servidor y sí puede leerla.
 *
 * Si un usuario sin sesión intenta acceder a una ruta privada, se le
 * redirige a /login?from=<ruta original>. Tras login, el frontend usa ese
 * `from` para redirigir de vuelta.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Rutas públicas
  if (pathname === "/") return NextResponse.next();
  const publicPrefixes = ["/login", "/register", "/api", "/_next", "/favicon"];
  if (publicPrefixes.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }
  // Archivos estáticos (algo.ext)
  const lastSegment = pathname.split("/").pop() ?? "";
  if (lastSegment.includes(".")) return NextResponse.next();

  // Requiere sesión
  const sessionCookie = request.cookies.get("eli_session");
  if (!sessionCookie) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?from=${encodeURIComponent(pathname)}`;
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};