// TC-38 (AC-15): the live feed page. It opens one credentialed EventSource, shows
// newest first, escapes titles, closes on unmount and says when it is reconnecting.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ArticleSummary } from "@/features/feed/api";
import { Live, type EventSourceLike } from "./Live";

class FakeSource implements EventSourceLike {
  listeners: Record<string, Array<(event: { data: string }) => void>> = {};
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0; // CONNECTING
  closed = false;
  constructor(
    readonly url: string,
    readonly init?: { withCredentials?: boolean },
  ) {}
  addEventListener(type: string, listener: (event: { data: string }) => void) {
    (this.listeners[type] ??= []).push(listener);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  emit(
    article: Partial<ArticleSummary> & { article_id: string },
    raw?: string,
  ) {
    const data = raw ?? JSON.stringify(summary(article));
    for (const listener of this.listeners["article"] ?? []) listener({ data });
  }
  failWhileReconnecting() {
    this.readyState = 0;
    this.onerror?.();
  }
  failForGood() {
    this.readyState = 2;
    this.onerror?.();
  }
}

const summary = (
  over: Partial<ArticleSummary> & { article_id: string },
): ArticleSummary => ({
  title: `Title ${over.article_id}`,
  url: `https://example.com/${over.article_id}`,
  domain: "example.com",
  published_at: "2026-10-27T10:00:00Z",
  themes: [],
  scores: null,
  source_count: 1,
  ...over,
});

let sources: FakeSource[] = [];
const createSource = (url: string, init?: { withCredentials?: boolean }) => {
  const source = new FakeSource(url, init);
  sources.push(source);
  return source;
};

beforeEach(() => {
  sources = [];
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const current = () => sources[sources.length - 1];
const titles = () =>
  screen.queryAllByRole("link").map((link) => link.textContent);

// TC-12, TC-13, TC-19 (AC-8, AC-13): status dot, reduced-motion-safe entrance, empty state.
const dot = () => document.querySelector('[data-slot="status-dot"]');

test("a status dot follows connecting, live, reconnecting and closed", () => {
  render(
    <Live
      createSource={createSource}
      deps={{
        fetch: async () =>
          new Response(
            JSON.stringify({ id: "u", email: "a@x.io", role: "viewer" }),
            {
              status: 200,
            },
          ),
      }}
    />,
  );
  expect(dot()?.getAttribute("data-state")).toBe("connecting");
  act(() => current().open());
  expect(dot()?.getAttribute("data-state")).toBe("live");
  act(() => current().failWhileReconnecting());
  expect(dot()?.getAttribute("data-state")).toBe("reconnecting");
  act(() => current().failForGood());
  expect(dot()?.getAttribute("data-state")).toBe("closed");
  expect(screen.getByRole("button", { name: "Reconnect" })).toBeTruthy();
});

test("the dot is decoration: the status text alone carries the meaning", () => {
  render(<Live createSource={createSource} />);
  expect(dot()?.getAttribute("aria-hidden")).toBe("true");
  expect(screen.getAllByRole("status")).toHaveLength(1);
});

test("new articles animate in only when motion is allowed", () => {
  render(<Live createSource={createSource} />);
  act(() => current().open());
  act(() => current().emit({ article_id: "a1" }));
  const item = screen.getByRole("link", { name: "Title a1" }).closest("li");
  const classes = (item?.className ?? "").split(/\s+/);
  expect(classes.some((c) => c.startsWith("motion-safe:animate-in"))).toBe(
    true,
  );
  // nothing animates unconditionally
  expect(
    classes.filter((c) => /^(animate-|fade-|slide-|zoom-)/.test(c)),
  ).toEqual([]);
});

test("with no articles yet a friendly empty state waits for the first one", () => {
  render(<Live createSource={createSource} />);
  act(() => current().open());
  expect(
    screen
      .getByText(/waiting for new articles/i)
      .closest('[data-slot="empty-state"]'),
  ).not.toBeNull();
  act(() => current().emit({ article_id: "a1" }));
  expect(screen.queryByText(/waiting for new articles/i)).toBeNull();
});

test("opens one credentialed stream on the configured API", () => {
  render(<Live createSource={createSource} />);
  expect(sources).toHaveLength(1);
  expect(current().url).toBe("http://127.0.0.1:8000/api/live");
  expect(current().init?.withCredentials).toBe(true);
});

test("says it is connecting, then live, and waits for articles", () => {
  render(<Live createSource={createSource} />);
  expect(screen.getByRole("status").textContent).toMatch(/connecting/i);
  act(() => current().open());
  expect(screen.getByRole("status").textContent).toMatch(/live/i);
  expect(screen.getByText(/waiting for new articles/i)).toBeTruthy();
});

test("each new article is put first, without a reload", () => {
  render(<Live createSource={createSource} />);
  act(() => current().open());
  act(() => current().emit({ article_id: "a1" }));
  act(() => current().emit({ article_id: "a2" }));
  expect(titles()).toEqual(["Title a2", "Title a1"]);
  expect(
    screen.getByRole("link", { name: "Title a2" }).getAttribute("href"),
  ).toBe("/articles/a2");
  expect(screen.queryByText(/waiting for new articles/i)).toBeNull();
});

test("an article that arrives twice (a reconnect replay) is listed once", () => {
  render(<Live createSource={createSource} />);
  act(() => current().emit({ article_id: "a1" }));
  act(() => current().emit({ article_id: "a1" }));
  expect(titles()).toEqual(["Title a1"]);
});

test("titles are text, never markup", () => {
  const { container } = render(<Live createSource={createSource} />);
  act(() =>
    current().emit({
      article_id: "x",
      title: "<script>alert('xss')</script><img src=x onerror=alert(1)>",
    }),
  );
  expect(
    screen.getByText(
      "<script>alert('xss')</script><img src=x onerror=alert(1)>",
    ),
  ).toBeTruthy();
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
});

test("a malformed event is ignored and the stream keeps working", () => {
  render(<Live createSource={createSource} />);
  act(() => current().emit({ article_id: "bad" }, "not json {"));
  act(() => current().emit({ article_id: "bad" }, JSON.stringify({ nope: 1 })));
  act(() => current().emit({ article_id: "ok" }));
  expect(titles()).toEqual(["Title ok"]);
});

test("the list is bounded so a long-open tab does not grow forever", () => {
  render(<Live createSource={createSource} />);
  act(() => {
    for (let i = 0; i < 230; i++) current().emit({ article_id: `n${i}` });
  });
  expect(titles()).toHaveLength(200);
  expect(titles()[0]).toBe("Title n229"); // newest kept, oldest dropped
});

test("leaving the page closes the stream", () => {
  const { unmount } = render(<Live createSource={createSource} />);
  expect(current().closed).toBe(false);
  unmount();
  expect(current().closed).toBe(true);
});

test("a dropped connection is shown as reconnecting, and recovers on its own", () => {
  render(<Live createSource={createSource} />);
  act(() => current().open());
  act(() => current().failWhileReconnecting());
  expect(screen.getByRole("status").textContent).toMatch(/reconnecting/i);
  expect(current().closed).toBe(false); // the browser retries with Last-Event-ID
  act(() => current().open());
  expect(screen.getByRole("status").textContent).toMatch(/live/i);
});

test("a stream that closed for good checks the session: a lost one goes to /login", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () => new Response('{"detail":"unauthorized"}', { status: 401 }),
    ),
  );
  const navigate = vi.fn();
  render(
    <Live
      createSource={createSource}
      deps={{ navigate, location: () => ({ pathname: "/live", search: "" }) }}
    />,
  );
  act(() => current().failForGood());
  await vi.waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/login?next=%2Flive"),
  );
});

test("a stream that closed for good with a valid session offers a manual reconnect", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({ id: "u", email: "a@x.io", role: "viewer" }),
          {
            status: 200,
          },
        ),
    ),
  );
  const navigate = vi.fn();
  render(<Live createSource={createSource} deps={{ navigate }} />);
  const first = current();
  act(() => first.failForGood());
  fireEvent.click(await screen.findByRole("button", { name: "Reconnect" }));
  expect(navigate).not.toHaveBeenCalled();
  expect(first.closed).toBe(true);
  expect(sources).toHaveLength(2);
  expect(current().init?.withCredentials).toBe(true);
  expect(screen.getByRole("status").textContent).toMatch(/connecting/i);
});
