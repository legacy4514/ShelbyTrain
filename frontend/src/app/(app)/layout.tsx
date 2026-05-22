import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex" }}>
      <Sidebar />
      <Header />
      <main style={{
        marginLeft: 200,
        marginTop: 56,
        flex: 1,
        minHeight: "100vh",
        padding: "36px clamp(32px, 4vw, 72px)",
        background: "var(--bg)",
      }}>
        {children}
      </main>
    </div>
  );
}
