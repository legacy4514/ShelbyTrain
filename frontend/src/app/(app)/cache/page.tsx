"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { cacheApi } from "@/lib/api/client";
import { Card, SectionTitle, StatCard, Button, ProgressBar } from "@/components/ui";
import { WalletGuard } from "@/components/WalletGuard";

type CacheShard = {
  key: string;
  size_mb: number;
  modified: number;
  blob_name?: string;
  valid?: boolean;
  cache_hits?: number;
  cache_misses?: number;
  downloads?: number;
  download_sec?: number;
  extract_sec?: number;
  last_accessed?: number;
};

export default function CachePage() {
  const qc = useQueryClient();

  const { data: stats, isLoading } = useQuery({
    queryKey: ["cache"],
    queryFn: cacheApi.stats,
    refetchInterval: 4000,
  });

  const evict = useMutation({
    mutationFn: (key: string) => cacheApi.evict(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cache"] }),
  });

  const clear = useMutation({
    mutationFn: cacheApi.clear,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cache"] }),
  });

  const shards = (stats?.shards ?? []) as CacheShard[];
  const usedMB = stats?.total_mb ?? 0;

  return (
    <WalletGuard message="Connect your wallet to view cached. Your wallet address is used as your Shelby account.">
    <div style={{ width: "100%", maxWidth: 1160 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontFamily: "var(--mono)", fontSize: 20, fontWeight: 500, color: "#2d1b0f" }}>Cache Monitor</h1>
        <p style={{ color: "#7a4a31", fontSize: 13, marginTop: 6 }}>
          Local shard cache at <span style={{ color: "var(--text)", fontFamily: "var(--mono)" }}>.shelby-cache/</span>
          {" "}— auto-refreshes every 4 seconds.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 16, marginBottom: 20 }}>
        <StatCard label="Cached shards" value={isLoading ? "..." : (stats?.shard_count ?? 0)} accent="green" />
        <StatCard label="Total size" value={isLoading ? "..." : usedMB.toFixed(1)} unit="MB" accent="green" />
        <StatCard label="Cache status" value={stats?.exists ? (shards.length > 0 ? "warm" : "empty") : "none"}
          accent={shards.length > 0 ? "green" : "blue"} />
      </div>

      <Card style={{ marginBottom: 16 }}>
        <SectionTitle>Storage usage</SectionTitle>
        <ProgressBar value={usedMB} max={512} label={`${usedMB.toFixed(1)} MB used`} />
        <div style={{ fontSize: 11, color: "var(--text3)", fontFamily: "var(--mono)", marginTop: 8 }}>
          Display scale: 512 MB max
        </div>
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <SectionTitle>Actions</SectionTitle>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Button variant="danger" onClick={() => clear.mutate()}
            disabled={clear.isPending || shards.length === 0}>
            ✕ Clear all cache
          </Button>
          {clear.isSuccess && (
            <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--green)" }}>✓ Cache cleared</span>
          )}
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: "var(--text3)", fontFamily: "var(--mono)" }}>
          Clearing forces the next benchmark to re-download shards from Shelby (cold start).
        </div>
      </Card>

      <Card>
        <SectionTitle>Cached shards ({shards.length})</SectionTitle>
        {isLoading && <div style={{ color: "var(--text3)", fontSize: 13, fontFamily: "var(--mono)" }}>Loading...</div>}
        {!isLoading && shards.length === 0 && (
          <div style={{ color: "var(--text3)", fontSize: 13, fontFamily: "var(--mono)" }}>
            Cache is empty. Run a Shelby benchmark to populate it.
          </div>
        )}
        {shards.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--mono)", fontSize: 11 }}>
            <thead>
              <tr>
                {["Blob", "Size", "Hits/Misses", "Download", "Extract", "Valid", ""].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "6px 10px",
                    color: "var(--text3)", borderBottom: "1px solid var(--border)",
                    fontWeight: 500, letterSpacing: "0.06em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shards.map((s) => (
                <tr key={s.key} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "8px 10px", color: "var(--text2)", maxWidth: 260,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.blob_name ?? s.key}</td>
                  <td style={{ padding: "8px 10px", color: "var(--text2)" }}>{s.size_mb} MB</td>
                  <td style={{ padding: "8px 10px", color: "var(--text2)" }}>
                    {s.cache_hits ?? 0}/{s.cache_misses ?? 0}
                  </td>
                  <td style={{ padding: "8px 10px", color: "var(--text2)" }}>
                    {s.download_sec?.toFixed?.(3) ?? "0.000"}s
                  </td>
                  <td style={{ padding: "8px 10px", color: "var(--text2)" }}>
                    {s.extract_sec?.toFixed?.(3) ?? "0.000"}s
                  </td>
                  <td style={{ padding: "8px 10px", color: "var(--text3)" }}>
                    {s.valid ? "yes" : "unknown"}
                  </td>
                  <td style={{ padding: "8px 10px" }}>
                    <Button variant="ghost" size="sm"
                      onClick={() => evict.mutate(s.key)}
                      disabled={evict.isPending}>
                      evict
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
    </WalletGuard>
  );
}
