/**
 * Anvero's mark (DECISIONS.md, 2026-09-29, "The logo"): an A with sharp ends, in the
 * accent's light teal on a dark navy square, and an amber dot for its crossbar. The
 * same drawing is `public/favicon.svg`; its colours are the brand's own and stay the
 * same in light and dark mode. Decorative wherever it sits beside the name.
 */
export function AnveroLogo({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <rect width="48" height="48" rx="12" fill="#0f2e3a" />
      <path
        d="M13.5 36 L24 12 L34.5 36"
        fill="none"
        stroke="#2dd4bf"
        strokeWidth="4.8"
        strokeLinecap="butt"
        strokeLinejoin="miter"
      />
      <circle cx="24" cy="28.5" r="3.2" fill="#f59e0b" />
    </svg>
  );
}
