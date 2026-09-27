import { useState, type MouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

// how large the picture is shown, and how far from the pointer
const PREVIEW_SIZE = 320;
const PREVIEW_GAP = 16;

interface ItemThumbProps {
  src: string;
  className?: string;
  /**
   * Rendered right after the thumbnail, sharing its hover area: hovering this too shows the
   * enlarged preview, so a caller with a name beside the picture (the order's item list) is not
   * limited to the small picture itself as the only spot that triggers it - which put the
   * pointer, and so the enlarged preview beside it, right over the SKU next to the thumbnail.
   */
  children?: ReactNode;
}

/**
 * An item's small picture that shows a large one beside the pointer while the pointer is
 * over it, or over anything passed as `children`.
 *
 * The large picture is drawn on the page itself, not inside the table, so the
 * table's scrolling cannot cut it off, and it flips to the pointer's other side
 * near the edge of the window. It ignores the pointer, so it never takes the
 * hover from the thumbnail and flickers.
 */
export function ItemThumb({ src, className, children }: ItemThumbProps) {
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);

  const follow = (event: MouseEvent) => setPointer({ x: event.clientX, y: event.clientY });

  return (
    // display: contents (index.css): owns the hover area and the portal, never a box of its
    // own, so a caller passing no children gets exactly the layout it had before.
    <span className="item-thumb-hover" onMouseEnter={follow} onMouseMove={follow} onMouseLeave={() => setPointer(null)}>
      <img src={src} alt="" loading="lazy" className={className} />
      {children}
      {pointer &&
        createPortal(
          <img
            src={src}
            alt=""
            className="thumb-preview"
            style={previewPosition(pointer)}
            width={PREVIEW_SIZE}
            height={PREVIEW_SIZE}
          />,
          document.body,
        )}
    </span>
  );
}

/** Beside the pointer, on the side with room, and inside the window vertically. */
function previewPosition({ x, y }: { x: number; y: number }): { left: number; top: number } {
  const room = window.innerWidth - x - PREVIEW_GAP;
  const left = room >= PREVIEW_SIZE ? x + PREVIEW_GAP : Math.max(0, x - PREVIEW_GAP - PREVIEW_SIZE);
  const top = Math.min(
    Math.max(0, y - PREVIEW_SIZE / 2),
    Math.max(0, window.innerHeight - PREVIEW_SIZE),
  );
  return { left, top };
}
