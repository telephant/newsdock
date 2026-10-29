// TC-21 (AC-8): the login form. Messages are text nodes, never HTML.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { LoginForm } from "./LoginForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });

function setup(respond: () => Response | Promise<Response>, next = "/") {
  const fetchMock = vi.fn<
    (url: string, init?: RequestInit) => Promise<Response>
  >(async () => respond());
  vi.stubGlobal("fetch", fetchMock);
  const navigate = vi.fn();
  render(<LoginForm next={next} navigate={navigate} />);
  return { fetchMock, navigate };
}

function submit(email = "a@x.io", password = "correct-horse-battery") {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: email },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
}

test("a good login posts the credentials and goes to the page asked for", async () => {
  const { fetchMock, navigate } = setup(
    () => json({ id: "u", email: "a@x.io", role: "viewer" }),
    "/live",
  );
  submit();
  await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/live"));
  const [url, init] = fetchMock.mock.calls.filter(
    ([u]) => !u.endsWith("/api/auth/options"),
  )[0];
  expect(url).toBe("http://127.0.0.1:8000/api/auth/login");
  expect(init?.method).toBe("POST");
  expect(init?.credentials).toBe("include");
  expect(JSON.parse(String(init?.body))).toEqual({
    email: "a@x.io",
    password: "correct-horse-battery",
  });
});

test("the default destination is the feed", async () => {
  const { navigate } = setup(() =>
    json({ id: "u", email: "a@x.io", role: "owner" }),
  );
  submit();
  await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/"));
});

test("a 401 shows one generic message, keeps the email and clears the password", async () => {
  const { navigate } = setup(() =>
    json({ detail: "invalid_credentials" }, 401),
  );
  submit("who@x.io", "wrong-password-1");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toMatch(/wrong email or password/i);
  expect(navigate).not.toHaveBeenCalled();
  expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe(
    "who@x.io",
  );
  expect((screen.getByLabelText("Password") as HTMLInputElement).value).toBe(
    "",
  );
});

test("a 429 says how long to wait", async () => {
  setup(() =>
    json({ detail: "too_many_attempts" }, 429, { "retry-after": "12" }),
  );
  submit();
  expect((await screen.findByRole("alert")).textContent).toContain(
    "12 seconds",
  );
  cleanup();
  setup(() =>
    json({ detail: "too_many_attempts" }, 429, { "retry-after": "600" }),
  );
  submit();
  expect((await screen.findByRole("alert")).textContent).toContain(
    "10 minutes",
  );
});

test("an unreachable server is reported without blaming the password", async () => {
  setup(() => {
    throw new TypeError("Failed to fetch");
  });
  submit();
  expect((await screen.findByRole("alert")).textContent).toMatch(
    /cannot reach/i,
  );
});

test("a malformed answer (422) asks for a valid email and password", async () => {
  setup(() => json({ detail: "invalid_email" }, 422));
  submit("not-an-email", "x");
  expect((await screen.findByRole("alert")).textContent).toMatch(
    /valid email and password/i,
  );
});

test("an unexpected error code is shown as plain text, never as HTML", async () => {
  setup(() => json({ detail: "<img src=x onerror=alert(1)>" }, 500));
  submit();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("<img src=x onerror=alert(1)>");
  expect(alert.querySelector("img")).toBeNull();
});

test("the button is disabled while a login is in flight (no double submit)", async () => {
  let release: (r: Response) => void = () => {};
  const { fetchMock } = setup(
    () => new Promise<Response>((resolve) => (release = resolve)) as never,
  );
  submit();
  const button = screen.getByRole("button", { name: /log in|logging in/i });
  await vi.waitFor(() =>
    expect((button as HTMLButtonElement).disabled).toBe(true),
  );
  fireEvent.click(button);
  expect(
    fetchMock.mock.calls.filter(([u]) => u.endsWith("/api/auth/login")),
  ).toHaveLength(1);
  release(json({ detail: "invalid_credentials" }, 401));
  await screen.findByRole("alert");
});

test("the form links to sign-up and uses password-manager friendly fields", () => {
  setup(() => json({}));
  expect(
    screen.getByRole("link", { name: /sign up/i }).getAttribute("href"),
  ).toBe("/signup");
  expect(screen.getByLabelText("Email").getAttribute("autocomplete")).toBe(
    "username",
  );
  expect(screen.getByLabelText("Password").getAttribute("autocomplete")).toBe(
    "current-password",
  );
});

// TC-9 (AC-6): the error belongs to the form and the fields; pending is visible.
test("the error is inside the form and marks both fields invalid", async () => {
  setup(() => json({ detail: "invalid_credentials" }, 401));
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

// TC-16 (AC-15): the link shows only when the server says the feature is on.
function withOptions(answer: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (url: string) =>
    String(url).endsWith("/api/auth/options") ? answer() : json({}),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<LoginForm next="/" navigate={vi.fn()} />);
  return fetchMock;
}

test("the forgot-password link appears when the options say enabled", async () => {
  withOptions(() => json({ password_reset_enabled: true }));
  const link = await screen.findByRole("link", { name: /forgot password/i });
  expect(link.getAttribute("href")).toBe("/forgot-password");
});

test.each([
  ["disabled", () => json({ password_reset_enabled: false })],
  ["an error", () => json({ detail: "x" }, 500)],
  [
    "no answer",
    () => {
      throw new TypeError("Failed to fetch");
    },
  ],
])("no forgot-password link when the options give %s", async (_n, answer) => {
  const fetchMock = withOptions(answer);
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
  await new Promise((r) => setTimeout(r, 0));
  expect(screen.queryByRole("link", { name: /forgot password/i })).toBeNull();
});

test("while in flight the button reads 'Logging in…' and the form is busy", async () => {
  setup(() => new Promise<Response>(() => {}) as never);
  submit();
  const button = await screen.findByRole("button", { name: "Logging in…" });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  expect(
    screen.getByRole("form", { name: "log in" }).getAttribute("aria-busy"),
  ).toBe("true");
});
