import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Pagination } from "./Pagination";

function renderPagination(props: Partial<Parameters<typeof Pagination>[0]> = {}) {
  const onPageChange = vi.fn();
  const onLimitChange = vi.fn();
  render(
    <Pagination
      skip={40}
      limit={20}
      count={230}
      onPageChange={onPageChange}
      onLimitChange={onLimitChange}
      {...props}
    />,
  );
  return { onPageChange, onLimitChange };
}

const pageField = () => screen.getByRole("spinbutton", { name: "Go to page" });
const submitPageField = () => fireEvent.submit(pageField().closest("form") as HTMLFormElement);

describe("the page buttons", () => {
  it("say where the list stands", () => {
    renderPagination();

    expect(pageField()).toHaveValue(3);
    expect(screen.getByText("of 12 (230 total)")).toBeInTheDocument();
  });

  it("step to the next and previous page", () => {
    const { onPageChange } = renderPagination();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));

    expect(onPageChange).toHaveBeenNthCalledWith(1, 60);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 20);
  });

  it("go to the first and the last page", () => {
    const { onPageChange } = renderPagination();

    fireEvent.click(screen.getByRole("button", { name: "First page" }));
    fireEvent.click(screen.getByRole("button", { name: "Last page" }));

    expect(onPageChange).toHaveBeenNthCalledWith(1, 0);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 220);
  });

  it("stop at the ends", () => {
    renderPagination({ skip: 0 });

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "First page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("are all off when everything fits on one page", () => {
    renderPagination({ skip: 0, count: 3 });

    for (const name of ["Previous", "Next", "First page", "Last page"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    expect(screen.getByText("of 1 (3 total)")).toBeInTheDocument();
  });
});

describe("going straight to a page", () => {
  it("goes to the number typed, on Enter", () => {
    const { onPageChange } = renderPagination();

    fireEvent.change(pageField(), { target: { value: "9" } });
    submitPageField();

    expect(onPageChange).toHaveBeenCalledWith(160);
  });

  it("goes to the number typed when the field is left", () => {
    const { onPageChange } = renderPagination();

    fireEvent.change(pageField(), { target: { value: "5" } });
    fireEvent.blur(pageField());

    expect(onPageChange).toHaveBeenCalledWith(80);
  });

  it("takes a page past the end to the last, and past the start to the first", () => {
    const { onPageChange } = renderPagination();

    fireEvent.change(pageField(), { target: { value: "99" } });
    submitPageField();
    expect(onPageChange).toHaveBeenLastCalledWith(220);
    expect(pageField()).toHaveValue(12);

    fireEvent.change(pageField(), { target: { value: "0" } });
    submitPageField();
    expect(onPageChange).toHaveBeenLastCalledWith(0);
  });

  it("does nothing for the page already open, and puts back what an empty field lost", () => {
    const { onPageChange } = renderPagination();

    fireEvent.change(pageField(), { target: { value: "3" } });
    submitPageField();
    fireEvent.change(pageField(), { target: { value: "" } });
    fireEvent.blur(pageField());

    expect(onPageChange).not.toHaveBeenCalled();
    expect(pageField()).toHaveValue(3);
  });

  it("follows the list when it moves to another page", () => {
    const { rerender } = render(<Pagination skip={0} limit={20} count={230} onPageChange={vi.fn()} />);
    expect(pageField()).toHaveValue(1);

    rerender(<Pagination skip={60} limit={20} count={230} onPageChange={vi.fn()} />);

    expect(pageField()).toHaveValue(4);
  });
});

describe("how many rows a page holds", () => {
  it("offers 20, 50, 100 and 200, and the size in use is chosen", () => {
    renderPagination({ limit: 50 });

    const select = screen.getByRole("combobox", { name: "Per page" });
    expect(select).toHaveValue("50");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toEqual([
      "20",
      "50",
      "100",
      "200",
    ]);
  });

  it("hands over the size chosen", () => {
    const { onLimitChange } = renderPagination();

    fireEvent.change(screen.getByRole("combobox", { name: "Per page" }), {
      target: { value: "100" },
    });

    expect(onLimitChange).toHaveBeenCalledWith(100);
  });

  it("keeps a size that came in the address, though it is not on offer", () => {
    renderPagination({ limit: 30, skip: 0 });

    const select = screen.getByRole("combobox", { name: "Per page" });
    expect(select).toHaveValue("30");
    expect(select.querySelectorAll("option")).toHaveLength(5);
  });

  it("is not shown when the page gave no way to change it", () => {
    renderPagination({ onLimitChange: undefined });

    expect(screen.queryByRole("combobox", { name: "Per page" })).not.toBeInTheDocument();
  });
});
