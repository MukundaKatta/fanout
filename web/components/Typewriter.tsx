"use client";

import { useEffect, useState } from "react";

/**
 * Reveals `text` character by character. Used for fresh draft content so it
 * feels like the agent is typing.
 *
 * Speed is per-char. Long drafts auto-skip past the typewriter to keep the
 * total reveal under ~2.5 seconds.
 */
export default function Typewriter({
  text,
  charMs = 6,
  className = "",
}: {
  text: string;
  charMs?: number;
  className?: string;
}) {
  const [i, setI] = useState(0);

  useEffect(() => {
    setI(0);
    const totalBudgetMs = 2500;
    const stride = Math.max(1, Math.ceil((text.length * charMs) / totalBudgetMs));
    let idx = 0;
    const id = setInterval(() => {
      idx = Math.min(text.length, idx + stride);
      setI(idx);
      if (idx >= text.length) clearInterval(id);
    }, charMs);
    return () => clearInterval(id);
  }, [text, charMs]);

  return (
    <span className={className}>
      {text.slice(0, i)}
      {i < text.length && (
        <span className="fanout-caret" />
      )}
    </span>
  );
}
