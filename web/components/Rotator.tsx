"use client";

import { useEffect, useState } from "react";

/**
 * Cycles through `words` with a smooth fade+blur transition. Each word takes
 * its natural width — the hero is center-aligned, so the line gracefully
 * re-centers per word without leaving empty gaps.
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
    <span
      key={i}
      className={`inline-block whitespace-nowrap fanout-rotator-item ${className}`}
    >
      {words[i]}
    </span>
  );
}
