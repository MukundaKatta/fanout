/**
 * Fanout brand mark — a "fan" of dispatch lines from a source node to three endpoints.
 *
 * Animation:
 *  • Source node breathes (gentle pulse, sets the heartbeat)
 *  • Each dispatch line is a stroke-dasharray running from source -> endpoint,
 *    staggered so the wave reads top -> middle -> bottom continuously
 *  • Endpoint dots scale + glow when their wave arrives, then settle
 *  • On hover, the loop accelerates (set via CSS animation-duration)
 */
export default function Logo({
  size = 28,
  className = "",
  animated = true,
}: {
  size?: number;
  className?: string;
  animated?: boolean;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`${className} ${animated ? "fanout-logo" : ""}`}
      aria-label="Fanout"
    >
      <defs>
        <linearGradient id="fanout-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0%"  stopColor="#A78BFA" />
          <stop offset="50%" stopColor="#F472B6" />
          <stop offset="100%" stopColor="#22D3EE" />
        </linearGradient>
        <radialGradient id="fanout-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%"  stopColor="#F472B6" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#F472B6" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Soft halo behind source */}
      <circle cx="6" cy="16" r="10" fill="url(#fanout-glow)" className="fanout-halo" />

      {/* Source node */}
      <circle cx="6" cy="16" r="3" fill="url(#fanout-grad)" className="fanout-source" />

      {/* Dispatch lines — drawn with stroke-dasharray for a "data running" effect */}
      <path d="M9 16 L26 6"  stroke="url(#fanout-grad)" strokeWidth="1.6" strokeLinecap="round"
            className="fanout-line fanout-line-1" pathLength="1" />
      <path d="M9 16 L28 16" stroke="url(#fanout-grad)" strokeWidth="1.6" strokeLinecap="round"
            className="fanout-line fanout-line-2" pathLength="1" />
      <path d="M9 16 L26 26" stroke="url(#fanout-grad)" strokeWidth="1.6" strokeLinecap="round"
            className="fanout-line fanout-line-3" pathLength="1" />

      {/* Endpoint dots — scale + brighten on wave arrival */}
      <circle cx="26" cy="6"  r="2" fill="url(#fanout-grad)" className="fanout-dot fanout-dot-1" />
      <circle cx="28" cy="16" r="2" fill="url(#fanout-grad)" className="fanout-dot fanout-dot-2" />
      <circle cx="26" cy="26" r="2" fill="url(#fanout-grad)" className="fanout-dot fanout-dot-3" />
    </svg>
  );
}
