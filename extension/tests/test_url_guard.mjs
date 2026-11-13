// Tests for the post_url allowlist used before opening + injecting into tabs.
import { isAllowedPostUrl } from "../src/url-guard.js";

let failures = 0;
const ok = (cond, label) => {
  if (!cond) {
    failures++;
    console.error("FAIL:", label);
  }
};

for (const good of [
  "https://x.com/someone",
  "https://x.com/someone/status/123",
  "https://www.linkedin.com/feed/update/urn:li:activity:1/",
  "https://bsky.app/profile/me.bsky.social/post/abc",
  "https://mastodon.social/@me/1",
]) {
  ok(isAllowedPostUrl(good), `allows ${good}`);
}

for (const bad of [
  null,
  "",
  "not a url",
  "javascript:alert(1)",
  "data:text/html,<script>alert(1)</script>",
  "file:///etc/passwd",
  "chrome://settings",
  "http://x.com/someone",
  "https://x.com.evil.example/",
  "https://evilx.com/",
  "https://user:pw@x.com/",
  "https://x.com:8443/",
  "https://example.com/",
  "http://localhost:8000/drafts",
]) {
  ok(!isAllowedPostUrl(bad), `rejects ${bad}`);
}

if (failures) {
  console.error(`${failures} url-guard test(s) failed`);
  process.exit(1);
}
console.log("OK — url-guard tests passed");
