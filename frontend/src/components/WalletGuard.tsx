"use client";
import { useWallet } from "@/lib/useWallet";

interface WalletGuardProps {
  children: React.ReactNode;
  message?: string;
}

export function WalletGuard({ children, message }: WalletGuardProps) {
  const { connected, connect, connecting } = useWallet();

  if (connected) return <>{children}</>;

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", minHeight: 400, textAlign: "center",
      padding: "48px 32px",
    }}>
      <div style={{
        width: 64, height: 64, borderRadius: "50%",
        border: "2px solid var(--border2)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 28, marginBottom: 24, color: "var(--text3)",
      }}>
        ⬡
      </div>
      <h2 style={{
        fontFamily: "var(--mono)", fontSize: 16, fontWeight: 500,
        color: "#2d1b0f", marginBottom: 10,
      }}>
        Wallet required
      </h2>
      <p style={{
        color: "#7a4a31", fontSize: 13, maxWidth: 380,
        lineHeight: 1.7, marginBottom: 28,
      }}>
        {message || "Connect your Aptos wallet to continue. Your wallet address is your identity on ShelbyTrain — it controls which datasets you own and can upload."}
      </p>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
        <button
          onClick={connect}
          disabled={connecting}
          style={{
            background: connecting ? "var(--bg3)" : "var(--green)",
            border: "none", borderRadius: "var(--radius)",
            color: connecting ? "var(--text3)" : "#000",
            fontFamily: "var(--mono)", fontSize: 13,
            cursor: connecting ? "not-allowed" : "pointer",
            fontWeight: 600, letterSpacing: "0.06em",
            padding: "10px 24px", transition: "all 0.15s",
          }}
        >
          {connecting ? "connecting..." : "⬡ Connect Wallet"}
        </button>
        <span style={{ fontSize: 11, color: "#7a4a31", fontFamily: "var(--mono)" }}>
          Supports Petra and other Aptos wallets
        </span>
      </div>
    </div>
  );
}
