import Logo from "./Logo";
import { PLATFORMS } from "@/lib/platforms";

export default function Footer() {
  return (
    <footer className="border-t border-white/[0.06] mt-24">
      <div className="mx-auto max-w-6xl px-6 py-12 space-y-8">
        <div className="flex items-center justify-center gap-2 text-white/30 text-xs uppercase tracking-[0.2em]">
          <span className="h-px w-8 bg-white/10" />
          Ships everywhere
          <span className="h-px w-8 bg-white/10" />
        </div>
        <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-5">
          {PLATFORMS.map(({ id, label, Icon }) => (
            <div
              key={id}
              className="group flex items-center gap-2 text-white/30 hover:text-white/80 transition-colors"
              title={label}
            >
              <Icon size={18} />
              <span className="text-xs hidden sm:inline">{label}</span>
            </div>
          ))}
        </div>
        <div className="pt-8 border-t border-white/[0.04] flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-white/30">
          <div className="flex items-center gap-2">
            <Logo size={16} />
            <span>Fanout · made for indie shippers</span>
          </div>
          <div className="flex items-center gap-4">
            <span>Privacy</span>
            <span>Terms</span>
            <span>© 2026</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
