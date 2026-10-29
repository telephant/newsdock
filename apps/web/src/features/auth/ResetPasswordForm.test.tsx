// TC-17 (AC-16), second step: the code and a new password.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ResetPasswordForm } from "./ResetPasswordForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });

function setup(respond: () => Response | Promise<Response>, email = "a@x.io") {
  const fetchMock = vi.fn<
    (url: string, init?: RequestInit) => Promise<Response>
  >(async () => respond());
  vi.stubGlobal("fetch", fetchMock);
  render(<ResetPasswordForm initialEmail={email} />);
  return fetchMock;
}

function submit(code = "123456", password = "a-brand-new-password") {
  fireEvent.change(screen.getByLabelText("Code"), { target: { value: code } });
  fireEvent.change(screen.getByLabelText("New password"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

test("the email is prefilled and the code field suits one-time codes", () => {
  setup(() => json({}));
  expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe(
    "a@x.io",
  );
  const code = screen.getByLabelText("Code");
  expect(code.getAttribute("inputmode")).toBe("numeric");
  expect(code.getAttribute("autocomplete")).toBe("one-time-code");
  expect(
    screen.getByLabelText("New password").getAttribute("autocomplete"),
  ).toBe("new-password");
});

test("a 204 shows 'Password changed' with a link to log in", async () => {
  const fetchMock = setup(() => new Response(null, { status: 204 }));
  submit();
  const note = await screen.findByRole("status");
  expect(note.textContent).toMatch(/password changed/i);
  expect(
    screen.getByRole("link", { name: /log in/i }).getAttribute("href"),
  ).toBe("/login");
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("http://127.0.0.1:8000/api/auth/reset-password");
  expect(JSON.parse(String(init?.body))).toEqual({
    email: "a@x.io",
    code: "123456",
    password: "a-brand-new-password",
  });
});

test("a 400 shows the uniform text with a link to request a new code", async () => {
  setup(() => json({ detail: "invalid_or_expired_code" }, 400));
  submit();
  expect((await screen.findByRole("alert")).textContent).toMatch(
    /wrong or has expired/i,
  );
  expect(
    screen
      .getByRole("link", { name: /request a new code/i })
      .getAttribute("href"),
  ).toBe("/forgot-password");
  expect(
    (screen.getByLabelText("New password") as HTMLInputElement).value,
  ).toBe("");
});

test.each([
  [422, { detail: "invalid_password" }, {}, /password/i],
  [
    429,
    { detail: "too_many_reset_attempts" },
    { "retry-after": "30" },
    /30 seconds/,
  ],
  [503, { detail: "password_reset_unavailable" }, {}, /not available/i],
])("status %s shows its message", async (status, body, headers, pattern) => {
  setup(() => json(body, status, headers));
  submit();
  expect((await screen.findByRole("alert")).textContent).toMatch(pattern);
  expect(screen.queryByRole("status")).toBeNull();
});
