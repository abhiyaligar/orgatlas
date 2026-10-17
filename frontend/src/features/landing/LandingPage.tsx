import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";

interface LandingPageProps {
  onOpenDashboard: () => void;
}

const PROBLEMS = [
  {
    title: "The decision is gone",
    body: "The reasoning behind a choice outlives the thread it happened in. Six months on, the code shows what was built but not why the obvious alternative was rejected.",
  },
  {
    title: "The context is scattered",
    body: "Design docs, Slack, tickets, commit messages and code each hold a piece. Nobody holds all of them, so the answer to a simple question becomes an afternoon of searching.",
  },
  {
    title: "New engineers start from nothing",
    body: "Onboarding is a tour of the codebase with someone senior, which does not scale and answers the questions you did not know to ask.",
  },
];

const CAPABILITIES = [
  {
    title: "Ask in plain language",
    body: "Questions are answered from the graph, not from a keyword match. The path the answer took is shown, node by node, so you can check the reasoning rather than trust it.",
  },
  {
    title: "Every answer carries evidence",
    body: "Citations, quotes and file references travel with the answer. When evidence is thin, OrgAtlas says so instead of inventing a confident reply.",
  },
  {
    title: "Repositories understood",
    body: "Ingest a repository and its history becomes queryable: symbols, ownership, churn, and which commits actually implemented a decision.",
  },
  {
    title: "Documents and Slack in the same graph",
    body: "Upload a PDF, a design note or a CSV of decisions and pull in Slack history. The entities are linked, so a metric in a document connects to the service that moved it.",
  },
  {
    title: "Available to your tools",
    body: "A read-only MCP server exposes the same context to editors and agents, with the same evidence rules the UI follows.",
  },
  {
    title: "Honest about limits",
    body: "Aggregate questions and call graphs are not supported yet. When the graph cannot answer, it says that rather than approximating.",
  },
];

export function LandingPage({ onOpenDashboard }: LandingPageProps) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <span className="text-sm font-semibold tracking-[0.2em]">ORGATLAS</span>
          <nav aria-label="Primary" className="flex items-center gap-2">
            <ThemeToggle />
            <Button onClick={onOpenDashboard}>Dashboard</Button>
          </nav>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-6 pb-16 pt-20 text-center">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Engineering context, kept as evidence
          </p>
          <h1 className="mx-auto mt-4 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
            Ask why something was built, and get the proof
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
            OrgAtlas turns a codebase, its history, your documents and your team
            discussions into one knowledge graph — then answers questions from it
            with the citations attached.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Button size="lg" onClick={onOpenDashboard}>
              Open the dashboard
            </Button>
            <a
              href="#how-it-works"
              className="inline-flex h-10 items-center rounded-md border border-border px-5 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              See how it works
            </a>
          </div>
        </section>

        <section className="border-y border-border bg-muted/30">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="text-2xl font-semibold tracking-tight">
              The problem it exists to solve
            </h2>
            <div className="mt-8 grid gap-6 md:grid-cols-3">
              {PROBLEMS.map((problem) => (
                <div
                  key={problem.title}
                  className="rounded-lg border border-border bg-card p-6"
                >
                  <h3 className="font-medium">{problem.title}</h3>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {problem.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="text-2xl font-semibold tracking-tight">
            What it gives you
          </h2>
          <div className="mt-8 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {CAPABILITIES.map((capability) => (
              <div
                key={capability.title}
                className="rounded-lg border border-border bg-card p-6"
              >
                <h3 className="font-medium">{capability.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {capability.body}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-t border-border bg-muted/30">
          <div className="mx-auto max-w-3xl px-6 py-20 text-center">
            <h2 className="text-2xl font-semibold tracking-tight">
              Bring your own repository
            </h2>
            <p className="mt-4 text-muted-foreground">
              Ingest a repo, drop in a few documents, and ask the question you
              have been avoiding.
            </p>
            <Button size="lg" className="mt-8" onClick={onOpenDashboard}>
              Open the dashboard
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto max-w-6xl px-6 py-6 text-sm text-muted-foreground">
          OrgAtlas · answers are only as good as the evidence behind them
        </div>
      </footer>
    </div>
  );
}