// TC-17 (AC-16), first step: ask for a code. The answer is the same for every email.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ForgotPasswordForm } from "./ForgotPasswordForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });

function setup(respond: () => Response | Promise<Response>) {
  const fetchMock = vi.fn<
    (url: string, init?: RequestInit) => Promise<Response>
  >(async () => respond());
  vi.stubGlobal("fetch", fetchMock);
  render(<ForgotPasswordForm />);
  return fetchMock;
}

function submit(email = "a@x.io") {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: email },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send code" }));
}

test("a 202 shows the generic confirmation and a link to the code screen with the email", async () => {
  const fetchMock = setup(() => json({ ok: true }, 202));
  submit("a@x.io");
  const note = await screen.findByRole("status");
  expect(note.textContent).toMatch(/if that email has an account/i);
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("http://127.0.0.1:8000/api/auth/forgot-password");
  expect(JSON.parse(String(init?.body))).toEqual({ email: "a@x.io" });
  expect(
    screen.getByRole("link", { name: /enter the code/i }).getAttribute("href"),
  ).toBe("/reset-password?email=a%40x.io");
});

test.each([
  [422, { detail: "invalid_email" }, {}, /valid email/i],
  [
    429,
    { detail: "too_many_reset_requests" },
    { "retry-after": "600" },
    /10 minutes/,
  ],
  [503, { detail: "password_reset_unavailable" }, {}, /not available/i],
])("status %s shows its message", async (status, body, headers, pattern) => {
  setup(() => json(body, status, headers));
  submit();
  expect((await screen.findByRole("alert")).textContent).toMatch(pattern);
  expect(screen.queryByRole("status")).toBeNull();
});

test("an unreachable server is reported", async () => {
  setup(() => {
    throw new TypeError("Failed to fetch");
  });
  submit();
  expect((await screen.findByRole("alert")).textContent).toMatch(
    /cannot reach/i,
  );
});
