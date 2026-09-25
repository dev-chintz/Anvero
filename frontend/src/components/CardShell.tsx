interface CardShellProps {
  title: string;
  /** Extra classes for the card (its own name, so styles and tests can find it). */
  className?: string;
  /** Inside another card or a section of the page: no frame and no heading of its own. */
  embedded?: boolean;
  children: React.ReactNode;
}

/**
 * The frame of a card on the order page: a titled, bordered section, or, when the page
 * already gives it a place and a heading (a tab, a folded section), just its content
 * as a labelled group. Lets a card serve both without two copies of it.
 */
export function CardShell({ title, className = "", embedded = false, children }: CardShellProps) {
  if (embedded) {
    return (
      <div role="group" className={`embedded-card ${className}`.trim()} aria-label={title}>
        {children}
      </div>
    );
  }
  return (
    <section className={`order-card ${className}`.trim()} aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
