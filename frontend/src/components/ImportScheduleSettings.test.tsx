import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { ImportScheduleSettings } from "./ImportScheduleSettings";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    integrationsApi: { importSchedule: vi.fn(), saveImportSchedule: vi.fn() },
  };
});

const { integrationsApi } = await import("../api/client");

const field = () => screen.getByRole("spinbutton");
const save = () => screen.getByRole("button", { name: "Save" });

beforeEach(() => {
  vi.mocked(integrationsApi.importSchedule).mockResolvedValue({ interval_minutes: 15 });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("the automatic update interval", () => {
  it("shows the interval in use, and offers nothing to save until it is changed", async () => {
    render(<ImportScheduleSettings />);

    await waitFor(() => expect(field()).toHaveValue(15));
    expect(save()).toBeDisabled();
  });

  it("saves a new interval and says when it takes effect", async () => {
    vi.mocked(integrationsApi.saveImportSchedule).mockResolvedValue({ interval_minutes: 30 });
    render(<ImportScheduleSettings />);
    await waitFor(() => expect(field()).toHaveValue(15));

    fireEvent.change(field(), { target: { value: "30" } });
    fireEvent.click(save());

    await waitFor(() => expect(integrationsApi.saveImportSchedule).toHaveBeenCalledWith(30));
    expect(await screen.findByRole("status")).toHaveTextContent("takes effect within half a minute");
    expect(save()).toBeDisabled();
  });

  it("can switch it off with 0", async () => {
    vi.mocked(integrationsApi.saveImportSchedule).mockResolvedValue({ interval_minutes: 0 });
    render(<ImportScheduleSettings />);
    await waitFor(() => expect(field()).toHaveValue(15));

    fireEvent.change(field(), { target: { value: "0" } });
    fireEvent.click(save());

    await waitFor(() => expect(integrationsApi.saveImportSchedule).toHaveBeenCalledWith(0));
  });

  it("refuses an interval the backend would, without asking it", async () => {
    render(<ImportScheduleSettings />);
    await waitFor(() => expect(field()).toHaveValue(15));

    for (const bad of ["3", "1441", "2.5", ""]) {
      fireEvent.change(field(), { target: { value: bad } });
      fireEvent.submit(field().closest("form") as HTMLFormElement);
      expect(await screen.findByRole("alert")).toHaveTextContent("Enter 0 (off) or a number of minutes from 5 to 1440.");
    }
    expect(integrationsApi.saveImportSchedule).not.toHaveBeenCalled();
  });

  it("shows the backend's own refusal", async () => {
    vi.mocked(integrationsApi.saveImportSchedule).mockRejectedValue(new ApiError(422, "not allowed"));
    render(<ImportScheduleSettings />);
    await waitFor(() => expect(field()).toHaveValue(15));

    fireEvent.change(field(), { target: { value: "20" } });
    fireEvent.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("not allowed");
  });

  it("says so when the interval cannot be read, and leaves the field alone", async () => {
    vi.mocked(integrationsApi.importSchedule).mockRejectedValue(new Error("down"));
    render(<ImportScheduleSettings />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not read the interval.");
    expect(field()).toBeDisabled();
  });
});
