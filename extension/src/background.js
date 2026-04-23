// Fanout background worker: polls backend for queued posts, dispatches to platform handlers.

const DEFAULT_API = "http://localhost:8000";
const POLL_ALARM = "fanout-poll";

// Per-platform routing: which tab pattern to find/open, OR which compose URL to open
// for "copy & open" platforms that the extension can't fully drive.
const PLATFORM_TARGETS = {
  // Auto-post via content script
  x:        { tabs: ["https://x.com/*", "https://twitter.com/*"], open: "https://x.com/home" },
  linkedin: { tabs: ["https://www.linkedin.com/*"],               open: "https://www.linkedin.com/feed/" },
  threads:  { tabs: ["https://www.threads.net/*"],                open: "https://www.threads.net/" },
  instagram:{ tabs: ["https://www.instagram.com/*"],              open: "https://www.instagram.com/" },
  bluesky:  { tabs: ["https://bsky.app/*"],                       open: "https://bsky.app/" },
  mastodon: {
    tabs: [
      "https://mastodon.social/*",
      "https://hachyderm.io/*",
      "https://fosstodon.org/*",
      "https://indieweb.social/*",
      "https://mas.to/*",
    ],
    open: "https://mastodon.social/home",
  },
  // Reddit: URL-prefill the title via ?title= query param, copy body to clipboard.
  // Avoids brittle DOM scraping; user picks a subreddit and pastes the body.
  reddit:   { redditPrefill: true },

  // Copy-to-clipboard + open compose URL (no content script — user pastes)
  hackernews:  { copyOpen: "https://news.ycombinator.com/submit" },
  producthunt: { copyOpen: "https://www.producthunt.com/posts/new" },
  medium:      { copyOpen: "https://medium.com/new-story" },
  devto:       { copyOpen: "https://dev.to/new" },
  telegram:    { copyOpen: "https://web.telegram.org/" },
  discord:     { copyOpen: "https://discord.com/channels/@me" },
  slack:       { copyOpen: "https://app.slack.com/" },

  // Email gets a mailto: link (handled in dispatch)
  email: { mailto: true },
};

async function getConfig() {
  const { apiUrl, enabled, jwt } = await chrome.storage.local.get(["apiUrl", "enabled", "jwt"]);
  return {
    apiUrl: apiUrl || DEFAULT_API,
    enabled: enabled !== false,
    jwt: jwt || "",
  };
}

function authHeaders(jwt) {
  return jwt ? { Authorization: `Bearer ${jwt}` } : {};
}

async function report(draftId, { postUrl, error, info }) {
  const { apiUrl, jwt } = await getConfig();
  try {
    await fetch(`${apiUrl}/posted`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(jwt) },
      body: JSON.stringify({
        draft_id: draftId,
        post_url: postUrl ?? null,
        // info = "needs_user_action" (copy & open) is not an error; only real
        // failures should mark the draft failed in the backend.
        error: error ?? null,
      }),
    });
  } catch (e) {
    console.warn("Fanout: report failed", e);
  }
}

async function findOrOpenTab(urlPatterns, openUrl) {
  const tabs = await chrome.tabs.query({ url: urlPatterns });
  if (tabs.length > 0) return tabs[0];
  return await chrome.tabs.create({ url: openUrl, active: false });
}

function splitEmail(text) {
  const lines = text.split("\n");
  const subject = lines[0].replace(/^SUBJECT:\s*/i, "").trim();
  const body = lines.slice(1).join("\n").trim();
  return { subject, body };
}

function splitTitleBody(text) {
  const lines = text.split("\n");
  const title = lines[0].replace(/^TITLE:\s*/i, "").trim();
  const body = lines.slice(1).join("\n").trim();
  return { title, body };
}

async function copyToTabClipboard(tabId, text) {
  // chrome.scripting.executeScript runs in the page; navigator.clipboard works there.
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: async (txt) => {
        try { await navigator.clipboard.writeText(txt); return true; }
        catch { return false; }
      },
      args: [text],
    });
    return true;
  } catch {
    return false;
  }
}

async function waitForTabLoad(tabId, { timeout = 15000 } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const onUpdated = (id, info) => {
      if (id === tabId && info.status === "complete" && !done) {
        done = true;
        chrome.tabs.onUpdated.removeListener(onUpdated);
        resolve();
      }
    };
    chrome.tabs.onUpdated.addListener(onUpdated);
    setTimeout(() => {
      if (!done) {
        done = true;
        chrome.tabs.onUpdated.removeListener(onUpdated);
        resolve();
      }
    }, timeout);
  });
}

async function dispatch(item) {
  const { platform, draft_id, content } = item;
  const target = PLATFORM_TARGETS[platform];
  if (!target) {
    await report(draft_id, { error: `Unsupported platform: ${platform}` });
    return;
  }

  try {
    // mailto: handler — open a compose window and we're done.
    if (target.mailto) {
      const { subject, body } = splitEmail(content);
      const url = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
      await chrome.tabs.create({ url, active: true });
      await report(draft_id, { info: "needs_user_action: email composer opened" });
      return;
    }

    // Copy-and-open platforms — copy content to clipboard, open the compose URL.
    if (target.copyOpen) {
      const tab = await chrome.tabs.create({ url: target.copyOpen, active: true });
      await waitForTabLoad(tab.id);
      const ok = await copyToTabClipboard(tab.id, content);
      await report(draft_id, {
        info: ok
          ? "needs_user_action: content copied to clipboard, paste into the open form"
          : "needs_user_action: opened compose page; copy from Fanout dashboard",
      });
      return;
    }

    // Reddit special case: open submit page with title prefilled in URL,
    // copy body to clipboard for the user to paste.
    if (target.redditPrefill) {
      const { title, body } = splitTitleBody(content);
      const url = `https://www.reddit.com/submit?title=${encodeURIComponent(title)}`;
      const tab = await chrome.tabs.create({ url, active: true });
      await waitForTabLoad(tab.id);
      await copyToTabClipboard(tab.id, body);
      await report(draft_id, {
        info: "needs_user_action: title prefilled, body in clipboard — pick a subreddit, paste body, click Submit",
      });
      return;
    }

    // Auto-post / assist platforms — find/open tab, send message to content script.
    const tab = await findOrOpenTab(target.tabs, target.open);
    await waitForTabLoad(tab.id);
    await new Promise((r) => setTimeout(r, 1500)); // let SPA finish rendering

    const resp = await chrome.tabs.sendMessage(tab.id, {
      type: "fanout:post",
      platform,
      draft_id,
      content,
    });

    if (resp?.ok) {
      await report(draft_id, { postUrl: resp.postUrl ?? null });
    } else {
      await report(draft_id, { error: resp?.error ?? "unknown error" });
    }
  } catch (e) {
    await report(draft_id, { error: String(e?.message ?? e) });
  }
}

async function poll() {
  const { apiUrl, enabled, jwt } = await getConfig();
  if (!enabled) return;
  try {
    const res = await fetch(`${apiUrl}/queue`, { headers: authHeaders(jwt) });
    if (!res.ok) return;
    const items = await res.json();
    for (const item of items) {
      await dispatch(item);
    }
  } catch {
    /* backend probably down */
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === POLL_ALARM) poll();
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "fanout:poll-now") {
    poll().then(() => sendResponse({ ok: true }));
    return true;
  }
});
