import React from "react";
import { BookOpen, ExternalLink, X } from "lucide-react";

export const GUIDE_STORAGE_KEY = "synbios.guide.v1.dismissed";

const REPO_URL = "https://github.com/Moissanite-Labs/synbios";

type GuideProps = {
  open: boolean;
  onClose: () => void;
  demoMode: boolean;
};

function Ui({ children }: { children: React.ReactNode }) {
  return <strong className="guide-ui">{children}</strong>;
}

export function Guide({ open, onClose, demoMode }: GuideProps) {
  if (!open) return null;

  return (
    <div className="guide-backdrop" onClick={onClose}>
      <section
        className="guide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <p className="eyebrow">ORIENTATION</p>
            <h2 id="guide-title">How to use the forge</h2>
          </div>
          <button type="button" aria-label="Close guide" onClick={onClose}>
            <X size={20} />
          </button>
        </header>
        <div className="guide-body">
          <section>
            <h3>What Synbios is</h3>
            <p>
              Synbios is a local-first collaboration forge for{" "}
              <strong>people and agents</strong> working on the same record. You
              define projects and tasks with scope and acceptance criteria,
              grant agents only the capabilities they need, attach artifacts
              bound by digest, record test evidence, and require an{" "}
              <strong>independent human review</strong> before work is accepted.
            </p>
            <p>
              This web client is the reference UI for that workflow. The Python
              backend stores an append-only, hash-chained audit log in SQLite
              and exposes it over a loopback HTTP API.
            </p>
          </section>

          {demoMode && (
            <section className="guide-callout">
              <h3>This Pages build</h3>
              <p>
                You are viewing the <strong>in-browser demo</strong>. Rules
                match the real store, but nothing is saved to disk—refresh the
                tab and the record resets. For a persistent forge, run{" "}
                <code>python -m synbios serve</code> locally (see the{" "}
                <a href={REPO_URL} target="_blank" rel="noreferrer">
                  repository README
                </a>
                ).
              </p>
            </section>
          )}

          <section>
            <h3>Try the demo flow</h3>
            <p>
              Use the synthetic credentials on the login screen, then follow the
              same path a real operator would take:
            </p>
            <ol className="guide-steps">
              <li>
                On the login screen, click <Ui>Use demo operator credential</Ui>
                , then <Ui>Open workspace</Ui>.
              </li>
              <li>
                Open <Ui>Projects</Ui> in the sidebar. Review the seeded project
                (for example <Ui>Synthetic · Commons starter</Ui>) or click{" "}
                <Ui>New project</Ui> to create one.
              </li>
              <li>
                Go to <Ui>The forge</Ui>. Click a task card (for example{" "}
                <Ui>Define contribution guide</Ui>) or, from Projects, use{" "}
                <Ui>Create task</Ui> to define scope, criteria, and
                dependencies.
              </li>
              <li>
                In the task panel, click <Ui>Claim task</Ui>, then{" "}
                <Ui>Start work</Ui>.
              </li>
              <li>
                Click <Ui>Add artifact</Ui> and bind a document or Git revision
                with its SHA-256 digest. A new artifact becomes the current
                candidate; older evidence is marked stale.
              </li>
              <li>
                Click <Ui>Add evidence</Ui> and record test results tied to that
                exact artifact revision.
              </li>
              <li>
                When passing test evidence exists and dependencies are accepted,
                click <Ui>Submit for review</Ui>.
              </li>
              <li>
                Click <Ui>Sign out</Ui>, then sign in with{" "}
                <Ui>Switch to demo reviewer</Ui> (or paste the reviewer
                credential). Open the same task and click{" "}
                <Ui>Review candidate</Ui>. Choose approve or request changes,
                then <Ui>Save to record</Ui>.
              </li>
              <li>
                With the operator again, open the accepted task and click{" "}
                <Ui>Export</Ui> to download a portable bundle JSON.
              </li>
              <li>
                Open <Ui>Access &amp; trust</Ui>, click <Ui>Verify a bundle</Ui>
                , paste the export, and run verification.
              </li>
            </ol>
          </section>

          <section>
            <h3>What each area is for</h3>
            <dl className="guide-dl">
              <dt>The forge</dt>
              <dd>
                Task board and stats—where active work, reviews, and accepted
                outcomes are visible at a glance.
              </dd>
              <dt>Projects</dt>
              <dd>
                Boundaries for related tasks (name, description, repository
                link). Tasks inherit a project context for exports.
              </dd>
              <dt>Provenance</dt>
              <dd>
                The hash-chained event log—who did what, when, with commits to
                state integrity (<Ui>Record intact</Ui> in the header).
              </dd>
              <dt>Access &amp; trust</dt>
              <dd>
                Human and agent <Ui>principals</Ui>, task-scoped <Ui>grants</Ui>{" "}
                (claim, work, artifact, evidence, submit), and bundle
                verification without importing records.
              </dd>
              <dt>Principals &amp; grants</dt>
              <dd>
                Agents are first-class identities with their own credentials,
                but they cannot self-approve or bypass grants. Humans administer
                the workspace.
              </dd>
            </dl>
          </section>

          <section>
            <h3>How this differs from GitHub</h3>
            <p>
              GitHub hosts repositories, pull requests, and checks. Synbios does
              not replace that hosting—it records{" "}
              <strong>accountable task workflow</strong> on your machine:
            </p>
            <ul>
              <li>
                <strong>Explicit claims</strong>—an open task must be claimed
                before work proceeds; grants scope what an agent may do per
                task.
              </li>
              <li>
                <strong>Artifact + evidence binding</strong>—submissions tie
                test reports to an exact revision digest, not just a branch
                name.
              </li>
              <li>
                <strong>Independent human review</strong>—the reviewer must be a
                human principal other than the artifact author; approval seals
                the task in the same transaction as the checks.
              </li>
              <li>
                <strong>Local audit chain</strong>—events hash together to
                detect tampering with stored history (not a signature or remote
                witness).
              </li>
              <li>
                <strong>Verifiable exports</strong>—bundles carry commitments
                you can check offline; they do not merge code or grant access by
                themselves.
              </li>
            </ul>
            <p className="guide-muted">
              Not built in 0.1: remote federation, signed identity, running
              tests inside the forge, Git-host enforcement, or sandboxing agent
              tools—the roadmap describes planned directions.
            </p>
          </section>

          <section>
            <h3>Source &amp; docs</h3>
            <p>
              <a
                className="guide-repo"
                href={REPO_URL}
                target="_blank"
                rel="noreferrer"
              >
                Moissanite-Labs/synbios on GitHub
                <ExternalLink size={15} />
              </a>
              — README, trust model, API contract, and local setup instructions.
            </p>
          </section>
        </div>
        <footer>
          <button type="button" className="primary" onClick={onClose}>
            Got it
          </button>
        </footer>
      </section>
    </div>
  );
}

export function GuideButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="guide-trigger"
      aria-label="Open guide"
      onClick={onClick}
    >
      <BookOpen size={17} />
      Guide
    </button>
  );
}
