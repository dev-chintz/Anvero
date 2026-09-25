import { useCallback, useState } from "react";

// whether the menu is unfolded is the operator's choice, kept in the browser
const SIDEBAR_KEY = "sidebar.open";

// below this width the menu is a narrow strip that unfolds over the page instead
// of pushing it aside (Sidebar.css, App.css)
const NARROW_QUERY = "(max-width: 768px)";

/** Whether the window is narrow enough for the menu to unfold over the page. */
export function isNarrowWindow(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(NARROW_QUERY).matches;
}

function initialOpen(): boolean {
  try {
    const stored = localStorage.getItem(SIDEBAR_KEY);
    if (stored === "true") return true;
    if (stored === "false") return false;
  } catch {
    // no stored choice: fall through to the default
  }
  // nothing chosen yet: unfolded beside the page, folded on a phone
  return !isNarrowWindow();
}

/**
 * Whether the menu is unfolded, and a way to flip it.
 *
 * Held above both the menu and the page, since the page makes room for exactly
 * as much as the menu takes.
 */
export function useSidebarOpen(): [boolean, () => void] {
  const [open, setOpen] = useState(initialOpen);

  const toggle = useCallback(() => {
    setOpen((current) => {
      const next = !current;
      try {
        localStorage.setItem(SIDEBAR_KEY, String(next));
      } catch {
        // the choice still holds for this visit
      }
      return next;
    });
  }, []);

  return [open, toggle];
}
