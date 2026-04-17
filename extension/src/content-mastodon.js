// Content script for any Mastodon web client.
// Mastodon is federated — installed on many domains. The extension matches a hand-picked
// set in the manifest; users can add their instance via "Refresh content script" in chrome://extensions.

(function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function waitFor(predicate, { timeout = 10000, interval = 100, label = "" } = {}) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const r = predicate();
      if (r) return r;
      await sleep(interval);
    }
    throw new Error(`timeout: ${label}`);
  }

  async function findEditor() {
    // Mastodon's web client exposes a textarea with class `compose-form__autosuggest-textarea__textarea`
    // (older Glitch fork) or a contenteditable on newer builds. Cover both.
    return await waitFor(
      () =>
        document.querySelector("textarea.compose-form__autosuggest-textarea__textarea") ||
        document.querySelector('textarea[placeholder*="What" i]') ||
        document.querySelector('div.compose-form__highlightable[contenteditable="true"]'),
      { timeout: 8000, label: "mastodon composer" }
    );
  }

  async function fillTextarea(el, text) {
    // Mastodon listens for 'input' on the textarea — set value and dispatch.
    el.focus();
    if (el.tagName === "TEXTAREA") {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
      setter.call(el, text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true }));
    }
    await sleep(150);
  }

  async function clickPublish() {
    const btn = await waitFor(
      () => {
        const all = Array.from(document.querySelectorAll('button'));
        return all.find((b) => {
          const label = (b.getAttribute("aria-label") || b.textContent || "").toLowerCase().trim();
          return /^(publish|toot|post)/.test(label) && !b.disabled;
        });
      },
      { timeout: 6000, label: "mastodon publish" }
    );
    btn.click();
    await sleep(2500);
  }

  chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
    if (msg?.type !== "fanout:post") return;
    (async () => {
      try {
        if (msg.content.length > 500) {
          throw new Error(`Mastodon limit is 500 chars (got ${msg.content.length})`);
        }
        const editor = await findEditor();
        await fillTextarea(editor, msg.content);
        await clickPublish();
        sendResponse({ ok: true, postUrl: null });
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message ?? e) });
      }
    })();
    return true;
  });
})();
