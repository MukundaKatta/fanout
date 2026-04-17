// Content script for linkedin.com — opens the share composer and posts.
// WARNING: LinkedIn DOM changes. Selectors may need updating.

(function () {
  function waitFor(selector, { timeout = 10000, root = document } = {}) {
    return new Promise((resolve, reject) => {
      const start = Date.now();
      const tick = () => {
        const el = root.querySelector(selector);
        if (el) return resolve(el);
        if (Date.now() - start > timeout) return reject(new Error(`timeout: ${selector}`));
        requestAnimationFrame(tick);
      };
      tick();
    });
  }

  async function openComposer() {
    // "Start a post" on the feed page.
    const starter =
      document.querySelector('button.share-box-feed-entry__trigger') ||
      document.querySelector('button[aria-label="Start a post"]');
    if (!starter) throw new Error("Share composer not found — are you on /feed/?");
    starter.click();
    return await waitFor('div[role="textbox"][contenteditable="true"]');
  }

  async function typeInto(el, text) {
    el.focus();
    const dt = new DataTransfer();
    dt.setData("text/plain", text);
    el.dispatchEvent(
      new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true })
    );
  }

  async function postNow() {
    const btn = await waitFor('button.share-actions__primary-action:not([disabled])');
    btn.click();
    await new Promise((r) => setTimeout(r, 3000));
    return { postUrl: null }; // LinkedIn doesn't give us the URL cleanly post-click.
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg?.type !== "fanout:post") return;
    (async () => {
      try {
        const editor = await openComposer();
        await typeInto(editor, msg.content);
        const { postUrl } = await postNow();
        sendResponse({ ok: true, postUrl });
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message ?? e) });
      }
    })();
    return true;
  });
})();
