import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UsersSettings } from "./UsersSettings";
import type { User } from "../types/user";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, email: "admin@example.com", role: "admin", permissions: [] } }),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    usersApi: { list: vi.fn(), create: vi.fn(), update: vi.fn() },
  };
});

const { usersApi } = await import("../api/client");

function user(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: "admin@example.com",
    role: "admin",
    is_active: true,
    permissions: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("UsersSettings", () => {
  beforeEach(() => {
    vi.mocked(usersApi.list).mockResolvedValue([
      user(),
      user({ id: 2, email: "packer@example.com", role: "user", permissions: [{ area: "orders", level: "manage" }] }),
    ]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lists every account with its role and status, and marks the logged-in one", async () => {
    const { container } = render(<UsersSettings />);

    expect(await screen.findByText("admin@example.com (you)")).toBeInTheDocument();
    const list = within(container.querySelector(".users-list") as HTMLElement);
    expect(list.getByText("packer@example.com")).toBeInTheDocument();
    expect(list.getByText("Administrator")).toBeInTheDocument();
    expect(list.getByText("User")).toBeInTheDocument();
  });

  it("opens the first account's panel and shows its permission grid", async () => {
    render(<UsersSettings />);

    await screen.findByText("admin@example.com (you)");
    // the first account (an admin) needs no grid
    expect(screen.getByText("An administrator needs no grants: it can already do everything.")).toBeInTheDocument();

    fireEvent.click(screen.getByText("packer@example.com"));
    expect(await screen.findByRole("combobox", { name: "Orders and production" })).toHaveValue("manage");
    expect(screen.getByRole("combobox", { name: "Finance and reports" })).toHaveValue("none");
  });

  it("saves a changed grant for an existing account", async () => {
    vi.mocked(usersApi.update).mockResolvedValue(user({ id: 2, role: "user" }));
    render(<UsersSettings />);
    fireEvent.click(await screen.findByText("packer@example.com"));

    fireEvent.change(screen.getByRole("combobox", { name: "Finance and reports" }), {
      target: { value: "view" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(usersApi.update).toHaveBeenCalledWith(2, {
        role: "user",
        is_active: true,
        permissions: [
          { area: "orders", level: "manage" },
          { area: "finance", level: "view" },
        ],
      }),
    );
  });

  it("creates a new account with the permissions chosen in its grid", async () => {
    vi.mocked(usersApi.create).mockResolvedValue(user({ id: 3, email: "new@example.com", role: "user" }));
    render(<UsersSettings />);
    await screen.findByText("admin@example.com (you)");

    fireEvent.click(screen.getByText("+ Add account"));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-perfectly-good-password" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Messages" }), { target: { value: "view" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(usersApi.create).toHaveBeenCalledWith({
        email: "new@example.com",
        password: "a-perfectly-good-password",
        role: "user",
        permissions: [{ area: "messages", level: "view" }],
      }),
    );
  });

  it("refuses a short password before calling the API", async () => {
    render(<UsersSettings />);
    await screen.findByText("admin@example.com (you)");

    fireEvent.click(screen.getByText("+ Add account"));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText(/at least 12 characters/)).toBeInTheDocument();
    expect(usersApi.create).not.toHaveBeenCalled();
  });
});
