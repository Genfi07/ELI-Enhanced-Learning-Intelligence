import type { NextConfig } from "next";

/**
 * Next.js reescribe /api/* al backend Python (puerto 8000).
 *
 * Beneficios:
 *   - El navegador ve un único origen (localhost:3000). Cero CORS.
 *   - Las cookies httpOnly del backend viajan sin SameSite=None.
 *   - En Codespaces solo exponemos el puerto 3000, no el 8000.
 *
 * En producción se reemplaza por la URL real del backend con una variable
 * de entorno. Por ahora apuntamos a localhost porque Codespaces lo proxea.
 */
const BACKEND_URL =
  process.env.ELI_BACKEND_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "https://eli-enhanced-learning-intelligence.onrender.com";
  
const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;