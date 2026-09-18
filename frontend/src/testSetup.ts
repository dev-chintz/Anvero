import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// Without this, React Testing Library only auto-unmounts between tests when
// `afterEach` is a global (vitest's `test.globals`), which this project does
// not enable — so a render from one test stayed in the document for the next.
afterEach(() => {
  cleanup();
});
