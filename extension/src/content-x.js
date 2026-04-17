// Content script for x.com — posts a tweet or a full thread via the composer.
// Uses reply-chain semantics: after the first tweet, the "+" button adds another editor
// in the same composer; "Post all" publishes them as a linked thread.
//
// Selectors are data-testid-based (more stable than classes) but X redesigns regularly.
// If posting breaks, inspect the composer and update the testids below.

(function () {
  const TESTID = {
    composeBtn: "SideNav_NewTweet_Button",
    editor: (i) => `tweetTextarea_${i}`,
    addAnother: "addButton",
    postBtn: "tweetButton",
    profileLink: "AppTabBar_Profile_Link",
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function qs(selector, root = document) {
    return root.querySelector(selector);
  }

  function byTestId(id, root = document) {
    return qs(`[data-testid="${id}"]`, root);
  }

  async function waitFor(predicate, { timeout = 10000, interval = 100, label = "" } = {}) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const result = predicate();
      if (result) return result;
      await sleep(interval);
    }
    throw new Error(`timeout: ${label || predicate.toString().slice(0, 80)}`);
  }

  async function pasteInto(el, text) {
    el.focus();
    const dt = new DataTransfer();
    dt.setData("text/plain", text);
    el.dispatchEvent(
      new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true })
    );
    // Let Draft.js / ProseMirror sync.
    await sleep(150);
  }

  async function openComposer() {
    const btn =
      byTestId(TESTID.composeBtn) ||
      qs('a[href="/compose/post"]') ||
      qs('a[href="/compose/tweet"]');
    if (btn) btn.click();
    return await waitFor(() => byTestId(TESTID.editor(0)), {
      timeout: 8000,
      label: "composer editor",
    });
  }

  async function addAnotherTweet(nextIndex) {
    // The + button lives inside the open composer dialog.
    const addBtn =
      byTestId(TESTID.addAnother) ||
      qs('[aria-label="Add another post"]') ||
      qs('[aria-label="Add post"]');
    if (!addBtn) throw new Error("Add-another-tweet button not found");
    addBtn.click();
    return await waitFor(() => byTestId(TESTID.editor(nextIndex)), {
      timeout: 5000,
      label: `editor ${nextIndex}`,
    });
  }

  async function clickPost() {
    const btn = await waitFor(
      () => {
        const candidates = document.querySelectorAll(`[data-testid="${TESTID.postBtn}"]`);
        for (const el of candidates) {
          if (el.getAttribute("aria-disabled") !== "true") return el;
        }
        return null;
      },
      { timeout: 8000, label: "post button enabled" }
    );
    btn.click();
  }

  async function grabFirstPostUrl() {
    // After posting, X navigates or updates; pulling a stable URL is flaky.
    // Best-effort: return the profile URL so the user can find the latest post.
    await sleep(3000);
    const handleLink = byTestId(TESTID.profileLink);
    const href = handleLink?.getAttribute("href");
    if (!href) return null;
    const handle = href.replace(/^\//, "").split("/")[0];
    return handle ? `https://x.com/${handle}` : null;
  }

  function splitThread(text) {
    const numbered = text.split(/\n(?=\s*\d+\s*[/)]\s*\d*)/);
    if (numbered.length > 1) return numbered.map((p) => p.trim()).filter(Boolean);
    return text
      .split(/\n\n+/)
      .map((p) => p.trim())
      .filter(Boolean);
  }

  function validate(tweets) {
    for (let i = 0; i < tweets.length; i++) {
      if (tweets[i].length > 280) {
        throw new Error(`Tweet ${i + 1} is ${tweets[i].length} chars (>280)`);
      }
    }
  }

  async function postThread(text) {
    const tweets = splitThread(text);
    if (tweets.length === 0) throw new Error("Empty content");
    validate(tweets);

    const firstEditor = await openComposer();
    await pasteInto(firstEditor, tweets[0]);

    for (let i = 1; i < tweets.length; i++) {
      const editor = await addAnotherTweet(i);
      await pasteInto(editor, tweets[i]);
    }

    await clickPost();
    const postUrl = await grabFirstPostUrl();
    return { postUrl, count: tweets.length };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg?.type !== "fanout:post") return;
    (async () => {
      try {
        const { postUrl, count } = await postThread(msg.content);
        sendResponse({ ok: true, postUrl, meta: { tweets: count } });
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message ?? e) });
      }
    })();
    return true; // async
  });
})();
