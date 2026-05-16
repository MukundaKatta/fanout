"use client";

import Logo from "./Logo";
import { Sparkles } from "lucide-react";
import { supabase, supabaseEnabled } from "@/lib/supabase";

function GitHubMark({ size = 16 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      fill="currentColor"
      height={size}
      viewBox="0 0 16 16"
      width={size}
    >
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.65 7.65 0 0 1 8 3.86c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

export default function NavBar({ email }: { email?: string | null }) {
  return (
    <nav className="sticky top-0 z-40 border-b border-white/[0.06] bg-black/40 backdrop-blur-2xl">
      <div className="mx-auto max-w-6xl px-6 h-14 flex items-center justify-between">
        <a href="/" className="flex items-center gap-2.5 group">
          <div className="relative">
            <Logo size={26} />
            <div className="absolute inset-0 -z-10 blur-xl opacity-50 group-hover:opacity-80 transition-opacity">
              <Logo size={26} />
            </div>
          </div>
          <span className="text-base font-semibold tracking-tight">Fanout</span>
          <span className="rounded-full border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] font-medium text-white/50">
            beta
          </span>
        </a>
        <div className="flex items-center gap-2">
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg text-white/50 hover:text-white hover:bg-white/5 transition-colors"
            aria-label="GitHub"
          >
            <GitHubMark size={16} />
          </a>
          <div className="hidden sm:flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-white/60">
            <Sparkles size={11} className="text-violet-300" />
            free models
          </div>
          {supabaseEnabled && email && (
            <button
              onClick={() => supabase!.auth.signOut()}
              className="text-xs text-white/50 hover:text-white transition-colors px-2 py-1"
            >
              Sign out
            </button>
          )}
          {supabaseEnabled && email && (
            <div className="h-7 w-7 rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 grid place-items-center text-[10px] font-semibold uppercase">
              {email[0]}
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
