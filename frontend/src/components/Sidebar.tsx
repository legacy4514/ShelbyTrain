"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const nav = [
  { href: "/dashboard",  label: "Dashboard",  icon: "⬡" },
  { href: "/upload",     label: "Upload",      icon: "↑" },
  { href: "/benchmark",  label: "Benchmark",   icon: "◈" },
  { href: "/datasets",   label: "Datasets",    icon: "▦" },
  { href: "/reconstruct", label: "Reconstruct", icon: "↓" },
  { href: "/cache",      label: "Cache",       icon: "◎" },
];

export function Sidebar() {
  const path = usePathname();

  return (
    <aside style={{
      width: 200, minHeight: "100vh", background: "var(--bg1)",
      borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
      padding: "24px 0",
      position: "fixed", top: 0, left: 0, zIndex: 10,
    }}>
      {/* Logo */}
      <div style={{ padding: "0 20px 28px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600,
          color: "var(--green)", letterSpacing: "0.08em" }}>
          SHELBY<span style={{ color: "var(--text3)" }}>TRAIN</span>
        </div>
        <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 3,
          fontFamily: "var(--mono)", letterSpacing: "0.06em" }}>
          dataset pipeline v0.1
        </div>
      </div>

      {/* Nav */}
      <nav style={{ padding: "16px 0", flex: 1 }}>
        {nav.map(({ href, label, icon }) => {
          const active = path === href || path.startsWith(href + "/");
          return (
            <Link key={href} href={href} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "9px 20px",
              background: active ? "var(--bg2)" : "transparent",
              borderLeft: active ? "2px solid var(--green)" : "2px solid transparent",
              color: active ? "var(--text)" : "var(--text2)",
              fontSize: 13, fontFamily: "var(--mono)",
              transition: "all 0.15s",
            }}>
              <span style={{ fontSize: 14, width: 18, textAlign: "center",
                color: active ? "var(--green)" : "var(--text3)" }}>
                {icon}
              </span>
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Network indicator */}
      <div style={{ padding: "16px 20px", borderTop: "1px solid var(--border)" }}>
        <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "var(--mono)",
          lineHeight: 1.8 }}>
          <div>Shelby Network</div>
          <div style={{ color: "var(--green-dim)" }}>● shelbynet</div>
        </div>
      </div>
    </aside>
  );
}
