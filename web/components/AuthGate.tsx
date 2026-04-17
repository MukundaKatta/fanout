"use client";

import { useEffect, useState } from "react";
import { supabase, supabaseEnabled } from "@/lib/supabase";
import NavBar from "./NavBar";
import Footer from "./Footer";
import Logo from "./Logo";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [inputEmail, setInputEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!supabaseEnabled || !supabase) {
      setReady(true);
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setEmail(data.session?.user.email ?? null);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      setEmail(session?.user.email ?? null);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-white/40">
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-white/40 animate-pulse" />
          Loading
        </span>
      </div>
    );
  }

  if (supabaseEnabled && !email) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <div className="glass w-full max-w-sm rounded-3xl p-8 space-y-5 fade-up">
          <div className="flex flex-col items-center gap-3 text-center">
            <Logo size={40} />
            <h1 className="text-3xl font-bold tracking-tight gradient-text">Fanout</h1>
            <p className="text-sm text-white/50">Magic link sign-in. No password.</p>
          </div>
          {sentTo ? (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-200">
              ✨ Magic link sent to <strong>{sentTo}</strong>. Check your inbox.
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={async (e) => {
                e.preventDefault();
                setError(null);
                const { error } = await supabase!.auth.signInWithOtp({
                  email: inputEmail,
                  options: { emailRedirectTo: window.location.origin },
                });
                if (error) setError(error.message);
                else setSentTo(inputEmail);
              }}
            >
              <input
                type="email"
                required
                value={inputEmail}
                onChange={(e) => setInputEmail(e.target.value)}
                placeholder="you@example.com"
                className="input"
              />
              <button type="submit" className="btn-primary w-full justify-center">
                Send magic link
              </button>
              {error && <p className="text-sm text-rose-300">{error}</p>}
            </form>
          )}
        </div>
      </main>
    );
  }

  return (
    <>
      {!supabaseEnabled && (
        <div className="border-b border-amber-500/20 bg-amber-500/5 px-4 py-1.5 text-center text-[11px] text-amber-300/80">
          Dev mode — Supabase not configured. Single-user, no auth.
        </div>
      )}
      <NavBar email={email} />
      {children}
      <Footer />
    </>
  );
}
