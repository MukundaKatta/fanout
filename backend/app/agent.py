"""Agentic content pipeline.

Modes:
  - run(): plan -> write -> critique -> refine, ONE polished draft per platform
  - variations(): plan -> write N distinct drafts per platform with different angles

Supports 15 channels — autopost-friendly social, communities, long-form blogs, and email.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from groq import Groq

DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

PLATFORMS = (
    # Social — auto-post via extension
    "linkedin",
    "x",
    "threads",
    "bluesky",
    "mastodon",
    # Visual — caption (needs media on user side)
    "instagram",
    # Communities — copy + open submit page
    "reddit",
    "hackernews",
    "producthunt",
    # Long-form — copy + open editor
    "medium",
    "devto",
    # Direct outreach
    "email",
    "telegram",
    "discord",
    "slack",
)

PLATFORM_RULES: dict[str, str] = {
    "linkedin": (
        "Professional tone. 1200-1600 chars. Hook in line 1. Line breaks for scannability. "
        "End with a soft question or CTA. 3-5 hashtags at the end."
    ),
    "x": (
        "Thread of 4-8 tweets. Each <=270 chars. Tweet 1 is a sharp hook (no hashtags). "
        "Number tweets (1/N). Last tweet has the CTA. Concrete language."
    ),
    "threads": (
        "Conversational, punchy. 400-500 chars single post OR 3-5 short connected posts. "
        "No hashtags. Feel native, not corporate."
    ),
    "bluesky": (
        "Single post. Strict 300-char limit. Casual, intelligent voice. Avoid hashtags "
        "(Bluesky has weak hashtag culture). One tight idea + one CTA link if relevant."
    ),
    "mastodon": (
        "Single post. Strict 500-char limit. Tech-leaning, federated audience. "
        "Use 1-2 hashtags max (e.g. #SaaS, #IndieHackers). Avoid corporate marketing voice."
    ),
    "instagram": (
        "Caption 800-1500 chars. Attention-grabbing first line. Short paragraphs. "
        "2-4 emojis. 8-12 hashtags at the end."
    ),
    "reddit": (
        "Format as TITLE on the first line, then a blank line, then BODY (400-1000 words). "
        "Title is plain (no clickbait, no all-caps). Body is genuine, helpful, not salesy — "
        "Reddit hates marketing. Lead with the problem, share what you built, invite feedback. "
        "No hashtags."
    ),
    "hackernews": (
        "Format as TITLE on the first line, then blank line, then FIRST COMMENT (200-400 words). "
        "Title format: 'Show HN: <product> – <one-line description>'. "
        "First comment explains origin, tech choices, and asks for technical feedback. "
        "Plain text. No emojis. No hashtags. HN audience values substance over polish."
    ),
    "producthunt": (
        "Format as TAGLINE on first line (<60 chars, punchy), then blank line, then "
        "DESCRIPTION (300-600 chars), then blank line, then MAKER COMMENT (200-400 chars) "
        "thanking hunters and inviting feedback. Use 1-2 emojis sparingly."
    ),
    "medium": (
        "Long-form article 600-1200 words. Format: # H1 title on first line, then blank line, "
        "then sub-headings (## H2), short paragraphs, occasional bullet lists. Story-driven, "
        "value-first. End with a CTA to try the product. Markdown."
    ),
    "devto": (
        "Technical blog post 500-900 words. Markdown. Format: # Title, then blank line, then "
        "intro hook, ## sections, code blocks where relevant. Audience is developers — be "
        "specific, show implementation details. End with 'What would you build with this?'"
    ),
    "email": (
        "Format as SUBJECT on first line (<60 chars, no clickbait), then blank line, then BODY. "
        "Body is 150-300 words, plain text, friendly second-person voice. One clear CTA link. "
        "Sign off with a placeholder name. No marketing jargon."
    ),
    "telegram": (
        "Channel announcement, 200-500 chars. Markdown. Hook in line 1. Use *bold* and _italic_ "
        "sparingly. End with a single link. 1-2 emojis ok."
    ),
    "discord": (
        "Server announcement, 300-600 chars. Casual, community-first voice. Use Discord markdown "
        "(**bold**, *italic*, > quote). Address @everyone-style audience. End with a link or "
        "channel mention."
    ),
    "slack": (
        "Workspace announcement, 200-400 chars. Professional but warm. Use Slack mrkdwn "
        "(*bold*, _italic_, `code`). Bullet list works well. End with a single CTA link."
    ),
}

# Platform output is plain text by default. Some platforms have structured output:
# we treat them all as strings, and downstream code can split by '\n\n' if it needs to
# extract subject vs body, title vs comment, etc.

ANGLES = [
    "data-driven and credibility-focused",
    "story-driven and personal",
    "contrarian / hot-take",
    "tactical how-to with a quick win",
    "founder-vulnerable, behind-the-scenes",
]


@dataclass
class Plan:
    audience: str
    angle: str
    key_points: list[str]
    tone: str
    cta: str

    def as_prompt_block(self) -> str:
        return (
            f"Audience: {self.audience}\n"
            f"Angle: {self.angle}\n"
            f"Key points:\n- " + "\n- ".join(self.key_points) + "\n"
            f"Tone: {self.tone}\n"
            f"CTA: {self.cta}"
        )


class SocialAgent:
    def __init__(self, client: Groq | None = None, model: str = DEFAULT_MODEL):
        self.client = client or Groq()
        self.model = model

    def _chat(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.7,
    ) -> str:
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    # --- single polished draft -----------------------------------------------

    def plan(self, product: str) -> Plan:
        system = (
            "You are a senior content strategist. Produce a tight content plan as strict "
            "JSON: audience (string), angle (string), key_points (3-5 items), tone, cta."
        )
        data = json.loads(self._chat(system, f"Product:\n{product}", json_mode=True))
        return Plan(
            audience=data["audience"],
            angle=data["angle"],
            key_points=list(data["key_points"]),
            tone=data["tone"],
            cta=data["cta"],
        )

    def write(self, platform: str, product: str, plan: Plan) -> str:
        if platform not in PLATFORM_RULES:
            raise ValueError(f"Unknown platform: {platform}")
        system = (
            f"You are a top {platform} copywriter. Follow rules:\n"
            f"{PLATFORM_RULES[platform]}\nOutput ONLY the post text. No preamble."
        )
        user = (
            f"Product:\n{product}\n\nContent plan:\n{plan.as_prompt_block()}\n\n"
            f"Write the {platform} post."
        )
        return self._chat(system, user).strip()

    def critique(self, platform: str, draft: str) -> str:
        system = (
            f"You are a ruthless {platform} editor. Evaluate against rules:\n"
            f"{PLATFORM_RULES[platform]}\nList up to 5 fixes. If excellent, say 'LGTM'."
        )
        return self._chat(system, f"Draft:\n{draft}").strip()

    def refine(self, platform: str, draft: str, feedback: str) -> str:
        if feedback.strip().upper().startswith("LGTM"):
            return draft
        system = (
            f"You are a top {platform} copywriter. Apply editor feedback. Rules:\n"
            f"{PLATFORM_RULES[platform]}\nOutput ONLY the revised post."
        )
        user = f"Original:\n{draft}\n\nFeedback:\n{feedback}\n\nRevise."
        return self._chat(system, user).strip()

    def run(self, product: str, platforms: tuple[str, ...] = PLATFORMS) -> dict:
        plan_ = self.plan(product)
        posts = {}
        for platform in platforms:
            draft = self.write(platform, product, plan_)
            feedback = self.critique(platform, draft)
            final = self.refine(platform, draft, feedback)
            posts[platform] = {"draft": draft, "feedback": feedback, "final": final}
        return {"plan": asdict(plan_), "posts": posts}

    # --- N variations per platform -------------------------------------------

    def variations(self, product: str, platform: str, n: int = 5) -> list[dict]:
        if platform not in PLATFORM_RULES:
            raise ValueError(f"Unknown platform: {platform}")
        if n < 1 or n > 8:
            raise ValueError("n must be between 1 and 8")

        chosen_angles = ANGLES[:n]
        angle_lines = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(chosen_angles))

        system = (
            f"You are a top {platform} copywriter. Generate {n} DISTINCT post variations "
            f"for the same product. Each variation must use a different angle, different "
            f"opening hook, and a noticeably different structure — not paraphrases.\n\n"
            f"Platform rules (apply to every variation):\n{PLATFORM_RULES[platform]}\n\n"
            f"Respond as strict JSON: {{\"variations\": [{{\"angle\": str, \"content\": str}}, ...]}}\n"
            f"Use these angles in order:\n{angle_lines}"
        )
        user = f"Product:\n{product}\n\nGenerate {n} variations now."
        raw = self._chat(system, user, json_mode=True, temperature=0.9)
        data = json.loads(raw)
        items = data.get("variations", [])
        out = []
        for i, item in enumerate(items[:n]):
            out.append({
                "angle": item.get("angle") or (chosen_angles[i] if i < len(chosen_angles) else "variation"),
                "content": (item.get("content") or "").strip(),
            })
        return [v for v in out if v["content"]]
