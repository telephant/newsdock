// TC-11 (AC-7), the dialog part: destructive actions wait for an explicit yes.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useConfirm, type ConfirmFn } from "./ConfirmDialog";

afterEach(cleanup);

function Harness({
  onAnswer,
  override,
}: {
  onAnswer: (ok: boolean) => void;
  override?: ConfirmFn;
}) {
  const { confirm, dialog } = useConfirm(override);
  return (
    <>
      <button
        onClick={() =>
          void confirm("Remove <b>x</b>?", "Remove").then(onAnswer)
        }
      >
        ask
      </button>
      {dialog}
    </>
  );
}

test("no dialog is shown until a question is asked", () => {
  render(<Harness onAnswer={() => {}} />);
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("the question is shown as text with Cancel and the action button", async () => {
  render(<Harness onAnswer={() => {}} />);
  fireEvent.click(screen.getByText("ask"));
  const dialog = await screen.findByRole("alertdialog");
  expect(within(dialog).getByText("Remove <b>x</b>?")).toBeTruthy();
  expect(dialog.querySelector("b")).toBeNull(); // text, never markup
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeTruthy();
  expect(within(dialog).getByRole("button", { name: "Remove" })).toBeTruthy();
});

test("Cancel answers no and closes the dialog", async () => {
  const answer = vi.fn();
  render(<Harness onAnswer={answer} />);
  fireEvent.click(screen.getByText("ask"));
  const dialog = await screen.findByRole("alertdialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  await vi.waitFor(() => expect(answer).toHaveBeenCalledWith(false));
  await vi.waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
});

test("the action button answers yes exactly once", async () => {
  const answer = vi.fn();
  render(<Harness onAnswer={answer} />);
  fireEvent.click(screen.getByText("ask"));
  const dialog = await screen.findByRole("alertdialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
  await vi.waitFor(() => expect(answer).toHaveBeenCalledWith(true));
  await vi.waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
  expect(answer).toHaveBeenCalledTimes(1);
});

test("an injected answer replaces the dialog (tests and embedders)", async () => {
  const answer = vi.fn();
  const override = vi.fn(() => true);
  render(<Harness onAnswer={answer} override={override} />);
  fireEvent.click(screen.getByText("ask"));
  await vi.waitFor(() => expect(answer).toHaveBeenCalledWith(true));
  expect(override).toHaveBeenCalledWith("Remove <b>x</b>?", "Remove");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});
