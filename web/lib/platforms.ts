import type { Platform } from "./api";
import {
  FaLinkedin,
  FaXTwitter,
  FaThreads,
  FaBluesky,
  FaMastodon,
  FaInstagram,
  FaReddit,
  FaYCombinator,
  FaProductHunt,
  FaMedium,
  FaDev,
  FaTelegram,
  FaDiscord,
  FaSlack,
  FaEnvelope,
} from "react-icons/fa6";
import type { IconType } from "react-icons";

export type Capability = "auto" | "assist" | "copy" | "mailto";

export type PlatformMeta = {
  id: Platform;
  label: string;
  Icon: IconType;
  /** Brand-accurate accent color used for the active highlight stripe and glow. */
  accent: string;
  capability: Capability;
  group: "social" | "communities" | "longform" | "outreach";
};

const C: Record<Capability, { label: string; tone: string }> = {
  auto:   { label: "auto-post",   tone: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/20" },
  assist: { label: "assisted",    tone: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-400/20" },
  copy:   { label: "copy & open", tone: "bg-sky-500/15 text-sky-300 ring-1 ring-sky-400/20" },
  mailto: { label: "mailto",      tone: "bg-violet-500/15 text-violet-300 ring-1 ring-violet-400/20" },
};

export const capabilityBadge = (cap: Capability) => C[cap];

export const PLATFORMS: PlatformMeta[] = [
  // Social
  { id: "linkedin",  label: "LinkedIn",     Icon: FaLinkedin,     accent: "#0A66C2", capability: "auto",   group: "social" },
  { id: "x",         label: "X",            Icon: FaXTwitter,     accent: "#FFFFFF", capability: "auto",   group: "social" },
  { id: "threads",   label: "Threads",      Icon: FaThreads,      accent: "#FFFFFF", capability: "auto",   group: "social" },
  { id: "bluesky",   label: "Bluesky",      Icon: FaBluesky,      accent: "#0285FF", capability: "auto",   group: "social" },
  { id: "mastodon",  label: "Mastodon",     Icon: FaMastodon,     accent: "#6364FF", capability: "auto",   group: "social" },
  { id: "instagram", label: "Instagram",    Icon: FaInstagram,    accent: "#E4405F", capability: "assist", group: "social" },

  // Communities
  { id: "reddit",      label: "Reddit",      Icon: FaReddit,       accent: "#FF4500", capability: "assist", group: "communities" },
  { id: "hackernews",  label: "Hacker News", Icon: FaYCombinator,  accent: "#FF6600", capability: "copy",   group: "communities" },
  { id: "producthunt", label: "Product Hunt",Icon: FaProductHunt,  accent: "#DA552F", capability: "copy",   group: "communities" },

  // Long-form
  { id: "medium",      label: "Medium",      Icon: FaMedium,       accent: "#FFFFFF", capability: "copy",   group: "longform" },
  { id: "devto",       label: "Dev.to",      Icon: FaDev,          accent: "#FFFFFF", capability: "copy",   group: "longform" },

  // Outreach
  { id: "email",       label: "Email",       Icon: FaEnvelope,     accent: "#EA4335", capability: "mailto", group: "outreach" },
  { id: "telegram",    label: "Telegram",    Icon: FaTelegram,     accent: "#26A5E4", capability: "copy",   group: "outreach" },
  { id: "discord",     label: "Discord",     Icon: FaDiscord,      accent: "#5865F2", capability: "copy",   group: "outreach" },
  { id: "slack",       label: "Slack",       Icon: FaSlack,        accent: "#4A154B", capability: "copy",   group: "outreach" },
];

export const PLATFORM_BY_ID: Record<Platform, PlatformMeta> = Object.fromEntries(
  PLATFORMS.map((p) => [p.id, p])
) as Record<Platform, PlatformMeta>;

export const PLATFORM_GROUPS: { id: PlatformMeta["group"]; label: string; hint: string }[] = [
  { id: "social",      label: "Social",          hint: "Auto-post from your browser session" },
  { id: "communities", label: "Communities",     hint: "Reddit, HN, Product Hunt" },
  { id: "longform",    label: "Long-form",       hint: "Medium, Dev.to" },
  { id: "outreach",    label: "Direct outreach", hint: "Email, chat platforms" },
];
