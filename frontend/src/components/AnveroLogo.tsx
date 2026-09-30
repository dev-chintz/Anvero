import { useId } from 'react';

/**
 * Anvero's mark (DECISIONS.md, 2026-09-30, "The logo", and docs/brand/): an A whose navy top
 * is crossed by a wave running into a teal arrow up and to the right. The same drawing is
 * `public/favicon.svg`. Its colours are the brand's own, the same in both looks; only the
 * navy turns white on a dark page, as the brand's negative version does. Decorative wherever
 * it sits beside the name.
 */
export function AnveroLogo({ size = 28, className }: { size?: number; className?: string }) {
  // the wave is drawn once in teal and once more in navy, cut to its left part; the cut
  // needs an id of its own for every mark on the page
  const clip = `anvero-wave-${useId().replace(/:/g, '')}`;
  const wave =
    'M42 722 C110 610 220 540 360 495 C482 452 612 410 686 292 L765 188 L700 112 Q692 100 707 97 ' +
    'L972 46 Q990 43 988 62 L964 320 Q961 338 946 329 L868 282 C815 385 725 480 590 545 ' +
    'C455 605 290 612 215 722 Z';
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 -130 1020 1020"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <clipPath id={clip}>
          <path d="M-20 -20 L650 -20 L640 330 C600 450 520 540 390 610 L300 800 L-20 800 Z" />
        </clipPath>
      </defs>
      <path
        fill="var(--brand-ink)"
        d="M170 495 L412 44 Q416 38 424 38 L516 38 Q524 38 528 45 L645 255 L545 350 L470 232 L372 418 Q262 440 170 495 Z"
      />
      <path fill="var(--brand-teal)" d={wave} />
      <path fill="var(--brand-ink)" clipPath={`url(#${clip})`} d={wave} />
      <path fill="var(--brand-teal)" d="M632 548 L760 448 L912 705 Q920 722 900 722 L792 722 Q780 722 774 712 Z" />
    </svg>
  );
}

/** The name as the logo writes it, and under it, where there is room, what Anvero is. */
export function AnveroWordmark({ tagline = false }: { tagline?: boolean }) {
  return (
    <span className="anvero-wordmark">
      {/* capitals by CSS, so a screen reader says the name rather than spelling it */}
      <span className="anvero-wordmark-name">Anvero</span>
      {tagline && <span className="anvero-wordmark-tagline">Sales Management System</span>}
    </span>
  );
}
