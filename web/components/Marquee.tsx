"use client";

import { ReactNode } from "react";

/**
 * Infinite-scroll horizontal marquee. Pauses on hover. Children are rendered twice
 * back-to-back so the loop seam is invisible.
 */
export default function Marquee({
  children,
  speedSeconds = 40,
  className = "",
}: {
  children: ReactNode;
  speedSeconds?: number;
  className?: string;
}) {
  return (
    <div className={`fanout-marquee group ${className}`}>
      <div
        className="fanout-marquee-track"
        style={{ animationDuration: `${speedSeconds}s` }}
      >
        <div className="fanout-marquee-row">{children}</div>
        <div className="fanout-marquee-row" aria-hidden="true">
          {children}
        </div>
      </div>
    </div>
  );
}
