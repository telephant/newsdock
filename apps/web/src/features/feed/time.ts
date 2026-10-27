// Relative time for feed cards ("5 minutes ago"); pure, the clock is a parameter.
// The full local date stays available in the element's title attribute.
const relative = new Intl.RelativeTimeFormat("en", { numeric: "always" });

const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;

export function timeAgo(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((now - then) / 1000);
  if (seconds < MINUTE) return "just now"; // also small clock skew (future times)
  if (seconds < HOUR)
    return relative.format(-Math.floor(seconds / MINUTE), "minute");
  if (seconds < DAY)
    return relative.format(-Math.floor(seconds / HOUR), "hour");
  if (seconds < 7 * DAY)
    return relative.format(-Math.floor(seconds / DAY), "day");
  const sameYear = new Date(then).getFullYear() === new Date(now).getFullYear();
  return new Date(then).toLocaleDateString("en", {
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
  });
}
