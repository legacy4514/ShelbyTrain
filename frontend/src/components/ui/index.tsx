import React from "react";

export function Card({ children, className = "", style }: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div style={{
      background: "var(--bg1)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-lg)",
      padding: "20px 24px",
      ...style,
    }} className={className}>
      {children}
    </div>
  );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{
      fontFamily: "var(--mono)",
      fontSize: 11,
      fontWeight: 500,
      letterSpacing: "0.12em",
      textTransform: "uppercase",
      color: "var(--text3)",
      marginBottom: 16,
    }}>
      {children}
    </h2>
  );
}

export function StatCard({ label, value, unit, accent }: {
  label: string; value: string | number; unit?: string; accent?: "green" | "amber" | "red" | "blue";
}) {
  const colors = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)", blue: "var(--blue)" };
  const color = accent ? colors[accent] : "var(--text)";
  return (
    <div style={{
      background: "var(--bg2)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius)",
      padding: "14px 18px",
    }}>
      <div style={{ fontSize: 11, color: "var(--text3)", fontFamily: "var(--mono)",
        letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 500, color, fontFamily: "var(--mono)" }}>
        {value}<span style={{ fontSize: 12, color: "var(--text3)", marginLeft: 4 }}>{unit}</span>
      </div>
    </div>
  );
}

export function Badge({ children, variant = "default" }: {
  children: React.ReactNode;
  variant?: "default" | "green" | "amber" | "red" | "blue";
}) {
  const styles = {
    default: { bg: "var(--bg3)", color: "var(--text2)" },
    green:   { bg: "rgba(0,212,160,0.1)", color: "var(--green)" },
    amber:   { bg: "rgba(245,158,11,0.1)", color: "var(--amber)" },
    red:     { bg: "rgba(239,68,68,0.1)", color: "var(--red)" },
    blue:    { bg: "rgba(59,130,246,0.1)", color: "var(--blue)" },
  };
  const s = styles[variant];
  return (
    <span style={{
      background: s.bg, color: s.color,
      fontSize: 11, fontFamily: "var(--mono)",
      padding: "2px 8px", borderRadius: 4,
      letterSpacing: "0.06em",
    }}>
      {children}
    </span>
  );
}

export function Button({ children, onClick, disabled, variant = "primary", size = "md" }: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "danger";
  size?: "sm" | "md";
}) {
  const base: React.CSSProperties = {
    fontFamily: "var(--mono)",
    fontSize: size === "sm" ? 11 : 13,
    fontWeight: 500,
    letterSpacing: "0.06em",
    border: "1px solid",
    borderRadius: "var(--radius)",
    padding: size === "sm" ? "5px 12px" : "8px 18px",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.45 : 1,
    transition: "all 0.15s",
  };
  const variants = {
    primary: { background: "var(--green)", borderColor: "var(--green)", color: "#fff" },
    ghost:   { background: "transparent", borderColor: "var(--border2)", color: "var(--text2)" },
    danger:  { background: "transparent", borderColor: "var(--red)", color: "var(--red)" },
  };
  return (
    <button style={{ ...base, ...variants[variant] }} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function ProgressBar({ value, max, label }: { value: number; max: number; label?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div>
      {label && (
        <div style={{ display: "flex", justifyContent: "space-between",
          fontSize: 11, color: "var(--text3)", marginBottom: 6, fontFamily: "var(--mono)" }}>
          <span>{label}</span>
          <span>{pct}%</span>
        </div>
      )}
      <div style={{ height: 4, background: "var(--bg3)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${pct}%`,
          background: "var(--green)", borderRadius: 2,
          transition: "width 0.3s ease",
        }} />
      </div>
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span style={{
      display: "inline-block", width: size, height: size,
      border: `2px solid var(--border2)`,
      borderTopColor: "var(--green)",
      borderRadius: "50%",
      animation: "spin 0.7s linear infinite",
    }} />
  );
}
