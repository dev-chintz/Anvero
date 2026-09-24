import { useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";

// how large the picture is shown, and how far from the pointer
const PREVIEW_SIZE = 320;
const PREVIEW_GAP = 16;

interface ItemThumbProps {
  src: string;
  className?: string;
}

/**
 * An item's small picture that shows a large one beside the pointer while it is
 * over it.
 *
 * The large picture is drawn on the page itself, not inside the table, so the
 * table's scrolling cannot cut it off, and it flips to the pointer's other side
 * near the edge of the window. It ignores the pointer, so it never takes the
 * hover from the thumbnail and flickers.
 */
export function ItemThumb({ src, className }: ItemThumbProps) {
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);

  const follow = (event: MouseEvent) => setPointer({ x: event.clientX, y: event.clientY });

  return (
    <>
      <img
        src={src}
        alt=""
        loading="lazy"
        className={className}
        onMouseEnter={follow}
        onMouseMove={follow}
        onMouseLeave={() => setPointer(null)}
      />
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
    </>
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
