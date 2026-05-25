"use client";
import { useRef, useState } from "react";
import { reconstructApi } from "@/lib/api/client";
import { WalletGuard } from "@/components/WalletGuard";
import { Button, Card, SectionTitle, Spinner } from "@/components/ui";

type ApiError = {
  response?: { data?: Blob | { detail?: string } };
  message?: string;
};

async function errorMessage(error: unknown) {
  if (typeof error === "object" && error !== null) {
    const e = error as ApiError;
    const data = e.response?.data;
    if (data instanceof Blob) {
      try {
        const parsed = JSON.parse(await data.text());
        return parsed.detail || e.message || "Reconstruct failed";
      } catch {
        return e.message || "Reconstruct failed";
      }
    }
    return e.message || "Reconstruct failed";
  }
  return "Reconstruct failed";
}

export default function ReconstructPage() {
  const [manifestFile, setManifestFile] = useState<File | null>(null);
  const [shelbyAccount, setShelbyAccount] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectFile = (file?: File) => {
    if (!file) return;
    setError(null);
    setManifestFile(file);
  };

  const reconstruct = async () => {
    if (!manifestFile) {
      setError("Choose a manifest.uploaded.json file first.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await reconstructApi.fromManifest(manifestFile, shelbyAccount);
      const url = URL.createObjectURL(result.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(await errorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <WalletGuard message="Connect your wallet to reconstruct Shelby datasets.">
      <div style={{ width: "100%", maxWidth: 860 }}>
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontFamily: "var(--mono)", fontSize: 20, fontWeight: 500, color: "#2d1b0f" }}>
            Reconstruct Dataset
          </h1>
          <p style={{ color: "#7a4a31", fontSize: 13, marginTop: 6 }}>
            Upload a sent manifest and download the dataset data from Shelby.
          </p>
        </div>

        {error && (
          <div style={{
            background: "rgba(239,68,68,0.08)", border: "1px solid var(--red)",
            borderRadius: "var(--radius)", padding: "12px 16px", marginBottom: 20,
            fontFamily: "var(--mono)", fontSize: 12, color: "var(--red)",
            lineHeight: 1.6, whiteSpace: "pre-wrap",
          }}>✗ {error}</div>
        )}

        <Card>
          <SectionTitle>Manifest</SectionTitle>
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => {
              e.preventDefault();
              setDragOver(false);
              selectFile(e.dataTransfer.files[0]);
            }}
            onClick={() => inputRef.current?.click()}
            style={{
              border: `2px dashed ${dragOver ? "var(--green)" : "var(--border2)"}`,
              borderRadius: "var(--radius-lg)",
              padding: "30px 24px",
              textAlign: "center",
              cursor: "pointer",
              background: dragOver ? "rgba(0,212,160,0.04)" : "var(--bg2)",
              marginBottom: 18,
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".json,application/json"
              style={{ display: "none" }}
              onChange={e => selectFile(e.target.files?.[0])}
            />
            <div style={{ fontFamily: "var(--mono)", fontSize: 14, color: manifestFile ? "var(--green)" : "var(--text)" }}>
              {manifestFile ? `✓ ${manifestFile.name}` : "Drop manifest.uploaded.json here or click to browse"}
            </div>
          </div>

          <label>
            <div style={{
              fontSize: 11, color: "var(--text3)", fontFamily: "var(--mono)",
              letterSpacing: "0.08em", marginBottom: 6,
            }}>
              SHELBY ACCOUNT
            </div>
            <input
              value={shelbyAccount}
              onChange={e => setShelbyAccount(e.target.value)}
              placeholder="0x... optional if manifest includes shelby_account"
              style={{
                width: "100%", background: "var(--bg2)", border: "1px solid var(--border)",
                borderRadius: "var(--radius)", padding: "8px 12px",
                color: "var(--text)", fontFamily: "var(--mono)", fontSize: 13, outline: "none",
                marginBottom: 16,
              }}
            />
          </label>

          <Button onClick={reconstruct} disabled={loading || !manifestFile}>
            {loading ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <Spinner size={13} /> Reconstructing...
              </span>
            ) : "↓ Reconstruct data"}
          </Button>
        </Card>
      </div>
    </WalletGuard>
  );
}
