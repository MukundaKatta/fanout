// Content script for bsky.app — opens composer and posts.

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

  async function openComposer() {
    // Floating new-post button has a known testid in Bluesky's web client.
    const trigger =
      document.querySelector('[data-testid="composeFAB"]') ||
      document.querySelector('[aria-label="New post"]') ||
      document.querySelector('button[aria-label*="post" i]');
    if (trigger) trigger.click();
    return await waitFor(
      () =>
        document.querySelector('[data-testid="composerTextInput"]') ||
        document.querySelector('div[contenteditable="true"][role="textbox"]'),
      { timeout: 8000, label: "bluesky composer" }
    );
  }

  async function paste(el, text) {
    el.focus();
    const dt = new DataTransfer();
    dt.setData("text/plain", text);
    el.dispatchEvent(
      new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true })
    );
    await sleep(150);
  }

  async function clickPost() {
    const btn = await waitFor(
      () =>
        document.querySelector('[data-testid="composerPublishBtn"]') ||
        Array.from(document.querySelectorAll('button')).find(
          (el) => /^post$/i.test((el.textContent || "").trim()) && !el.disabled
        ),
      { timeout: 6000, label: "bluesky publish" }
    );
    btn.click();
    await sleep(2500);
  }

  chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
    if (msg?.type !== "fanout:post") return;
    (async () => {
      try {
        if (msg.content.length > 300) {
          throw new Error(`Bluesky limit is 300 chars (got ${msg.content.length})`);
        }
        const editor = await openComposer();
        await paste(editor, msg.content);
        await clickPost();
        sendResponse({ ok: true, postUrl: null });
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message ?? e) });
      }
    })();
    return true;
  });
})();
