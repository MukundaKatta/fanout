// URL guard for anything the extension opens + injects scripts into.
//
// `post_url` comes back from the backend (and is ultimately user/page
// supplied), so before the outcome puller opens it in a background tab and
// runs `chrome.scripting.executeScript` against it we require:
//   - https: only (no javascript:, data:, file:, chrome:, http:)
//   - no embedded credentials
//   - host is one of the platforms the extension already holds
//     host_permissions for (exact host match, no suffix tricks).

export const POST_URL_HOSTS = new Set([
  "x.com",
  "twitter.com",
  "www.linkedin.com",
  "www.threads.net",
  "www.instagram.com",
  "bsky.app",
  "mastodon.social",
  "hachyderm.io",
  "fosstodon.org",
  "indieweb.social",
  "mas.to",
  "www.reddit.com",
  "news.ycombinator.com",
  "www.producthunt.com",
  "medium.com",
  "dev.to",
]);

export function isAllowedPostUrl(raw) {
  if (typeof raw !== "string" || !raw) return false;
  let u;
  try {
    u = new URL(raw);
  } catch {
    return false;
  }
  if (u.protocol !== "https:") return false;
  if (u.username || u.password) return false;
  if (u.port && u.port !== "443") return false;
  return POST_URL_HOSTS.has(u.hostname.toLowerCase());
}
