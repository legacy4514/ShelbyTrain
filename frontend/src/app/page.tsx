import Link from "next/link";

const pipelineSteps = ["Shard", "Upload", "Benchmark", "Cache"];

export default function LandingPage() {
  return (
    <main className="landing-shell">
      <section className="landing-hero">
        <div className="hero-chrome hero-chrome-top" />
        <div className="hero-chrome hero-chrome-bottom" />
        <div className="hero-grid" />
        <div className="hero-orbit hero-orbit-one" />
        <div className="hero-orbit hero-orbit-two" />

        <nav className="landing-nav" aria-label="Landing navigation">
          <Link href="/" className="landing-brand">
            SHELBY<span>TRAIN</span>
          </Link>
          <Link href="/dashboard" className="landing-open">
            OPEN APP
          </Link>
        </nav>

        <div className="hero-content">
          <p className="hero-kicker">decentralized AI dataset pipeline</p>
          <h1>ShelbyTrain</h1>
          <h2>Where Datasets Train, Shelby Serves.</h2>
          <p className="hero-copy">
            Shard local datasets, push them to Shelby, and benchmark local,
            cold, and cached training throughput from one focused workspace.
          </p>

          <div className="hero-actions">
            <Link href="/dashboard" className="hero-primary">
              START BUILDING ↗
            </Link>
            <Link href="/datasets" className="hero-secondary">
              VIEW DATASETS
            </Link>
          </div>

          <div className="pipeline-rail" aria-label="Dataset pipeline stages">
            {pipelineSteps.map((step, index) => (
              <div className="pipeline-node" key={step}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {step}
              </div>
            ))}
          </div>
        </div>

        <div className="hero-cue">↓</div>
      </section>

    </main>
  );
}
