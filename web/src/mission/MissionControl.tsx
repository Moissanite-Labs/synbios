import {
  useEffect,
  useRef,
  useState,
  useId,
  cloneElement,
  isValidElement,
  type FormEvent,
  type ReactNode,
} from "react";
import "../style.css";
import CrystalLattice from "./CrystalLattice";
import {
  stages,
  stageNames,
  type Task,
  type Snapshot,
  type Principal,
  type Stage,
  type Project,
  type Artifact,
} from "./types";

const demoMode = import.meta.env.VITE_DEMO_MODE === "true";
const humanize = (s: string) => s.replaceAll("_", " ").replaceAll(".", " · ");
const lines = (v: FormDataEntryValue | null) =>
  String(v || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
const text = (v: FormDataEntryValue | null) => String(v || "").trim();
const when = (v: string) =>
  new Date(v).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const initials = (v: string) =>
  v
    .split(/\s+/)
    .map((x) => x[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
const psQuote = (v: string) => "\'" + v.replaceAll("\'", "\'\'") + "\'";
const quote = (v: string) => "'" + v.replaceAll("'", "'\"'\"'") + "'";
const terminal = (t: Task) => ["accepted", "cancelled"].includes(t.status);
const revision = (t: Task) => t.revision ?? 1;
const eventLabels: Record<string, string> = {
  "task.create": "Work created",
  "plan.create": "Work plan created",
  "task.claim": "Work claimed",
  "task.delegate": "Work delegated",
  "task.assign": "Ownership changed",
  "task.update": "Direction updated",
  "task.report": "Progress reported",
  "task.transition": "Work status changed",
  "decision.create": "Decision requested",
  "decision.resolve": "Decision recorded",
  "decision.withdraw": "Decision withdrawn",
  "artifact.add": "Result attached",
  "evidence.add": "Evidence recorded",
  "review.create": "Review recorded",
};
const stageOf = (t: Task) => t.stage || "build";
const latestReport = (t: Task) =>
  t.reports
    ?.filter(
      (r) => (r.assignment_revision ?? 0) === (t.assignment_revision ?? 0),
    )
    .at(-1);

function Avatar({ person }: { person?: Principal }) {
  return (
    <div
      className={`av ${person?.kind === "human" ? "h" : person ? "a" : "unassigned"}`}
      aria-hidden="true"
    >
      <span>{person ? initials(person.name) : "?"}</span>
    </div>
  );
}
function Brand() {
  return (
    <div className="brand">
      <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
        <polygon
          points="11,1 20,6 20,16 11,21 2,16 2,6"
          fill="none"
          stroke="#eceef0"
          strokeWidth="1.2"
        />
        <circle cx="11" cy="11" r="2.4" fill="#f2ab6d" />
        <rect
          x="13.6"
          y="4.6"
          width="3.2"
          height="3.2"
          transform="rotate(45 15.2 6.2)"
          fill="#7cc6f2"
        />
        <line
          x1="11"
          y1="11"
          x2="15.2"
          y2="6.2"
          stroke="#eceef0"
          strokeWidth=".8"
        />
      </svg>
      <span>SYNBIOS</span>
    </div>
  );
}
function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {isValidElement(children)
        ? cloneElement(
            children as React.ReactElement<Record<string, unknown>>,
            { id, "aria-describedby": hint ? `${id}-hint` : undefined },
          )
        : children}
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}
function Dialog({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => d?.close();
  }, []);
  return (
    <dialog
      className="mission-dialog"
      ref={ref}
      aria-labelledby="dialog-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <header>
        <h2 id="dialog-title">{title}</h2>
        <button
          type="button"
          className="mini"
          aria-label="Close dialog"
          onClick={close}
        >
          Close
        </button>
      </header>
      {children}
    </dialog>
  );
}

export default function MissionControl() {
  const [token, setToken] = useState(
    sessionStorage.getItem("synbios.token") || "",
  );
  const [state, setState] = useState<Snapshot | null>(null);
  const [projectId, setProjectId] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [stageFilter, setStageFilter] = useState<Stage | "">("");
  const [dialog, setDialog] = useState("");
  const [formTask, setFormTask] = useState<Task | undefined>();
  const [formProject, setFormProject] = useState<Project | undefined>();
  const [formArtifact, setFormArtifact] = useState<Artifact | undefined>();
  const dialogEpoch = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [brief, setBrief] = useState("");
  const [briefTitle, setBriefTitle] = useState("Task brief");
  const [secretBrief, setSecretBrief] = useState(false);
  const [guide, setGuide] = useState(
    localStorage.getItem("synbios.mission.guide") !== "seen",
  );
  const [paused, setPaused] = useState(false);
  const [decisionNote, setDecisionNote] = useState("");
  const [lastSync, setLastSync] = useState("");
  const generation = useRef(0);
  const requestVersion = useRef(0);
  const workInFlight = useRef(false);
  const handoffInFlight = useRef(false);
  const actor = state?.actor;
  const readOnly = demoMode || (!!state && !state.integrity.valid);
  const project =
    state?.projects.find((p) => p.id === projectId) || state?.projects[0];
  const tasks = (state?.tasks || []).filter(
    (t) => t.project_id === project?.id,
  );
  const openDecisions = tasks
    .filter((t) => !terminal(t))
    .flatMap((t) =>
      (t.decisions || [])
        .filter((d) => d.status === "open")
        .map((d) => ({ task: t, decision: d })),
    );
  const pendingReviews = tasks.filter((t) => t.status === "in_review");
  const selected =
    tasks.find((t) => t.id === selectedId) ||
    openDecisions[0]?.task ||
    pendingReviews[0] ||
    tasks.find((t) => !terminal(t)) ||
    tasks[0];
  const decision =
    selected && !terminal(selected)
      ? selected.decisions?.find((d) => d.status === "open")
      : undefined;
  const latestDecision = decision || selected?.decisions?.at(-1);
  const owner = state?.principals.find((p) => p.id === selected?.assignee_id);
  const isHuman = actor?.kind === "human";
  const canCoordinate =
    isHuman ||
    !!state?.coordinator_grants?.some(
      (g) =>
        g.project_id === project?.id &&
        g.principal_id === actor?.id &&
        !g.revoked_at,
    );
  const currentArtifact = selected?.artifacts.at(-1);
  const staleContract =
    !!currentArtifact &&
    (currentArtifact.contract_revision ?? 1) !==
      (selected?.contract_revision ?? 1);
  const currentEvidence =
    selected?.evidence.filter(
      (e) =>
        e.artifact_id === currentArtifact?.id &&
        e.artifact_digest === currentArtifact?.digest &&
        e.revision === currentArtifact?.revision &&
        !e.stale &&
        !staleContract,
    ) || [];
  const dependencyTasks = selected
    ? selected.dependencies
        .map((id) => state?.tasks.find((t) => t.id === id))
        .filter((t): t is Task => !!t)
    : [];
  const filteredTasks = tasks.filter(
    (t) => !stageFilter || stageOf(t) === stageFilter,
  );
  const activeTasks = tasks.filter((t) => !terminal(t));
  const blockedTasks = activeTasks.filter((t) => (t.blockers || []).length > 0);
  const canWork = (task: Task) =>
    isHuman ||
    !!state?.grants.some(
      (g) =>
        g.principal_id === actor?.id &&
        g.task_id === task.id &&
        !g.revoked_at &&
        g.capabilities.includes("work"),
    );
  const name = (id?: string | null) =>
    state?.principals.find((p) => p.id === id)?.name || "Unassigned";
  const overlaps = (state?.scope_overlaps || []).filter((o) =>
    o.task_ids?.every((id) => tasks.some((t) => t.id === id)),
  );
  const apiBase = window.location.origin;

  function logout() {
    generation.current++;
    requestVersion.current++;
    sessionStorage.removeItem("synbios.token");
    setToken("");
    setState(null);
    setProjectId("");
    setSelectedId("");
    setDialog("");
    setBrief("");
    setSecretBrief(false);
    setError("");
    setNotice("");
    setBusy(false);
    workInFlight.current = false;
    handoffInFlight.current = false;
  }
  async function api(path: string, method = "GET", body?: unknown) {
    const g = generation.current;
    if (demoMode) {
      const demo = await import("../demo/store");
      return demo.demoRequest(path, method, token, body);
    }
    const r = await fetch("/api/" + path, {
      method,
      headers: {
        Authorization: "Bearer " + token,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (r.status === 401 && g === generation.current) {
        logout();
        setError(
          "Your connection key has expired or was revoked. Open this workspace again with a current key.",
        );
      }
      throw Object.assign(
        new Error(data.error || `Request failed (${r.status})`),
        { status: r.status },
      );
    }
    return data;
  }
  async function refresh(silent = false) {
    const g = generation.current,
      order = ++requestVersion.current;
    try {
      const next = (await api("state")) as Snapshot;
      if (g !== generation.current || order !== requestVersion.current) return;
      setState(next);
      setLastSync(new Date().toLocaleTimeString());
      if (!silent) setError("");
    } catch (e) {
      if (g === generation.current && order === requestVersion.current) {
        setError((e as Error).message);
        if ((e as Error & { status?: number }).status === 409)
          setState((s) =>
            s ? { ...s, integrity: { ...s.integrity, valid: false } } : s,
          );
      }
    }
  }
  useEffect(() => {
    if (!token) return;
    sessionStorage.setItem("synbios.token", token);
    void refresh();
    const id = window.setInterval(() => {
      if (!workInFlight.current && document.visibilityState === "visible")
        void refresh(true);
    }, 4000);
    return () => window.clearInterval(id);
  }, [token]);
  useEffect(() => {
    setDecisionNote("");
  }, [selected?.id, decision?.id]);
  useEffect(() => {
    document.documentElement.classList.toggle("motion-paused", paused);
  }, [paused]);
  async function command(action: string, payload: Record<string, unknown>) {
    if (workInFlight.current) return null;
    if (readOnly) {
      setError(
        "This workspace is read-only. Restore a valid local record before changing the mission.",
      );
      return null;
    }
    const g = generation.current;
    workInFlight.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    requestVersion.current++;
    try {
      const result = await api("commands/" + action, "POST", payload);
      if (g !== generation.current) return null;
      await refresh();
      if (g !== generation.current) return null;
      return result;
    } catch (e) {
      if (g === generation.current) {
        setError((e as Error).message);
        await refresh(true);
      }
      return null;
    } finally {
      if (g === generation.current) {
        setBusy(false);
        workInFlight.current = false;
      }
    }
  }
  async function openDemo() {
    const demo = await import("../demo/store");
    setToken(demo.demoTokens.operator);
  }
  function openDialog(kind: string) {
    dialogEpoch.current++;
    setFormTask(selected ? structuredClone(selected) : undefined);
    setFormProject(project ? structuredClone(project) : undefined);
    setFormArtifact(
      currentArtifact ? structuredClone(currentArtifact) : undefined,
    );
    setError("");
    setDialog(kind);
  }
  function closeDialog() {
    if (workInFlight.current || handoffInFlight.current) return;
    dialogEpoch.current++;
    setDialog("");
    setBrief("");
    setSecretBrief(false);
    setFormTask(undefined);
    setFormProject(undefined);
    setFormArtifact(undefined);
  }
  function chooseTask(id: string) {
    setSelectedId(id);
    setHighlighted(null);
  }
  async function showPrompt(task?: Task) {
    const g = generation.current;
    const epoch = ++dialogEpoch.current;
    try {
      const path = task
        ? `tasks/${encodeURIComponent(task.id)}/prompt`
        : `projects/${encodeURIComponent(project!.id)}/coordinator-prompt`;
      const result = await api(path);
      if (g !== generation.current || epoch !== dialogEpoch.current) return;
      try {
        await navigator.clipboard.writeText(result.prompt);
        if (g !== generation.current || epoch !== dialogEpoch.current) return;
        setNotice(
          `${task ? "Task" : "Coordinator"} prompt copied. Paste it into the agent session; use that agent’s own connection key.`,
        );
      } catch {
        if (g !== generation.current || epoch !== dialogEpoch.current) return;
        setBrief(result.prompt);
        setSecretBrief(false);
        setBriefTitle(task ? "Task brief" : "Coordinator brief");
        setDialog("brief");
        setNotice("Clipboard access is unavailable. Copy the brief below.");
      }
    } catch (e) {
      if (g === generation.current && epoch === dialogEpoch.current)
        setError((e as Error).message);
    }
  }
  async function copyBrief() {
    try {
      await navigator.clipboard.writeText(brief);
      setNotice(
        "Brief copied. Paste it into the agent session you want to use.",
      );
    } catch {
      const box = document.getElementById(
        "agent-brief",
      ) as HTMLTextAreaElement | null;
      box?.focus();
      box?.select();
      setNotice(
        "Your browser did not allow clipboard access. The brief is selected; copy it using your keyboard.",
      );
    }
  }
  async function submitForm(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const g = generation.current;
    const epoch = dialogEpoch.current;
    const data = new FormData(e.currentTarget);
    let result: Record<string, unknown> | null = null;
    if (dialog === "mission") {
      result = await command("project.create", {
        name: text(data.get("name")),
        description: text(data.get("description")),
        repository: text(data.get("workspace")),
        workspace: text(data.get("workspace")),
      });
      if (result) {
        setProjectId(String(result.id));
        setSelectedId("");
      }
    }
    if (dialog === "mission-edit" && formProject)
      result = await command("project.update", {
        project_id: formProject.id,
        expected_revision: formProject.revision ?? 1,
        name: text(data.get("name")),
        description: text(data.get("description")),
      });
    if (dialog === "slice" && formProject) {
      result = await command("plan.create", {
        project_id: formProject.id,
        tasks: [
          {
            key: "work",
            title: text(data.get("title")),
            description: text(data.get("description")),
            criteria: lines(data.get("criteria")),
            scope: lines(data.get("scope")),
            stage: text(data.get("stage")),
            priority: text(data.get("priority")),
            dependencies: data.getAll("dependencies").map(String),
          },
        ],
      });
      if (result && Array.isArray(result.tasks) && result.tasks[0])
        setSelectedId(String((result.tasks[0] as Task).id));
    }
    if (dialog === "redirect" && formTask) {
      result = await command("task.update", {
        task_id: formTask.id,
        expected_revision: revision(formTask),
        title: text(data.get("title")),
        description: text(data.get("description")),
        criteria: lines(data.get("criteria")),
        scope: lines(data.get("scope")),
        stage: text(data.get("stage")),
        priority: text(data.get("priority")),
        candidate_path: text(data.get("candidate_path")),
        dependencies: data.getAll("dependencies").map(String),
      });
    }
    if (dialog === "assign" && formTask)
      result = await command("task.assign", {
        task_id: formTask.id,
        principal_id: text(data.get("principal_id")),
        expected_revision: revision(formTask),
      });
    if (
      (dialog === "delegate" && formTask) ||
      (dialog === "coordinator" && formProject)
    ) {
      const isCoordinator = dialog === "coordinator";
      handoffInFlight.current = true;
      try {
        result = await command(
          isCoordinator ? "coordinator.enroll" : "task.delegate",
          {
            ...(isCoordinator
              ? { project_id: formProject!.id }
              : {
                  task_id: formTask!.id,
                  expected_revision: revision(formTask!),
                }),
            name: text(data.get("name")),
          },
        );
        if (result) {
          setBusy(true);
          try {
            const path = isCoordinator
              ? `projects/${encodeURIComponent(formProject!.id)}/coordinator-prompt`
              : `tasks/${encodeURIComponent(formTask!.id)}/prompt`;
            const generated = await api(path);
            if (g !== generation.current || epoch !== dialogEpoch.current)
              return;
            const credential = String(result.token || "");
            setBrief(
              `${generated.prompt}\n\n## Connect this session\nThis credential belongs to this agent only. Keep it out of commits, logs, and shared notes.\n\n\`\`\`sh\nexport SYNBIOS_URL=${quote(apiBase)}\nexport SYNBIOS_TOKEN=${quote(credential)}\npython -m synbios state\n\`\`\`\n\nPowerShell:\n\n\`\`\`powershell\n$env:SYNBIOS_URL = ${psQuote(apiBase)}\n$env:SYNBIOS_TOKEN = ${psQuote(credential)}\npython -m synbios state\n\`\`\`\n`,
            );
            setSecretBrief(true);
            setBriefTitle(isCoordinator ? "Coordinator brief" : "Task brief");
            setDialog("brief");
            return;
          } catch (e) {
            if (g !== generation.current || epoch !== dialogEpoch.current)
              return;
            // Enrollment committed even if fetching the prose fails. Retain the
            // once-issued token so the operator can recover rather than lose it.
            setBrief(
              `Agent created. Fetch the ${isCoordinator ? "coordinator" : "task"} prompt again after reconnecting.\n\nexport SYNBIOS_URL=${quote(apiBase)}\nexport SYNBIOS_TOKEN=${quote(String(result.token || ""))}\n\nPowerShell:\n$env:SYNBIOS_URL = ${psQuote(apiBase)}\n$env:SYNBIOS_TOKEN = ${psQuote(String(result.token || ""))}\n`,
            );
            setSecretBrief(true);
            setBriefTitle("Connection key — save before closing");
            setDialog("brief");
            setError((e as Error).message);
            return;
          }
        }
      } finally {
        handoffInFlight.current = false;
        if (g === generation.current) setBusy(false);
      }
    }
    if (dialog === "report" && formTask)
      result = await command("task.report", {
        task_id: formTask.id,
        expected_revision: revision(formTask),
        summary: text(data.get("summary")),
        progress:
          text(data.get("progress")) === ""
            ? null
            : Number(data.get("progress")),
        blocker: text(data.get("blocker")),
      });
    if (dialog === "decision" && formTask)
      result = await command("decision.create", {
        task_id: formTask.id,
        expected_revision: revision(formTask),
        title: text(data.get("title")),
        question: text(data.get("question")),
        options: lines(data.get("options")),
      });
    if (dialog === "artifact" && formTask)
      result = await command("artifact.add", {
        task_id: formTask.id,
        title: text(data.get("title")),
        kind: text(data.get("kind")),
        revision: text(data.get("revision")),
        digest: text(data.get("digest")),
        uri: text(data.get("uri")),
        summary: text(data.get("summary")),
      });
    if (dialog === "evidence" && formTask && formArtifact)
      result = await command("evidence.add", {
        task_id: formTask.id,
        artifact_id: formArtifact.id,
        artifact_digest: formArtifact.digest,
        revision: formArtifact.revision,
        kind: "test",
        status: text(data.get("status")),
        command: text(data.get("command")),
        summary: text(data.get("summary")),
        tool: text(data.get("tool")),
        tool_version: text(data.get("tool_version")),
        assumptions: [],
      });
    if (result && g === generation.current && epoch === dialogEpoch.current) {
      closeDialog();
      setNotice(
        "Saved. Your agents will see the updated mission on their next refresh.",
      );
    }
  }
  async function resolveDecision(choice: string) {
    if (!selected || !decision) return;
    const result = await command("decision.resolve", {
      task_id: selected.id,
      decision_id: decision.id,
      expected_revision: revision(selected),
      choice,
      note: decisionNote,
    });
    if (result)
      setNotice("Decision recorded. The choice is now available to the team.");
  }
  async function review(choice: "approved" | "changes_requested") {
    if (!selected || !currentArtifact) return;
    const result = await command("review.create", {
      task_id: selected.id,
      artifact_id: currentArtifact.id,
      revision: currentArtifact.revision,
      decision: choice,
      comment: decisionNote,
    });
    if (result)
      setNotice(
        choice === "approved"
          ? "Review recorded. This work is accepted in Synbios."
          : "Changes requested. Your note is available to the team.",
      );
  }

  if (!state)
    return (
      <>
        <header className="top">
          <Brand />
          <span className="spacer" />
          <span className="chip">Local mission control</span>
        </header>
        <main className="connect wrap">
          <div className="mono">Different minds. Shared possibility.</div>
          <h1>
            Give your agents
            <br />
            <em>a shared mission.</em>
          </h1>
          <p>
            See what each agent is building, how the work fits together, and
            where your judgment can move it forward.
          </p>
          <section className="panel connect-card">
            <h2>
              {demoMode ? "Explore the Crystal Lattice" : "Open your workspace"}
            </h2>
            {demoMode ? (
              <>
                <p>
                  A synthetic example of the same mission view. Real
                  collaboration runs on your machine.
                </p>
                <button className="btn primary" onClick={() => void openDemo()}>
                  Explore example mission
                </button>
              </>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const key = text(new FormData(e.currentTarget).get("token"));
                  generation.current++;
                  setToken(key);
                }}
              >
                <Field
                  label="Workspace connection key"
                  hint="Your local Synbios launch command prints this key. It stays in this browser tab."
                >
                  <input
                    type="password"
                    name="token"
                    required
                    autoComplete="off"
                  />
                </Field>
                <button className="btn primary" type="submit">
                  Open workspace
                </button>
              </form>
            )}
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <details className="connection-help">
              <summary>First time here?</summary>
              <p>
                Run Synbios locally with{" "}
                <code>
                  python -m synbios start --workspace /path/to/your/project
                </code>
                . Open the address it prints, then paste its connection key
                here.
              </p>
              <p>
                Once connected, describe your goal, ask a coordinator to divide
                it into work, and give each agent its own task brief.
              </p>
            </details>
          </section>
        </main>
      </>
    );

  return (
    <>
      <a className="skip" href="#mission">
        Skip to mission
      </a>
      {demoMode && (
        <section className="demo-banner">
          <div>
            <strong>SYNTHETIC EXAMPLE</strong>
            <p>
              Explore the designer’s Crystal Lattice with example work. Nothing
              here runs agents or changes a real project.
            </p>
          </div>
          <a
            className="mini"
            href="https://github.com/Moissanite-Labs/synbios#start-with-your-codebase"
          >
            Run your own local mission
          </a>
        </section>
      )}
      <header className="top">
        <Brand />
        <nav className="crumbs" aria-label="Workspace">
          <span>Mission control</span>
          <span aria-hidden="true">/</span>
          {state.projects.length > 0 && (
            <select
              aria-label="Current mission"
              value={project?.id || ""}
              onChange={(e) => {
                setProjectId(e.target.value);
                setSelectedId("");
                setStageFilter("");
              }}
            >
              {state.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </nav>
        <span className="spacer" />
        <button className="mini" onClick={() => setGuide((v) => !v)}>
          Guide
        </button>
        <button
          className="mini"
          aria-label="Refresh workspace"
          onClick={() => void refresh()}
        >
          Refresh
        </button>
        <div className="me">
          <Avatar person={actor} />
          <span>{actor?.name}</span>
        </div>
        <button className="mini" onClick={logout}>
          Disconnect
        </button>
      </header>
      <main className="wrap" id="mission">
        {error && (
          <div className="status-message error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="status-message" role="status">
            {notice}
            <button
              className="mini"
              aria-label="Dismiss notification"
              onClick={() => setNotice("")}
            >
              Dismiss
            </button>
          </div>
        )}
        {!state.integrity.valid && (
          <div className="status-message error" role="alert">
            This workspace’s record could not be verified. Refresh and inspect
            the local store before relying on it.
          </div>
        )}
        <section className="hero" aria-labelledby="mission-title">
          <div>
            <div className="mono">
              Your mission · {demoMode ? "example data" : "local workspace"}
            </div>
            <h1 id="mission-title">
              {project?.name || "What will we build?"}
              <em>
                {project ? "shared possibility" : "start with an outcome"}
              </em>
            </h1>
            <p>
              {project?.description ||
                "Describe what you want to achieve. Synbios gives your agents a shared plan and gives you a clear view of their work."}
            </p>
          </div>
          <ol className="stages" aria-label="Project stages">
            {stages.map((stage, i) => {
              const group = tasks.filter((t) => stageOf(t) === stage),
                done = group.filter((t) => t.status === "accepted").length,
                current = group.some((t) => !terminal(t));
              return (
                <li
                  key={stage}
                  className={`stage ${group.length && done === group.length ? "done" : current ? "now" : ""}`}
                  style={
                    {
                      "--p": `${group.length ? (done / group.length) * 100 : 0}%`,
                    } as React.CSSProperties
                  }
                >
                  <div className="n">{String(i + 1).padStart(3, "0")}</div>
                  <div className="t">{stageNames[i]}</div>
                  <i className="bar" />
                </li>
              );
            })}
          </ol>
        </section>
        {guide && (
          <section className="orientation" aria-label="Getting started">
            <div>
              <strong>Start with the outcome. Let the work take shape.</strong>
              <p>
                1. Describe the mission. 2. Give a coordinator its brief to
                create work slices. 3. Delegate slices to your agents. The
                crystal shows their work; the decision panel brings the next
                choice to you.
              </p>
              <p className="fine">
                Select a node to see its owner, progress, dependencies and
                evidence. Agents report through the local API; registration
                alone does not mean a session is running.
              </p>
            </div>
            <button
              className="mini"
              onClick={() => {
                setGuide(false);
                localStorage.setItem("synbios.mission.guide", "seen");
              }}
            >
              Got it
            </button>
          </section>
        )}
        <section className="mission-bar" aria-label="Mission actions">
          <div className="mission-counts">
            <span>
              <b>{activeTasks.length}</b> open pieces
            </span>
            <button
              className="text-button"
              onClick={() =>
                chooseTask(
                  openDecisions[0]?.task.id ||
                    pendingReviews[0]?.id ||
                    selected?.id ||
                    "",
                )
              }
            >
              <b>{openDecisions.length + pendingReviews.length}</b> need your
              judgment
            </button>
            <span>
              <b>{blockedTasks.length}</b> blocked
            </span>
            <span>
              <b>{activeTasks.filter((t) => !t.assignee_id).length}</b>{" "}
              unassigned
            </span>
          </div>
          <div className="actions">
            <button
              className="mini"
              disabled={readOnly || !isHuman}
              onClick={() => openDialog("mission")}
            >
              {project ? "New mission" : "Create mission"}
            </button>
            {project && (
              <>
                <button
                  className="mini"
                  disabled={readOnly || !isHuman}
                  onClick={() => openDialog("mission-edit")}
                >
                  Edit mission
                </button>
                <button
                  className="btn ghost"
                  disabled={readOnly || !isHuman}
                  onClick={() => openDialog("coordinator")}
                >
                  Plan with a coordinator
                </button>
                <button
                  className="btn primary"
                  disabled={readOnly || !canCoordinate}
                  onClick={() => openDialog("slice")}
                >
                  Add work slice
                </button>
              </>
            )}
          </div>
        </section>
        {overlaps.length > 0 && (
          <details className="scope-attention">
            <summary>
              {overlaps.length} shared work{" "}
              {overlaps.length === 1 ? "area" : "areas"} to coordinate
            </summary>
            <p className="fine">
              These declared scopes overlap. Agents should agree on their
              boundaries and keep changes in separate checkouts.
            </p>
            <ul>
              {overlaps.map((o, i) => (
                <li key={i}>
                  {o.task_ids?.map((id, j) => (
                    <span key={id}>
                      {j > 0 && " ↔ "}
                      <button
                        className="source-link"
                        onClick={() => chooseTask(id)}
                      >
                        {tasks.find((t) => t.id === id)?.title}
                      </button>
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </details>
        )}
        <div className="grid">
          <CrystalLattice
            project={project}
            onMissionSelect={() =>
              isHuman && !demoMode && openDialog("mission-edit")
            }
            tasks={tasks}
            principals={state.principals}
            selected={selected?.id || ""}
            highlighted={highlighted}
            onSelect={chooseTask}
            onStage={(s) => {
              setStageFilter((v) => (v === s ? "" : (s as Stage)));
              document.getElementById("work-list")?.scrollIntoView({
                behavior: paused ? "instant" : "smooth",
                block: "start",
              });
            }}
          />
          <div className="col-d">
            <section
              className="panel decision"
              aria-labelledby="decision-heading"
            >
              {!selected ? (
                <>
                  <div className="dtop">
                    <div className="dlabel mono">
                      <i className="live-dot" />
                      Your next move
                    </div>
                    <span className="pill">Ready to begin</span>
                  </div>
                  <h3 id="decision-heading">
                    {project
                      ? "Give the mission its first piece of work"
                      : "Name the outcome you want"}
                  </h3>
                  <p className="reason">
                    {project
                      ? "A coordinator can read the mission and propose connected work slices. You can also add the first slice yourself."
                      : "A mission gives every agent the same goal. Its work will grow outward through the crystal, from idea to ship."}
                  </p>
                  <div className="principle">
                    <span className="bar" />
                    <div className="in">
                      <blockquote>
                        “Different minds. Shared possibility.”
                      </blockquote>
                      <p>
                        Each piece has an owner, a clear outcome and evidence of
                        what changed.
                      </p>
                    </div>
                  </div>
                  <div className="actions empty-actions">
                    <button
                      className="btn primary"
                      disabled={readOnly || !isHuman}
                      onClick={() =>
                        openDialog(project ? "coordinator" : "mission")
                      }
                    >
                      {project ? "Plan with a coordinator" : "Create mission"}
                    </button>
                    {project && (
                      <button
                        className="btn ghost"
                        disabled={readOnly || !canCoordinate}
                        onClick={() => openDialog("slice")}
                      >
                        Add work slice
                      </button>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <div className="dtop">
                    <div className="dlabel mono">
                      <i
                        className={`live-dot ${decision || selected.status === "in_review" ? "" : "quiet"}`}
                      />
                      {decision
                        ? "Decision · needs your judgment"
                        : selected.status === "in_review"
                          ? "Review · needs your judgment"
                          : "Selected work"}
                    </div>
                    <span
                      className={`pill ${selected.status === "accepted" ? "signed" : ""}`}
                    >
                      {decision ? "Open choice" : humanize(selected.status)}
                    </span>
                  </div>
                  <h3 id="decision-heading">
                    {decision?.title || selected.title}
                  </h3>
                  <div className="by">
                    <Avatar person={owner} />
                    <span>
                      {owner ? (
                        <>
                          Owned by <b>{owner.name}</b> · {owner.kind}
                        </>
                      ) : (
                        <b>Ready for an owner</b>
                      )}
                      <span className="bybuild">
                        {" "}
                        · {stageNames[stages.indexOf(stageOf(selected))]}
                      </span>
                    </span>
                  </div>
                  <div className="dsec dbody">
                    <div className="mainc">
                      <h4 className="mono">
                        {decision ? "Why this needs you" : "The outcome"}
                      </h4>
                      <p className="reason">
                        {decision?.question ||
                          selected.description ||
                          selected.title}
                      </p>
                      {decision && (
                        <p className="fine">
                          For: {selected.title} · requested by{" "}
                          {name(decision.created_by)}
                        </p>
                      )}
                      <dl className="conseq">
                        <div>
                          <dt>Next action</dt>
                          <dd>
                            {decision
                              ? "Choose a direction"
                              : selected.status === "in_review"
                                ? "Review the current result"
                                : selected.status === "accepted"
                                  ? "Available to dependent work"
                                  : !selected.assignee_id
                                    ? "Give an agent its task brief"
                                    : (selected.blockers || []).length
                                      ? "Resolve the blocker below"
                                      : "Continue the assigned work"}
                          </dd>
                        </div>
                        <div>
                          <dt>Depends on</dt>
                          <dd>
                            {dependencyTasks.length
                              ? dependencyTasks.map((t) => t.title).join(", ")
                              : "Ready independently"}
                          </dd>
                        </div>
                        <div>
                          <dt>Current signal</dt>
                          <dd>
                            {latestReport(selected)?.summary ||
                              (currentArtifact
                                ? "Result attached; inspect its evidence"
                                : "No progress report yet")}
                          </dd>
                        </div>
                      </dl>
                      {staleContract && (
                        <p className="error">
                          The direction changed after this result was attached.
                          Ask the agent for an updated result and fresh
                          evidence.
                        </p>
                      )}
                      {(selected.blockers || []).length > 0 && (
                        <div className="blockers">
                          <h4 className="mono">What is holding this up</h4>
                          <ul>
                            {selected.blockers!.map((b, i) => (
                              <li key={i}>{b.summary}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <details className="criteria" open={!decision}>
                        <summary>What done looks like</summary>
                        <ul>
                          {selected.criteria.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      </details>
                    </div>
                    <aside
                      className="margin"
                      aria-label="Sources and connections"
                    >
                      <div className="srchead">
                        <h4 className="mono">Sources &amp; connections</h4>
                      </div>
                      <ol className="notes">
                        {dependencyTasks.map((t, i) => (
                          <li
                            className={`note ${state.principals.find((p) => p.id === t.assignee_id)?.kind === "human" ? "h" : ""}`}
                            key={t.id}
                            onMouseEnter={() => setHighlighted(t.id)}
                            onMouseLeave={() => setHighlighted(null)}
                            onFocus={() => setHighlighted(t.id)}
                            onBlur={() => setHighlighted(null)}
                          >
                            <span className="num">{i + 1}</span>
                            <div>
                              <button
                                className="source-link"
                                onClick={() => chooseTask(t.id)}
                              >
                                {t.title}
                              </button>
                              <div className="what">
                                {humanize(t.status)} · {name(t.assignee_id)}
                              </div>
                            </div>
                          </li>
                        ))}
                        {currentArtifact && (
                          <li className="note">
                            <span className="num">
                              {dependencyTasks.length + 1}
                            </span>
                            <div>
                              <div className="who">{currentArtifact.title}</div>
                              <div className="what">
                                {currentArtifact.summary ||
                                  humanize(currentArtifact.kind)}
                              </div>
                              <div className="meta">
                                {currentEvidence.length} current evidence record
                                {currentEvidence.length === 1 ? "" : "s"}
                              </div>
                            </div>
                          </li>
                        )}
                        {currentEvidence.map((e) => (
                          <li className="note" key={e.id}>
                            <span className={`evidence-mark ${e.status}`}>
                              {e.status === "passed"
                                ? "✓"
                                : e.status === "failed"
                                  ? "!"
                                  : "?"}
                            </span>
                            <div>
                              <div className="who">
                                {humanize(e.kind)} · {e.status}
                              </div>
                              <div className="what">{e.summary}</div>
                              <div className="meta">
                                Reported with {e.tool} {e.tool_version}
                              </div>
                            </div>
                          </li>
                        ))}
                      </ol>
                      {!dependencyTasks.length && !currentArtifact && (
                        <p className="fine">
                          No sources attached yet. Dependencies, results and
                          test evidence will appear here.
                        </p>
                      )}
                      <p className="fine">
                        Evidence is reported by contributors. Open the record to
                        inspect exact revisions.
                      </p>
                    </aside>
                  </div>
                  {decision ? (
                    <>
                      <div className="signrow">
                        <div>
                          <div className="sigline">
                            <span className="x">×</span>
                            <span className="hint">
                              your direction goes here
                            </span>
                          </div>
                          <div className="under">Decision by {actor?.name}</div>
                        </div>
                        <div className="actions actions-main">
                          {decision.options.map((option) => (
                            <button
                              key={option}
                              className="btn primary"
                              disabled={busy || readOnly || !isHuman}
                              onClick={() => void resolveDecision(option)}
                            >
                              {option}
                            </button>
                          ))}
                        </div>
                      </div>
                      <Field
                        label="Decision note"
                        hint="Optional context for the agents continuing this work."
                      >
                        <textarea
                          value={decisionNote}
                          onChange={(e) => setDecisionNote(e.target.value)}
                          rows={2}
                        />
                      </Field>
                    </>
                  ) : selected.status === "in_review" ? (
                    <>
                      <div className="signrow">
                        <div>
                          <div className="sigline">
                            <span className="x">×</span>
                            <span className="hint">your review goes here</span>
                          </div>
                          <div className="under">Review by {actor?.name}</div>
                        </div>
                        <div className="actions actions-main">
                          <button
                            className="btn primary"
                            disabled={
                              busy ||
                              readOnly ||
                              !isHuman ||
                              currentArtifact?.created_by === actor?.id
                            }
                            onClick={() => void review("approved")}
                          >
                            Approve current result
                          </button>
                          <button
                            className="btn ghost"
                            disabled={
                              busy ||
                              readOnly ||
                              !isHuman ||
                              currentArtifact?.created_by === actor?.id
                            }
                            onClick={() => void review("changes_requested")}
                          >
                            Request changes
                          </button>
                        </div>
                      </div>
                      <Field label="Review note">
                        <textarea
                          value={decisionNote}
                          onChange={(e) => setDecisionNote(e.target.value)}
                          rows={2}
                        />
                      </Field>
                      {currentArtifact?.created_by === actor?.id && (
                        <p className="fine">
                          A different person must review a result you authored.
                        </p>
                      )}
                    </>
                  ) : latestDecision?.status === "resolved" ? (
                    <div className="decision-record">
                      <div className="sigline signed">
                        <span className="x">×</span>
                        <span className="record-signature">
                          {name(latestDecision.resolved_by)}
                        </span>
                      </div>
                      <div className="under">
                        Decision recorded ·{" "}
                        {latestDecision.resolved_at &&
                          when(latestDecision.resolved_at)}
                      </div>
                      <p>
                        <b>{latestDecision.title}:</b> {latestDecision.choice}
                        {latestDecision.note && ` — ${latestDecision.note}`}
                      </p>
                    </div>
                  ) : null}
                  <div className="actions work-actions">
                    <button
                      className="btn primary"
                      disabled={readOnly || busy}
                      onClick={() => void showPrompt(selected)}
                    >
                      Copy task prompt
                    </button>
                    {!terminal(selected) && (
                      <>
                        <button
                          className="btn ghost"
                          disabled={readOnly || busy || !canCoordinate}
                          onClick={() => openDialog("delegate")}
                        >
                          Delegate to agent
                        </button>
                        <button
                          className="btn link"
                          disabled={readOnly || busy || !canCoordinate}
                          onClick={() => openDialog("redirect")}
                        >
                          Redirect work
                        </button>
                      </>
                    )}
                  </div>
                  <details className="record-inspector">
                    <summary>Inspect work and evidence</summary>
                    <div className="inspector-body">
                      <dl>
                        <dt>Scope</dt>
                        <dd>{selected.scope.join(", ")}</dd>
                        <dt>Candidate workspace</dt>
                        <dd>
                          {selected.candidate_path ||
                            "Not attached — ask the agent to use an isolated checkout"}
                        </dd>
                        <dt>Work identifier</dt>
                        <dd>
                          <code>{selected.id}</code>
                        </dd>
                        <dt>Mission revision</dt>
                        <dd>{revision(selected)}</dd>
                      </dl>
                      <div className="actions">
                        {!terminal(selected) && (
                          <>
                            <button
                              className="mini"
                              disabled={readOnly || !canCoordinate || busy}
                              onClick={() => openDialog("assign")}
                            >
                              Assign existing agent
                            </button>
                            <button
                              className="mini"
                              disabled={readOnly || !canWork(selected) || busy}
                              onClick={() => openDialog("report")}
                            >
                              Report progress
                            </button>
                            <button
                              className="mini"
                              disabled={readOnly || !canWork(selected) || busy}
                              onClick={() => openDialog("decision")}
                            >
                              Request a decision
                            </button>
                            <button
                              className="mini"
                              disabled={readOnly || !canWork(selected) || busy}
                              onClick={() => openDialog("artifact")}
                            >
                              Attach a result
                            </button>
                            <button
                              className="mini"
                              disabled={
                                readOnly ||
                                !canWork(selected) ||
                                !currentArtifact ||
                                busy
                              }
                              onClick={() => openDialog("evidence")}
                            >
                              Record test evidence
                            </button>
                            <button
                              className="mini"
                              disabled={readOnly || !canWork(selected) || busy}
                              onClick={() =>
                                void command("task.transition", {
                                  task_id: selected.id,
                                  status: "in_review",
                                })
                              }
                            >
                              Submit for review
                            </button>
                          </>
                        )}
                        <a
                          className="mini"
                          href={`?advanced=1#task=${encodeURIComponent(selected.id)}`}
                        >
                          Open full record console
                        </a>
                      </div>
                      {selected.reports?.map((r) => (
                        <article className="report" key={r.id}>
                          <strong>{r.summary}</strong>
                          <p>
                            {name(r.created_by)} · {when(r.created_at)} ·{" "}
                            {r.progress == null
                              ? "Progress not estimated"
                              : `${r.progress}% reported`}
                          </p>
                          {r.blocker && (
                            <p className="blocker">Blocked: {r.blocker}</p>
                          )}
                        </article>
                      ))}
                      {selected.artifacts.map((a) => (
                        <article className="report" key={a.id}>
                          <strong>{a.title}</strong>
                          <p>{a.summary}</p>
                          <code>{a.revision}</code>
                          <p className="fine">SHA-256 {a.digest}</p>
                        </article>
                      ))}
                    </div>
                  </details>
                </>
              )}
            </section>
          </div>
        </div>
        <div className="lower">
          <section className="panel" aria-labelledby="crew-heading">
            <div className="ph">
              <h2 id="crew-heading">Crew</h2>
              <span className="mono">where effort is assigned</span>
            </div>
            <ul className="crew">
              {state.principals
                .filter(
                  (p) =>
                    p.active &&
                    (p.id === actor?.id ||
                      activeTasks.some((t) => t.assignee_id === p.id) ||
                      state.coordinator_grants?.some(
                        (g) =>
                          g.project_id === project?.id &&
                          g.principal_id === p.id &&
                          !g.revoked_at,
                      )),
                )
                .map((p) => {
                  const assigned = activeTasks.filter(
                      (t) => t.assignee_id === p.id,
                    ),
                    coordinator = state.coordinator_grants?.some(
                      (g) =>
                        g.project_id === project?.id &&
                        g.principal_id === p.id &&
                        !g.revoked_at,
                    );
                  return (
                    <li className="mem" key={p.id}>
                      <Avatar person={p} />
                      <div>
                        <div className="nm">{p.name}</div>
                        <div className="rl">
                          {coordinator
                            ? "Coordinator"
                            : p.kind === "human"
                              ? "Direction & review"
                              : "Agent session"}
                        </div>
                      </div>
                      <span className="scope">
                        {assigned.length}{" "}
                        {assigned.length === 1 ? "piece" : "pieces"}
                      </span>
                    </li>
                  );
                })}
            </ul>
            <div className="legend">
              <span>
                <i className="lh" />
                Carbon · person
              </span>
              <span>
                <i className="la" />
                Silicon · agent
              </span>
            </div>
            <p className="fine">
              Assignments show where effort is directed. Runtime and cost
              telemetry unavailable.
            </p>
            {project && canCoordinate && !demoMode && (
              <button className="mini" onClick={() => void showPrompt()}>
                Copy coordinator prompt
              </button>
            )}
          </section>
          <section className="panel" aria-labelledby="live-heading">
            <div className="ph">
              <h2 id="live-heading">Live work</h2>
              <span className="mono">latest agent reports</span>
            </div>
            <ul className="live">
              {activeTasks
                .filter((t) => t.assignee_id)
                .slice(0, 6)
                .map((t) => {
                  const report = latestReport(t),
                    person = state.principals.find(
                      (p) => p.id === t.assignee_id,
                    );
                  return (
                    <li
                      className={`job ${report?.progress == null ? "paused" : ""}`}
                      key={t.id}
                    >
                      <div className="row">
                        <span className="who">
                          <i
                            className={`dot ${person?.kind === "agent" ? "a" : ""}`}
                          />
                          {name(t.assignee_id)}
                        </span>
                        <button
                          className="mini"
                          onClick={() => chooseTask(t.id)}
                        >
                          Inspect
                        </button>
                      </div>
                      <div className="what">{t.title}</div>
                      {report?.progress != null && (
                        <div
                          className={`prog ${person?.kind === "human" ? "h" : ""}`}
                          role="img"
                          aria-label={`${report.progress} percent reported`}
                        >
                          <i style={{ width: `${report.progress}%` }} />
                        </div>
                      )}
                      <div className="src">
                        {report
                          ? `${report.summary} · ${when(report.created_at)}`
                          : "Awaiting the first progress report"}
                      </div>
                    </li>
                  );
                })}
            </ul>
            {!activeTasks.some((t) => t.assignee_id) && (
              <p className="empty-copy">
                Delegate a work slice to see its agent’s updates here.
              </p>
            )}
            {activeTasks.filter((t) => t.assignee_id).length > 6 && (
              <a href="#work-list" className="mini">
                See all assigned work
              </a>
            )}
            <p className="fine">
              Progress is self-reported. No running process is inferred.
            </p>
          </section>
          <section className="panel tracep" aria-labelledby="trace-heading">
            <div className="ph">
              <h2 id="trace-heading">Trace</h2>
              <span className="mono">where work came from</span>
            </div>
            <ol className="trace">
              {state.events
                .filter((e) => tasks.some((t) => t.id === e.task_id))
                .slice(-8)
                .reverse()
                .map((e) => {
                  const t = tasks.find((t) => t.id === e.task_id),
                    person = state.principals.find((p) => p.id === e.actor_id);
                  return (
                    <li
                      className="tr"
                      key={e.id}
                      tabIndex={0}
                      onMouseEnter={() => setHighlighted(e.task_id)}
                      onMouseLeave={() => setHighlighted(null)}
                      onFocus={() => setHighlighted(e.task_id)}
                      onBlur={() => setHighlighted(null)}
                    >
                      <i
                        className={`dot g ${person?.kind === "agent" ? "a" : ""}`}
                      />
                      <button
                        className="source-link w"
                        onClick={() => e.task_id && chooseTask(e.task_id)}
                      >
                        {eventLabels[e.type] || humanize(e.type)}
                      </button>
                      <time>{when(e.created_at)}</time>
                      <span className="from">
                        {person?.name || "Workspace"} · <b>{t?.title}</b>
                      </span>
                      <code>{e.hash.slice(0, 8)}</code>
                    </li>
                  );
                })}
            </ol>
            {!state.events.some((e) =>
              tasks.some((t) => t.id === e.task_id),
            ) && (
              <p className="empty-copy">
                Assignments, updates, decisions and evidence appear here as they
                are recorded.
              </p>
            )}
          </section>
        </div>
        <section
          className="panel work-register"
          id="work-list"
          aria-labelledby="work-heading"
        >
          <div className="ph">
            <h2 id="work-heading">
              All work
              {stageFilter && ` · ${stageNames[stages.indexOf(stageFilter)]}`}
            </h2>
            <div className="actions">
              {stageFilter && (
                <button className="mini" onClick={() => setStageFilter("")}>
                  Show every stage
                </button>
              )}
              <span className="mono">
                {filteredTasks.length} pieces · nothing hidden
              </span>
            </div>
          </div>
          <div className="work-list">
            {filteredTasks.map((t) => (
              <button
                className={`work-row ${selected?.id === t.id ? "selected" : ""}`}
                key={t.id}
                onClick={() => {
                  chooseTask(t.id);
                  document.getElementById("decision-heading")?.scrollIntoView({
                    behavior: paused ? "instant" : "smooth",
                    block: "center",
                  });
                }}
              >
                <span>
                  <strong>{t.title}</strong>
                  <small>
                    {name(t.assignee_id)} ·{" "}
                    {stageNames[stages.indexOf(stageOf(t))]}
                  </small>
                </span>
                <span
                  className={`work-state ${(t.blockers || []).length ? "blocked" : ""}`}
                >
                  {(t.blockers || []).length ? "Blocked" : humanize(t.status)}
                </span>
              </button>
            ))}
          </div>
          {!filteredTasks.length && (
            <p className="empty-copy">
              {stageFilter
                ? "There is no work in this stage yet."
                : "Start with one meaningful outcome. Add a work slice or give a coordinator its brief."}
            </p>
          )}
        </section>
        <footer>
          <span>
            Synbios · local mission control ·{" "}
            {lastSync ? `updated ${lastSync}` : "connecting"}
            <br />
            {demoMode
              ? "Synthetic example · no real agents"
              : "Your work stays in the local workspace"}
          </span>
          <em>Different minds. Shared possibility.</em>
          <div className="footer-links">
            <button
              className="mini"
              aria-pressed={paused}
              onClick={() => setPaused((v) => !v)}
            >
              {paused ? "Resume motion" : "Pause motion"}
            </button>
            <a href="?advanced=1">Record console</a>
            <a href="https://github.com/Moissanite-Labs/exofab/pull/17">
              Crystal Lattice design
            </a>
          </div>
        </footer>
      </main>
      {dialog && (
        <Dialog
          title={
            {
              mission: "Create mission",
              "mission-edit": "Edit mission",
              slice: "New work slice",
              redirect: "Redirect work",
              delegate: "Delegate to agent",
              coordinator: "Plan with a coordinator",
              assign: "Assign existing agent",
              report: "Report progress",
              decision: "Request a decision",
              artifact: "Attach a result",
              evidence: "Record test evidence",
              brief: briefTitle,
            }[dialog] || dialog
          }
          close={closeDialog}
        >
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {dialog === "brief" ? (
            <>
              <p>
                {secretBrief
                  ? "This brief includes the agent’s new connection key. Copy it into the chosen session before closing; Synbios will not show the key again."
                  : "Give this brief to the agent handling the work. It uses that agent’s own connection key."}
              </p>
              <textarea
                id="agent-brief"
                aria-label="Agent task brief"
                value={brief}
                readOnly
                spellCheck={false}
                rows={18}
              />
              <div className="actions">
                <button
                  className="btn primary"
                  onClick={() => void copyBrief()}
                >
                  {briefTitle === "Coordinator brief"
                    ? "Copy coordinator prompt"
                    : "Copy task prompt"}
                </button>
                <button className="btn ghost" onClick={closeDialog}>
                  Done
                </button>
              </div>
              {notice && <p role="status">{notice}</p>}
            </>
          ) : (
            <form onSubmit={(e) => void submitForm(e)}>
              {(dialog === "mission" || dialog === "mission-edit") && (
                <>
                  <p>Give all your agents one clear destination.</p>
                  <Field label="Mission name">
                    <input
                      name="name"
                      required
                      autoFocus
                      defaultValue={
                        dialog === "mission-edit" ? formProject?.name : ""
                      }
                      placeholder="Exo desktop"
                    />
                  </Field>
                  <Field label="Desired outcome">
                    <textarea
                      name="description"
                      required
                      rows={3}
                      defaultValue={
                        dialog === "mission-edit"
                          ? formProject?.description
                          : ""
                      }
                      placeholder="What should be possible when this mission is complete?"
                    />
                  </Field>
                  {dialog === "mission" && (
                    <Field
                      label="Local project folder"
                      hint="Optional. The coordinator includes this location in agent briefs."
                    >
                      <input name="workspace" placeholder="/path/to/exo" />
                    </Field>
                  )}
                </>
              )}
              {(dialog === "slice" || dialog === "redirect") && (
                <>
                  <p>
                    {dialog === "redirect"
                      ? "Update the shared direction. Connected agents see it on their next read; paste a refreshed brief into sessions that are not polling."
                      : "A slice is one outcome an agent can own. Connect dependencies when work must happen in sequence."}
                  </p>
                  <WorkFields
                    task={dialog === "redirect" ? formTask : undefined}
                    tasks={tasks}
                  />
                  <Field label="Stage">
                    <select
                      name="stage"
                      defaultValue={
                        dialog === "redirect" ? stageOf(formTask!) : "build"
                      }
                    >
                      {stages.map((s, i) => (
                        <option key={s} value={s}>
                          {stageNames[i]}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <details>
                    <summary>Scope and connections</summary>
                    <Field
                      label="Work scope"
                      hint="One area or relative path per line. This describes the assignment; agent tools must still respect it."
                    >
                      <textarea
                        name="scope"
                        defaultValue={
                          dialog === "redirect"
                            ? formTask?.scope.join("\n")
                            : "."
                        }
                        required
                        rows={2}
                      />
                    </Field>
                    <Field label="Priority">
                      <select
                        name="priority"
                        defaultValue={
                          dialog === "redirect" ? formTask?.priority : "normal"
                        }
                      >
                        <option value="low">Low</option>
                        <option value="normal">Normal</option>
                        <option value="high">High</option>
                      </select>
                    </Field>
                    <Field
                      label="Depends on"
                      hint="Choose work that must be accepted before this slice can be submitted."
                    >
                      <select
                        name="dependencies"
                        multiple
                        defaultValue={
                          dialog === "redirect" ? formTask?.dependencies : []
                        }
                      >
                        {tasks
                          .filter(
                            (t) => t.id !== formTask?.id || dialog === "slice",
                          )
                          .map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.title}
                            </option>
                          ))}
                      </select>
                    </Field>
                    {dialog === "redirect" && (
                      <Field
                        label="Candidate workspace"
                        hint="An existing isolated checkout. This field records the location; it does not create or move files."
                      >
                        <input
                          name="candidate_path"
                          defaultValue={formTask?.candidate_path || ""}
                        />
                      </Field>
                    )}
                  </details>
                </>
              )}
              {(dialog === "delegate" || dialog === "coordinator") && (
                <>
                  <p>
                    {dialog === "coordinator"
                      ? "Create a coordinator identity, then paste its brief into Codex, Claude Code or another local agent. It can divide this mission into work slices through the API."
                      : "Create a task-scoped identity and a complete brief for any local agent session. A prior owner’s task grants will be revoked."}
                  </p>
                  <Field label="Agent name">
                    <input
                      name="name"
                      required
                      autoFocus
                      placeholder={
                        dialog === "coordinator"
                          ? "Exo coordinator"
                          : "Codex · desktop work"
                      }
                    />
                  </Field>
                  <p className="fine">
                    Creating a brief does not launch a process. The agent
                    connects when you give it the brief. The one-time key will
                    be shown only here.
                  </p>
                </>
              )}
              {dialog === "assign" && (
                <>
                  <p>
                    Move ownership to an existing identity. The previous owner’s
                    task grants are revoked; already running external tools are
                    not interrupted.
                  </p>
                  <Field label="Agent or person">
                    <select
                      name="principal_id"
                      required
                      defaultValue={formTask?.assignee_id || ""}
                    >
                      <option value="" disabled>
                        Choose an owner
                      </option>
                      {state.principals
                        .filter((p) => p.active)
                        .map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} · {p.kind}
                          </option>
                        ))}
                    </select>
                  </Field>
                </>
              )}
              {dialog === "report" && (
                <>
                  <Field label="Progress update">
                    <textarea name="summary" required rows={3} />
                  </Field>
                  <Field
                    label="Progress percent"
                    hint="Optional estimate, shown as self-reported."
                  >
                    <input name="progress" type="number" min="0" max="100" />
                  </Field>
                  <Field
                    label="Blocker"
                    hint="Leave empty to clear a previous reported blocker."
                  >
                    <textarea name="blocker" rows={2} />
                  </Field>
                </>
              )}
              {dialog === "decision" && (
                <>
                  <Field label="Decision title">
                    <input name="title" required />
                  </Field>
                  <Field label="Why this needs a decision">
                    <textarea name="question" required rows={3} />
                  </Field>
                  <Field
                    label="Options"
                    hint="One choice per line, at least two."
                  >
                    <textarea name="options" required rows={3} />
                  </Field>
                </>
              )}
              {dialog === "artifact" && (
                <>
                  <p>
                    Attach a result from the agent’s isolated work. Synbios
                    records its identity; it does not apply files.
                  </p>
                  <Field label="Result title">
                    <input name="title" required />
                  </Field>
                  <Field label="Result kind">
                    <select name="kind">
                      <option value="git_commit">Git commit</option>
                      <option value="document">Document</option>
                    </select>
                  </Field>
                  <Field label="Revision">
                    <input name="revision" required />
                  </Field>
                  <Field label="SHA-256 digest">
                    <input name="digest" required pattern="[a-f0-9]{64}" />
                  </Field>
                  <Field label="Location">
                    <input name="uri" />
                  </Field>
                  <Field label="Summary">
                    <textarea name="summary" rows={3} />
                  </Field>
                </>
              )}
              {dialog === "evidence" && (
                <>
                  <p>
                    This report is bound to the selected result’s exact revision
                    and digest.
                  </p>
                  <Field label="Test outcome">
                    <select name="status">
                      <option value="passed">Passed</option>
                      <option value="failed">Failed</option>
                      <option value="unavailable">Unavailable</option>
                    </select>
                  </Field>
                  <Field label="What was checked">
                    <textarea name="summary" required rows={3} />
                  </Field>
                  <Field label="Command run">
                    <input name="command" />
                  </Field>
                  <Field label="Tool">
                    <input name="tool" required />
                  </Field>
                  <Field label="Tool version">
                    <input name="tool_version" required />
                  </Field>
                </>
              )}
              <div className="actions form-actions">
                <button type="submit" className="btn primary" disabled={busy}>
                  {busy
                    ? "Saving…"
                    : {
                        mission: "Create mission",
                        "mission-edit": "Save mission",
                        slice: "Create work slice",
                        redirect: "Save direction",
                        delegate: "Create agent brief",
                        coordinator: "Create coordinator brief",
                        assign: "Assign owner",
                        report: "Save progress report",
                        decision: "Create decision",
                        artifact: "Attach result",
                        evidence: "Save evidence",
                      }[dialog] || "Save"}
                </button>
                <button
                  className="btn ghost"
                  type="button"
                  onClick={closeDialog}
                  disabled={busy}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </Dialog>
      )}
    </>
  );
}

function WorkFields({ task }: { task?: Task; tasks: Task[] }) {
  return (
    <>
      <Field label="Title">
        <input
          name="title"
          defaultValue={task?.title || ""}
          required
          autoFocus
          placeholder="Make the desktop reconnect reliably"
        />
      </Field>
      <Field label="Outcome">
        <textarea
          name="description"
          defaultValue={task?.description || ""}
          rows={3}
          required
          placeholder="What should the agent deliver?"
        />
      </Field>
      <Field label="Acceptance criteria" hint="One observable check per line.">
        <textarea
          name="criteria"
          defaultValue={task?.criteria.join("\n") || ""}
          required
          rows={3}
          placeholder="Reconnecting restores the current session without losing messages"
        />
      </Field>
    </>
  );
}
