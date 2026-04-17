/**
 * Ambient rotating squares behind everything.
 *
 * Two concentric, gradient-bordered squares spin in opposite directions at
 * different speeds to create gentle depth. Sits in a fixed -z-10 layer so it
 * never affects layout or pointer events.
 *
 * Hidden under prefers-reduced-motion via the existing global rule (each
 * element uses a `fanout-*` animation class which is no-op'd in that media query).
 */
export default function BackgroundSquares() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-[5] overflow-hidden"
    >
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        {/* Outer square — clockwise, slow */}
        <div className="fanout-square-outer" />
        {/* Inner square — counter-clockwise, faster */}
        <div className="fanout-square-inner" />
        {/* Tiny accent square — fastest, far smaller */}
        <div className="fanout-square-accent" />
      </div>
    </div>
  );
}
