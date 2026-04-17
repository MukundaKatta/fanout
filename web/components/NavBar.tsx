"use client";

import Logo from "./Logo";
import { Github, Sparkles } from "lucide-react";
import { supabase, supabaseEnabled } from "@/lib/supabase";

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
            <Github size={16} />
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
