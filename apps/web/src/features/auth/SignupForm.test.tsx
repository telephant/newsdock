// TC-21 (AC-8): the sign-up form.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SignupForm } from "./SignupForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

function setup(respond: () => Response) {
  const fetchMock = vi.fn<
    (url: string, init?: RequestInit) => Promise<Response>
  >(async () => respond());
  vi.stubGlobal("fetch", fetchMock);
  const navigate = vi.fn();
  render(<SignupForm navigate={navigate} />);
  return { fetchMock, navigate };
}

function submit(email = "new@x.io", password = "correct-horse-battery") {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: email },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
}

test("a successful sign-up goes to the login page", async () => {
  const { fetchMock, navigate } = setup(() =>
    json({ id: "u", email: "new@x.io", role: "viewer" }, 201),
  );
  submit();
  await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/login"));
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("http://127.0.0.1:8000/api/auth/signup");
  expect(init?.method).toBe("POST");
  expect(JSON.parse(String(init?.body))).toEqual({
    email: "new@x.io",
    password: "correct-horse-battery",
  });
});

test.each([
  [409, "email_taken", /already registered/i],
  [422, "invalid_email", /valid email address/i],
  [422, "invalid_password", /10 to 128 characters/i],
  [403, "signup_closed", /sign-up is closed/i],
])(
  "%s %s shows a clear message and stays on the form",
  async (status, detail, text) => {
    const { navigate } = setup(() => json({ detail }, status));
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(text);
    expect(navigate).not.toHaveBeenCalled();
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe(
      "new@x.io",
    );
  },
);

test("an unreachable server is reported", async () => {
  setup(() => {
    throw new TypeError("Failed to fetch");
  });
  submit();
  expect((await screen.findByRole("alert")).textContent).toMatch(
    /cannot reach/i,
  );
});

test("an unexpected code is plain text, and the form offers a way back to login", async () => {
  setup(() => json({ detail: "<b>boom</b>" }, 500));
  submit();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("<b>boom</b>");
  expect(alert.querySelector("b")).toBeNull();
  expect(
    screen.getByRole("link", { name: /log in/i }).getAttribute("href"),
  ).toBe("/login");
  expect(screen.getByLabelText("Password").getAttribute("autocomplete")).toBe(
    "new-password",
  );
});

// TC-9 (AC-6): the error belongs to the form and the fields; pending is visible.
test("the error is inside the form and marks both fields invalid", async () => {
  setup(() => json({ detail: "email_taken" }, 409));
  const email = screen.getByLabelText("Email");
  expect(email.getAttribute("aria-invalid")).toBeNull();
  submit();
  const alert = await screen.findByRole("alert");
  expect(alert.closest("form")).not.toBeNull();
  for (const field of [email, screen.getByLabelText("Password")]) {
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.getAttribute("aria-describedby")).toBe(alert.id);
  }
});

test("while in flight the button reads 'Signing up…' and the form is busy", async () => {
  setup(() => new Promise<Response>(() => {}) as never);
  submit();
  const button = await screen.findByRole("button", { name: "Signing up…" });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  expect(
    screen.getByRole("form", { name: "sign up" }).getAttribute("aria-busy"),
  ).toBe("true");
});
