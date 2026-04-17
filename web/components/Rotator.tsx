"use client";

import { useEffect, useState } from "react";

/**
 * Cycles through `words` with a smooth fade-up transition. Used to make the
 * hero feel alive ("Ship to LinkedIn → X → Bluesky → Reddit ...").
 */
export default function Rotator({
  words,
  intervalMs = 1800,
  className = "",
}: {
  words: string[];
  intervalMs?: number;
  className?: string;
}) {
  const [i, setI] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setI((v) => (v + 1) % words.length), intervalMs);
    return () => clearInterval(t);
  }, [words.length, intervalMs]);

  return (
    <span className={`relative inline-block align-baseline ${className}`}>
      {/* Reserve max width via the longest word so the layout doesn't jitter */}
      <span className="invisible whitespace-nowrap">
        {words.reduce((a, b) => (a.length >= b.length ? a : b))}
      </span>
      <span className="absolute inset-0 overflow-hidden">
        <span
          key={i}
          className="block whitespace-nowrap fanout-rotator-item"
        >
          {words[i]}
        </span>
      </span>
    </span>
  );
}
