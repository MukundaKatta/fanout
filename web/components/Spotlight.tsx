"use client";

import { ReactNode, useRef } from "react";

/**
 * Wraps a region with a soft mouse-following radial gradient. The gradient is
 * applied via CSS variables so it stays in sync without re-rendering React.
 */
export default function Spotlight({
  children,
  className = "",
  color = "rgba(255,255,255,0.06)",
}: {
  children: ReactNode;
  className?: string;
  color?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - rect.left}px`);
    el.style.setProperty("--my", `${e.clientY - rect.top}px`);
  }

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      className={`fanout-spotlight ${className}`}
      style={{ ["--spot" as string]: color }}
    >
      {children}
    </div>
  );
}
