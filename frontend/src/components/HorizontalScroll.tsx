import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "../i18n";

/**
 * A wide table that scrolls sideways, with its scrollbar kept at the bottom edge
 * of the window while the table is in view.
 *
 * A scrollbar under a table of twenty rows is a page away, and the columns on the
 * right cannot be reached until it is. The table's own scrollbar is hidden and a
 * second one, as wide as the table, sticks to the bottom of the window and moves
 * the table with it (and follows it, whichever of the two moves).
 */
export function HorizontalScroll({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const contentRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [overflowing, setOverflowing] = useState(false);

  const measure = () => {
    const content = contentRef.current;
    if (!content) return;
    setWidth(content.scrollWidth);
    setOverflowing(content.scrollWidth > content.clientWidth + 1);
  };

  // the table grows and shrinks with its rows and the window
  useLayoutEffect(measure);
  useEffect(() => {
    window.addEventListener("resize", measure);
    const observer =
      typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(measure);
    if (observer && contentRef.current) {
      observer.observe(contentRef.current);
      Array.from(contentRef.current.children).forEach((child) => observer.observe(child));
    }
    return () => {
      window.removeEventListener("resize", measure);
      observer?.disconnect();
    };
  }, []);

  // each follows the other; setting the position it already has raises no event, so this ends
  const follow = (from: HTMLDivElement | null, to: HTMLDivElement | null) => {
    if (from && to && Math.abs(to.scrollLeft - from.scrollLeft) > 0.5) {
      to.scrollLeft = from.scrollLeft;
    }
  };

  return (
    <>
      <div
        ref={contentRef}
        className="table-wrapper hscroll-content"
        onScroll={() => follow(contentRef.current, barRef.current)}
        // reachable with the keyboard once there is something to scroll to
        role={overflowing ? "region" : undefined}
        aria-label={overflowing ? t("orders.tableScroll") : undefined}
        tabIndex={overflowing ? 0 : undefined}
      >
        {children}
      </div>
      <div
        ref={barRef}
        className="hscroll-bar"
        hidden={!overflowing}
        aria-hidden="true"
        data-testid="hscroll-bar"
        onScroll={() => follow(barRef.current, contentRef.current)}
      >
        <div style={{ width }} />
      </div>
    </>
  );
}
