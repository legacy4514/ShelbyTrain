"use client";
import { useWallet } from "@/lib/useWallet";

export function Header() {
  const {
    connected,
    address,
    connecting,
    connect,
    disconnect,
    walletName,
    hasWallet,
    walletChecked,
  } = useWallet();

  return (
    <div style={{
      position: "fixed", top: 0, left: 200, right: 0, height: 56,
      background: "var(--bg1)",
      borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center",
      justifyContent: "flex-end",
      padding: "0 32px",
      zIndex: 9,
    }}>
      {connected && address ? (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            background: "var(--bg2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "6px 14px",
          }}>
            <div style={{
              width: 7, height: 7, borderRadius: "50%",
              background: "var(--green)",
              boxShadow: "0 0 6px var(--green)",
            }} />
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)", marginRight: 4 }}>
              {walletName}
            </span>
            <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--text)" }}>
              {address.slice(0, 6)}...{address.slice(-4)}
            </span>
          </div>
          <button onClick={disconnect} style={{
            background: "transparent",
            border: "1px solid var(--border2)",
            borderRadius: "var(--radius)",
            color: "var(--text3)",
            fontFamily: "var(--mono)",
            fontSize: 11, cursor: "pointer",
            padding: "6px 12px",
            letterSpacing: "0.06em",
          }}>
            disconnect
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {walletChecked && !hasWallet && (
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)" }}>
              No Aptos wallet detected
            </span>
          )}
          <button
            onClick={connect}
            disabled={connecting}
            style={{
              background: connecting ? "var(--bg3)" : "var(--green)",
              border: "none",
              borderRadius: "var(--radius)",
              color: connecting ? "var(--text3)" : "#fff",
              fontFamily: "var(--mono)",
              fontSize: 12,
              cursor: connecting ? "not-allowed" : "pointer",
              fontWeight: 600,
              letterSpacing: "0.06em",
              padding: "8px 18px",
              transition: "all 0.15s",
            }}
          >
            {connecting ? "connecting..." : walletChecked && !hasWallet ? "Install Petra" : "Connect Wallet"}
          </button>
        </div>
      )}
    </div>
  );
}
