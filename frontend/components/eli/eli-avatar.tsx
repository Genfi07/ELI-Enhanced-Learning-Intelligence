"use client";

import { cn } from "@/lib/utils";

type EliState = "idle" | "thinking" | "streaming" | "happy";

interface EliAvatarProps {
  /** Tamaño en píxeles. Default: 32 */
  size?: number;
  /** Estado emocional que afecta la animación */
  state?: EliState;
  /** Clase CSS adicional */
  className?: string;
}

/**
 * Avatar animado de ELI.
 *
 * Un orbe con gradiente + spark interior, con animaciones que cambian
 * según el estado:
 *   - idle: respiración lenta (4s)
 *   - thinking: pulso rápido + rotación (1.5s)
 *   - streaming: glow intenso + escala sutil
 *   - happy: destello breve + rebote
 *
 * Usa CSS puro (keyframes en globals.css) para mejor performance.
 * Respeta prefers-reduced-motion.
 */
export function EliAvatar({
  size = 32,
  state = "idle",
  className,
}: EliAvatarProps) {
  const innerSize = Math.round(size * 0.55);

  return (
    <div
      className={cn(
        "relative flex shrink-0 items-center justify-center rounded-full",
        "bg-gradient-to-br from-violet-500/20 via-fuchsia-500/10 to-cyan-500/20",
        "border border-white/10",
        "eli-avatar",
        state === "thinking" && "eli-avatar--thinking",
        state === "streaming" && "eli-avatar--streaming",
        state === "happy" && "eli-avatar--happy",
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {/* Halo exterior con blur sutil */}
      <div
        className="eli-avatar-halo absolute inset-0 rounded-full"
        style={{
          background:
            "radial-gradient(circle at 30% 30%, rgba(167,139,250,0.5), transparent 60%)",
        }}
      />

      {/* Spark SVG con gradiente */}
      <svg
        width={innerSize}
        height={innerSize}
        viewBox="0 0 24 24"
        fill="none"
        className="eli-avatar-spark relative z-10"
      >
        <defs>
          <linearGradient id="eli-spark-grad" x1="0" y1="0" x2="24" y2="24">
            <stop offset="0%" stopColor="#c4b5fd" />
            <stop offset="50%" stopColor="#a78bfa" />
            <stop offset="100%" stopColor="#67e8f9" />
          </linearGradient>
        </defs>
        <path
          d="M12 2 L13.5 8.5 L20 10 L13.5 11.5 L12 18 L10.5 11.5 L4 10 L10.5 8.5 Z"
          fill="url(#eli-spark-grad)"
          stroke="url(#eli-spark-grad)"
          strokeWidth="0.5"
          strokeLinejoin="round"
        />
        <circle cx="19" cy="5" r="1.2" fill="#67e8f9" opacity="0.9" />
        <circle cx="5" cy="19" r="0.8" fill="#c4b5fd" opacity="0.7" />
      </svg>
    </div>
  );
}