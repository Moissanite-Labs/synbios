import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUpRight,
  ArrowRight,
  Plus,
  Search,
  LayoutGrid,
  FolderKanban,
  Activity,
  ShieldCheck,
  LogOut,
  RefreshCw,
  X,
  Check,
  Copy,
  Download,
  KeyRound,
  GitBranch,
  FileCheck2,
  ChevronRight,
  Hexagon,
  Circle,
  AlertTriangle,
  Menu,
  Fingerprint,
} from "lucide-react";
import "@fontsource/dm-sans/latin-400.css";
import "@fontsource/dm-sans/latin-500.css";
import "@fontsource/dm-sans/latin-600.css";
import "@fontsource/dm-sans/latin-700.css";
import "@fontsource/space-grotesk/latin-400.css";
import "@fontsource/space-grotesk/latin-500.css";
import "@fontsource/space-grotesk/latin-600.css";
import "./style.css";
type CommandPayload = Record<string, unknown>;
type Principal = {
  id: string;
  name: string;
  kind: "human" | "agent";
  active: boolean;
  created_at: string;
};
type Project = {
  id: string;
  name: string;
  description: string;
  repository: string;
  created_at: string;
};
type Artifact = {
  id: string;
  title: string;
  kind: string;
  revision: string;
  digest: string;
  uri: string;
  summary: string;
  created_by: string;
  created_at: string;
};
type Evidence = {
  id: string;
  artifact_id: string;
  artifact_digest: string;
  revision: string;
  kind: string;
  status: string;
  command: string;
  summary: string;
  tool: string;
  tool_version: string;
  assumptions: string[];
  created_at: string;
};
type Review = {
  id: string;
  artifact_id: string;
  revision: string;
  decision: string;
  comment: string;
  created_by: string;
  created_at: string;
};
type Task = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  criteria: string[];
  scope: string[];
  status: string;
  priority: string;
  assignee_id: string | null;
  dependencies: string[];
  artifacts: Artifact[];
  evidence: Evidence[];
  reviews: Review[];
};
type Grant = {
  id: string;
  principal_id: string;
  task_id: string;
  capabilities: string[];
  revoked_at: string | null;
};
type ProvenanceEvent = {
  id: string;
  seq: number;
  type: string;
  actor_id: string;
  task_id: string | null;
  hash: string;
  created_at: string;
};
type Snapshot = {
  actor: Principal;
  projects: Project[];
  tasks: Task[];
  principals: Principal[];
  grants: Grant[];
  events: ProvenanceEvent[];
  integrity: { valid: boolean; event_count: number };
  metrics: Record<string, number>;
};
const statuses = [
  "open",
  "claimed",
  "in_progress",
  "in_review",
  "changes_requested",
  "accepted",
  "cancelled",
];
const label = (s: string) => s.replaceAll("_", " ");
const lines = (v: FormDataEntryValue | null) =>
  String(v || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
const date = (v: string) =>
  new Date(v).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
function App() {
  const generation = useRef(0);
  const [token, setToken] = useState(
    sessionStorage.getItem("synbios.token") || "",
  );
  const [state, setState] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState("board");
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState("");
  const [modal, setModal] = useState("");
  const [secret, setSecret] = useState("");
  const [notice, setNotice] = useState("");
  const [mobile, setMobile] = useState(false);
  async function api(path: string, method = "GET", body?: unknown) {
    const requestGeneration = generation.current;
    const r = await fetch("/api/" + path, {
      method,
      headers: {
        Authorization: "Bearer " + token,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) {
      if (r.status === 401 && requestGeneration === generation.current)
        logout();
      throw new Error(data.error || `Request failed (${r.status})`);
    }
    return data;
  }
  function logout() {
    generation.current++;
    sessionStorage.removeItem("synbios.token");
    setToken("");
    setState(null);
    setSelected("");
    setModal("");
    setSecret("");
    setError("");
    setNotice("");
    setMobile(false);
    setBusy(false);
  }
  async function refresh() {
    const requestGeneration = generation.current;
    setError("");
    try {
      const snapshot = await api("state");
      if (requestGeneration === generation.current) setState(snapshot);
    } catch (e) {
      if (requestGeneration === generation.current)
        setError((e as Error).message);
    }
  }
  useEffect(() => {
    if (token) {
      sessionStorage.setItem("synbios.token", token);
      void refresh();
    }
  }, [token]);
  async function command(action: string, payload: CommandPayload) {
    const requestGeneration = generation.current;
    setBusy(true);
    setError("");
    try {
      const result = await api("commands/" + action, "POST", payload);
      if (requestGeneration !== generation.current) return null;
      await refresh();
      if (requestGeneration !== generation.current) return null;
      setModal("");
      setNotice("Saved to the local record.");
      if (result.token) setSecret(result.token);
      return result;
    } catch (e) {
      if (requestGeneration === generation.current)
        setError((e as Error).message);
      return null;
    } finally {
      if (requestGeneration === generation.current) setBusy(false);
    }
  }
  async function download() {
    try {
      const data = await api("tasks/" + selected + "/export");
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `synbios-${selected}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    if (!selected && !modal && !secret) return;
    const previous = document.activeElement as HTMLElement;
    const dialog = [
      ...document.querySelectorAll<HTMLElement>("[role=dialog]"),
    ].at(-1);
    const focusable = () =>
      dialog
        ? [
            ...dialog.querySelectorAll<HTMLElement>(
              'button:not(:disabled),input,textarea,select,[tabindex="0"]',
            ),
          ]
        : [];
    focusable()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (secret) return;
        if (modal) setModal("");
        else setSelected("");
      }
      if (e.key === "Tab") {
        const list = focusable();
        if (!list.length) return;
        if (e.shiftKey && document.activeElement === list[0]) {
          e.preventDefault();
          list.at(-1)?.focus();
        } else if (!e.shiftKey && document.activeElement === list.at(-1)) {
          e.preventDefault();
          list[0].focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [selected, modal, secret]);
  const human = state?.actor.kind === "human";
  const task = state?.tasks.find((t) => t.id === selected);
  const current = task?.artifacts.at(-1);
  const mutable = task && !["accepted", "cancelled"].includes(task.status);
  const evidence =
    task?.evidence.filter(
      (e) =>
        e.artifact_id === current?.id &&
        e.artifact_digest === current?.digest &&
        e.revision === current?.revision,
    ) || [];
  const dependenciesReady = task?.dependencies.every(
    (id: string) =>
      state?.tasks.find((t) => t.id === id)?.status === "accepted",
  );
  const passing =
    evidence.some((e) => e.kind === "test" && e.status === "passed") &&
    !evidence.some((e) => e.kind === "test" && e.status === "failed");
  const can = (cap: string) =>
    human ||
    state?.grants.some(
      (g) =>
        g.principal_id === state.actor.id &&
        g.task_id === selected &&
        !g.revoked_at &&
        g.capabilities.includes(cap),
    );
  const filtered =
    state?.tasks.filter(
      (t) =>
        (!project || t.project_id === project) &&
        (!filter || t.status === filter) &&
        (t.title + " " + t.description)
          .toLowerCase()
          .includes(search.toLowerCase()),
    ) || [];
  function field(
    name: string,
    title: string,
    required = true,
    placeholder = "",
    multi = false,
  ) {
    return (
      <label>
        {title}
        {multi ? (
          <textarea
            name={name}
            required={required}
            placeholder={placeholder}
            rows={3}
          />
        ) : (
          <input name={name} required={required} placeholder={placeholder} />
        )}
      </label>
    );
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (["evidence.add", "review.create"].includes(modal) && !current) {
      setError("Current candidate unavailable. Refresh the task.");
      return;
    }
    const d = new FormData(e.currentTarget);
    const obj = Object.fromEntries(d) as CommandPayload;
    let action = modal;
    if (modal === "task.create") {
      obj.criteria = lines(d.get("criteria"));
      obj.scope = lines(d.get("scope"));
      obj.dependencies = d.getAll("dependencies");
    }
    if (modal === "artifact.add") obj.task_id = selected;
    if (modal === "evidence.add") {
      Object.assign(obj, {
        task_id: selected,
        artifact_id: current!.id,
        artifact_digest: current!.digest,
        revision: current!.revision,
        assumptions: lines(d.get("assumptions")),
      });
    }
    if (modal === "review.create")
      Object.assign(obj, {
        task_id: selected,
        artifact_id: current!.id,
        revision: current!.revision,
      });
    if (modal === "grant.create") {
      obj.capabilities = d.getAll("capabilities");
    }
    if (modal === "verify") {
      setBusy(true);
      try {
        const result = await api(
          "bundles/verify",
          "POST",
          JSON.parse(String(d.get("bundle"))),
        );
        setNotice(
          result.valid
            ? "Bundle verification passed."
            : "Bundle verification failed: " + (result.errors || []).join("; "),
        );
        setModal("");
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
      return;
    }
    await command(action, obj);
  }
  if (!state)
    return (
      <main className="login">
        <div className="login-art">
          <Logo />
          <div className="orbit">
            <Hexagon size={150} strokeWidth={0.5} />
            <span className="orbit-point" />
          </div>
          <div>
            <p className="eyebrow">HUMAN JUDGMENT. AGENT CAPABILITY.</p>
            <h1>
              Build together.
              <br />
              Keep the evidence.
            </h1>
            <p>
              A shared forge for work that can be inspected,
              <br />
              reviewed, and carried forward.
            </p>
          </div>
          <small>LOCAL-FIRST / REFERENCE IMPLEMENTATION</small>
        </div>
        <section className="login-form">
          <p className="eyebrow">ENTER YOUR WORKSPACE</p>
          <h2>Welcome to the forge.</h2>
          <p>Connect with a credential issued by your local operator.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setToken(String(new FormData(e.currentTarget).get("token")));
            }}
          >
            <label>
              Local access token
              <input
                name="token"
                type="password"
                required
                autoComplete="off"
                placeholder="Paste your credential"
              />
            </label>
            <button className="primary" disabled={busy}>
              Open workspace <ArrowRight size={17} />
            </button>
          </form>
          {error && (
            <div role="alert" className="error">
              {error}
              <button className="text" onClick={() => void refresh()}>
                Retry
              </button>
            </div>
          )}
          <div className="trust">
            <ShieldCheck size={20} />
            <p>
              Your token stays in this tab’s session storage. The local operator
              controls identity and access. This is not a remote identity
              service.
            </p>
          </div>
        </section>
      </main>
    );
  return (
    <div className="app">
      <aside className={mobile ? "sidebar show" : "sidebar"}>
        <Logo />
        <p className="nav-label">WORKSPACE</p>
        {[
          ["board", "The forge", LayoutGrid],
          ["projects", "Projects", FolderKanban],
          ["activity", "Provenance", Activity],
          ["access", "Access & trust", ShieldCheck],
        ].map(([id, title, Icon]) => (
          <button
            key={String(id)}
            className={"nav " + (view === id ? "active" : "")}
            onClick={() => {
              setView(String(id));
              setSelected("");
              setMobile(false);
            }}
          >
            {React.createElement(Icon as any, { size: 19 })}
            {String(title)}
            {id === "board" && <span>{state.tasks.length}</span>}
          </button>
        ))}
        <div className="sidebar-bottom">
          <div className="local-indicator">
            <i /> LOCAL WORKSPACE
          </div>
          <p>
            Deliberate work.
            <br />A durable record.
          </p>
          <div className="identity">
            <div className="avatar">{state.actor.name.slice(0, 1)}</div>
            <div>
              <strong>{state.actor.name}</strong>
              <small>{state.actor.kind} principal</small>
            </div>
            <button aria-label="Sign out" title="Sign out" onClick={logout}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button
            className="mobile-menu"
            aria-label="Toggle navigation"
            onClick={() => setMobile(!mobile)}
          >
            <Menu size={21} />
          </button>
          <span>
            Workspace <ChevronRight size={13} />{" "}
            {view === "board" ? "The forge" : label(view)}
          </span>
          <div className="top-actions">
            <span className="integrity">
              <i className={state.integrity.valid ? "good" : "bad"} />
              {state.integrity.valid ? "Record intact" : "Integrity alert"}
            </span>
            <button
              aria-label="Refresh workspace"
              onClick={() => void refresh()}
            >
              <RefreshCw size={17} />
            </button>
          </div>
        </header>
        <main className="content">
          {error && (
            <div className="error" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              {notice}
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <p className="eyebrow">
                SYNBIOS /{" "}
                {view === "board"
                  ? "COLLABORATIVE WORK"
                  : label(view).toUpperCase()}
              </p>
              <h1>
                {view === "board"
                  ? "The forge."
                  : view === "projects"
                    ? "Project ground."
                    : view === "activity"
                      ? "Every step, recorded."
                      : "Access is explicit."}
              </h1>
              <p>
                {view === "board"
                  ? "Turn intent into artifacts. Let evidence carry the work."
                  : view === "projects"
                    ? "A clear boundary for every body of work."
                    : view === "activity"
                      ? "A local, hash-chained history of workspace decisions."
                      : "Named principals, scoped capabilities, human accountability."}
              </p>
            </div>
            {human && ["board", "projects"].includes(view) && (
              <button
                className="primary"
                onClick={() =>
                  setModal(
                    view === "projects" ? "project.create" : "task.create",
                  )
                }
              >
                <Plus size={17} />
                {view === "projects" ? "New project" : "Create task"}
              </button>
            )}
          </div>
          {view === "board" && (
            <>
              <section className="stats">
                {[
                  [
                    "In the forge",
                    state.tasks.filter(
                      (t) => !["accepted", "cancelled"].includes(t.status),
                    ).length,
                    "Active tasks",
                  ],
                  [
                    "Awaiting judgment",
                    state.tasks.filter((t) => t.status === "in_review").length,
                    "Ready for human review",
                  ],
                  [
                    "Accepted work",
                    state.tasks.filter((t) => t.status === "accepted").length,
                    "Evidence-backed decisions",
                  ],
                  [
                    "Connected projects",
                    state.projects.length,
                    "Defined boundaries",
                  ],
                ].map(([title, value, sub], i) => (
                  <div className="stat" key={String(title)}>
                    <span>{title}</span>
                    <strong>
                      {String(value).padStart(2, "0")}
                      <span className="stat-symbol">
                        {i === 1 ? (
                          <ArrowUpRight size={23} />
                        ) : i === 2 ? (
                          <Check size={23} />
                        ) : (
                          <Hexagon size={23} />
                        )}
                      </span>
                    </strong>
                    <small>{sub}</small>
                  </div>
                ))}
              </section>
              <div className="section-heading">
                <h2>
                  Work in motion <span>{filtered.length}</span>
                </h2>
                <span className="eyebrow">INTENT → EVIDENCE → REVIEW</span>
              </div>
              <div className="filters">
                <div className="search">
                  <Search size={17} />
                  <input
                    aria-label="Search tasks"
                    placeholder="Find work by title or intent…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <select
                  aria-label="Filter by project"
                  value={project}
                  onChange={(e) => setProject(e.target.value)}
                >
                  <option value="">All projects</option>
                  {state.projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Filter by status"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="">All states</option>
                  {statuses.map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="board">
                {[
                  ["Ready to begin", ["open"]],
                  [
                    "In motion",
                    ["claimed", "in_progress", "changes_requested"],
                  ],
                  ["Human review", ["in_review"]],
                  ["Accepted", ["accepted", "cancelled"]],
                ].map(([title, ss]) => (
                  <section className="column" key={String(title)}>
                    <h3>
                      <Circle size={10} />
                      {title}
                      <span>
                        {
                          filtered.filter((t) =>
                            (ss as string[]).includes(t.status),
                          ).length
                        }
                      </span>
                    </h3>
                    {filtered
                      .filter((t) => (ss as string[]).includes(t.status))
                      .map((t) => (
                        <button
                          className="task-card"
                          key={t.id}
                          onClick={() => setSelected(t.id)}
                        >
                          <div className="card-top">
                            <span className="project-tag">
                              {state.projects.find((p) => p.id === t.project_id)
                                ?.name || "Project"}
                            </span>
                            <span className={"priority " + t.priority}>
                              {t.priority}
                            </span>
                          </div>
                          <h4>{t.title}</h4>
                          <p>{t.description}</p>
                          <div className="card-state">
                            <Badge status={t.status} />
                            {t.evidence.some((e) => e.kind === "proof") && (
                              <span className="shadow">Proof · shadow</span>
                            )}
                          </div>
                          <footer>
                            <span>
                              <FileCheck2 size={14} />
                              {t.artifacts.length} artifacts ·{" "}
                              {t.evidence.length} evidence
                            </span>
                            <ArrowUpRight size={16} />
                          </footer>
                        </button>
                      ))}
                    {!filtered.some((t) =>
                      (ss as string[]).includes(t.status),
                    ) && (
                      <div className="empty-column">
                        <Plus size={18} />
                        <span>No work here yet</span>
                      </div>
                    )}
                  </section>
                ))}
              </div>
              <div className="bottom-note">
                <Fingerprint size={16} /> Built for accountable collaboration.
                Acceptance records a human decision; it does not merge code or
                execute work.
              </div>
            </>
          )}
          {view === "projects" && (
            <div className="project-grid">
              {state.projects.map((p) => (
                <button
                  className="project-card"
                  key={p.id}
                  onClick={() => {
                    setProject(p.id);
                    setView("board");
                  }}
                >
                  <FolderKanban size={26} />
                  <h2>{p.name}</h2>
                  <p>{p.description || "No description supplied."}</p>
                  <code>{p.repository || "No repository linked"}</code>
                  <footer>
                    {state.tasks.filter((t) => t.project_id === p.id).length}{" "}
                    tasks
                    <ArrowUpRight size={19} />
                  </footer>
                </button>
              ))}
              {!state.projects.length && (
                <Empty
                  title="Start with a shared boundary."
                  text="Create a project to organize the work, scope, and evidence."
                />
              )}
            </div>
          )}
          {view === "activity" && (
            <>
              <div className="record-banner">
                <ShieldCheck size={26} />
                <div>
                  <strong>
                    {state.integrity.valid
                      ? "Local event chain verifies."
                      : "Local event chain failed verification."}
                  </strong>
                  <p>
                    {state.integrity.event_count} events · Tamper detection
                    within this store. Not signatures, external authenticity, or
                    protection from whole-store replacement.
                  </p>
                </div>
                <button onClick={() => setModal("verify")}>
                  Verify a bundle
                </button>
              </div>
              <div className="timeline">
                {[...state.events].reverse().map((e) => (
                  <div className="event" key={e.id}>
                    <span className="event-dot" />
                    <div>
                      <strong>{label(e.type.replaceAll(".", " · "))}</strong>
                      <p>
                        {state.principals.find((p) => p.id === e.actor_id)
                          ?.name || e.actor_id}{" "}
                        {e.task_id && (
                          <>
                            →{" "}
                            <button
                              className="text"
                              onClick={() => setSelected(e.task_id || "")}
                            >
                              {state.tasks.find((t) => t.id === e.task_id)
                                ?.title || e.task_id}
                            </button>
                          </>
                        )}
                      </p>
                      <code title={e.hash}>
                        #{e.seq} / {e.hash.slice(0, 24)}…
                      </code>
                    </div>
                    <time>{date(e.created_at)}</time>
                  </div>
                ))}
              </div>
            </>
          )}
          {view === "access" && (
            <>
              <div className="record-banner">
                <KeyRound size={26} />
                <div>
                  <strong>Local trust, clearly bounded.</strong>
                  <p>
                    Human principals administer this workspace. Agents need
                    explicit task grants. Tokens identify a principal; proof
                    evidence remains unverified shadow evidence.
                  </p>
                </div>
              </div>
              <div className="section-heading">
                <h2>
                  Principals <span>{state.principals.length}</span>
                </h2>
                {human && (
                  <button onClick={() => setModal("principal.create")}>
                    <Plus size={16} />
                    Add principal
                  </button>
                )}
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Principal</th>
                      <th>Kind</th>
                      <th>State</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.principals.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.name}</strong>
                          <small>{p.id}</small>
                        </td>
                        <td>{p.kind}</td>
                        <td>
                          <Badge status={p.active ? "active" : "inactive"} />
                        </td>
                        <td>
                          {date(p.created_at)}
                          {human && p.active && p.id !== state.actor.id && (
                            <button
                              className="revoke-principal"
                              disabled={busy}
                              onClick={() =>
                                void command("principal.revoke", {
                                  principal_id: p.id,
                                })
                              }
                            >
                              Deactivate credential
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="section-heading">
                <h2>
                  Task grants{" "}
                  <span>
                    {state.grants.filter((g) => !g.revoked_at).length} active
                  </span>
                </h2>
                {human && (
                  <button onClick={() => setModal("grant.create")}>
                    <Plus size={16} />
                    Grant access
                  </button>
                )}
              </div>
              <div className="grant-list">
                {state.grants.map((g) => (
                  <div className="grant" key={g.id}>
                    <div>
                      <strong>
                        {
                          state.principals.find((p) => p.id === g.principal_id)
                            ?.name
                        }
                      </strong>
                      <p>
                        {state.tasks.find((t) => t.id === g.task_id)?.title ||
                          g.task_id}
                      </p>
                      <div className="caps">
                        {g.capabilities.map((c: string) => (
                          <span key={c}>{c}</span>
                        ))}
                      </div>
                    </div>
                    {g.revoked_at ? (
                      <Badge status="revoked" />
                    ) : (
                      human && (
                        <button
                          onClick={() =>
                            void command("grant.revoke", { grant_id: g.id })
                          }
                          disabled={busy}
                        >
                          Revoke grant
                        </button>
                      )
                    )}
                  </div>
                ))}
                {!state.grants.length && (
                  <Empty
                    title="No delegated access."
                    text="Grant only the capabilities an agent needs for a specific task."
                  />
                )}
              </div>
            </>
          )}
        </main>
      </div>
      {task && (
        <div className="drawer-backdrop" onClick={() => setSelected("")}>
          <section
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="task-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <span className="eyebrow">TASK RECORD</span>
              <button aria-label="Close task" onClick={() => setSelected("")}>
                <X />
              </button>
            </header>
            <div className="drawer-body">
              <Badge status={task.status} />
              <h2 id="task-title">{task.title}</h2>
              <p>{task.description}</p>
              <div className="action-row">
                {task.status === "open" && (
                  <button
                    disabled={!can("claim") || busy}
                    onClick={() =>
                      void command("task.claim", { task_id: selected })
                    }
                  >
                    Claim task
                  </button>
                )}
                {["claimed", "changes_requested"].includes(task.status) && (
                  <button
                    disabled={!can("work") || busy}
                    onClick={() =>
                      void command("task.transition", {
                        task_id: selected,
                        status: "in_progress",
                      })
                    }
                  >
                    Start work
                  </button>
                )}
                {mutable &&
                  ["in_progress", "changes_requested"].includes(
                    task.status,
                  ) && (
                    <button
                      className="primary"
                      disabled={
                        !can("submit") ||
                        !current ||
                        !passing ||
                        !dependenciesReady ||
                        busy
                      }
                      onClick={() =>
                        void command("task.transition", {
                          task_id: selected,
                          status: "in_review",
                        })
                      }
                    >
                      Submit for review
                    </button>
                  )}
                <button onClick={() => void download()}>
                  <Download size={15} />
                  Export
                </button>
                {human && mutable && (
                  <button
                    onClick={() =>
                      void command("task.transition", {
                        task_id: selected,
                        status: "cancelled",
                      })
                    }
                  >
                    Cancel task
                  </button>
                )}
                {human && task.status === "cancelled" && (
                  <button
                    onClick={() =>
                      void command("task.transition", {
                        task_id: selected,
                        status: "open",
                      })
                    }
                  >
                    Reopen
                  </button>
                )}
              </div>
              {mutable && (
                <p className="gate">
                  Submission requires a current artifact, passing current tests,
                  no failed current tests, accepted dependencies, and submit
                  permission.
                </p>
              )}
              <section className="detail-section">
                <h3>Acceptance criteria</h3>
                {task.criteria.map((c: string, i: number) => (
                  <p className="criterion" key={i}>
                    <span>{i + 1}.</span>
                    {c}
                  </p>
                ))}
                <h3>Scope boundary</h3>
                <div className="caps">
                  {task.scope.map((s: string) => (
                    <code key={s}>{s}</code>
                  ))}
                </div>
                <h3>Dependencies</h3>
                {task.dependencies.length ? (
                  task.dependencies.map((id: string) => (
                    <button
                      className="dependency"
                      key={id}
                      onClick={() => setSelected(id)}
                    >
                      {state.tasks.find((t) => t.id === id)?.title || id}
                      <Badge
                        status={
                          state.tasks.find((t) => t.id === id)?.status ||
                          "unknown"
                        }
                      />
                    </button>
                  ))
                ) : (
                  <p className="muted">No dependencies.</p>
                )}
              </section>
              <section className="detail-section">
                <div className="section-heading">
                  <h3>Artifact candidates</h3>
                  {mutable && can("artifact") && (
                    <button onClick={() => setModal("artifact.add")}>
                      <Plus size={14} />
                      Add artifact
                    </button>
                  )}
                </div>
                {[...task.artifacts].reverse().map((a) => (
                  <div className="artifact" key={a.id}>
                    <strong>{a.title}</strong>
                    <span className="freshness">
                      {a.id === current?.id
                        ? "CURRENT CANDIDATE"
                        : "SUPERSEDED"}
                    </span>
                    <p>{a.summary}</p>
                    <dl>
                      <dt>Revision</dt>
                      <dd>{a.revision}</dd>
                      <dt>SHA-256</dt>
                      <dd>{a.digest}</dd>
                      <dt>Reference</dt>
                      <dd>{a.uri || "None"}</dd>
                    </dl>
                    <small>{date(a.created_at)}</small>
                  </div>
                ))}
                {!current && (
                  <p className="muted">
                    Add an artifact revision and content digest to begin the
                    evidence trail.
                  </p>
                )}
              </section>
              <section className="detail-section">
                <div className="section-heading">
                  <h3>Evidence ledger</h3>
                  {mutable && current && can("evidence") && (
                    <button onClick={() => setModal("evidence.add")}>
                      <Plus size={14} />
                      Add evidence
                    </button>
                  )}
                </div>
                {[...task.evidence].reverse().map((e) => {
                  const fresh = evidence.some((x) => x.id === e.id);
                  return (
                    <div
                      className={"evidence " + (!fresh ? "stale" : "")}
                      key={e.id}
                    >
                      <div>
                        <Badge status={e.status} />
                        <strong>
                          {e.kind === "proof"
                            ? "Proof · shadow evidence"
                            : label(e.kind)}
                        </strong>
                        <span className="freshness">
                          {fresh
                            ? "Current candidate"
                            : "Stale · older candidate"}
                        </span>
                      </div>
                      <p>{e.summary}</p>
                      <code>{e.command || "No command recorded"}</code>
                      <small>
                        {e.tool} {e.tool_version} · {date(e.created_at)}
                      </small>
                      {e.kind === "proof" && (
                        <p className="gate">
                          Supplied proof output. Not independently verified by
                          Synbios.
                        </p>
                      )}
                      {e.assumptions.length > 0 && (
                        <p>Assumptions: {e.assumptions.join("; ")}</p>
                      )}
                    </div>
                  );
                })}
                {!task.evidence.length && (
                  <p className="muted">
                    No evidence yet. This workspace records supplied results; it
                    does not execute commands.
                  </p>
                )}
              </section>
              <section className="detail-section">
                <div className="section-heading">
                  <h3>Human judgment</h3>
                  {human && task.status === "in_review" && current && (
                    <button
                      disabled={current.created_by === state.actor.id}
                      onClick={() => setModal("review.create")}
                    >
                      Review candidate
                    </button>
                  )}
                </div>
                {human &&
                  current?.created_by === state.actor.id &&
                  task.status === "in_review" && (
                    <p className="gate">
                      A different human principal must review your artifact.
                    </p>
                  )}
                {[...task.reviews].reverse().map((r) => (
                  <div className="review" key={r.id}>
                    <Badge status={r.decision} />
                    <p>{r.comment}</p>
                    <small>
                      {
                        state.principals.find((p) => p.id === r.created_by)
                          ?.name
                      }{" "}
                      · {date(r.created_at)} ·{" "}
                      {r.artifact_id === current?.id
                        ? "current candidate"
                        : "superseded candidate"}
                    </small>
                  </div>
                ))}
                {!task.reviews.length && (
                  <p className="muted">No human decision yet.</p>
                )}
              </section>
            </div>
          </section>
        </div>
      )}
      {modal && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
          >
            <header>
              <h2 id="modal-title">
                {
                  (
                    {
                      "project.create": "Create a project",
                      "task.create": "Define the work",
                      "artifact.add": "Add an artifact",
                      "evidence.add": "Record evidence",
                      "review.create": "Review current candidate",
                      "principal.create": "Create a principal",
                      "grant.create": "Delegate capabilities",
                      verify: "Verify portable bundle",
                    } as Record<string, string>
                  )[modal]
                }
              </h2>
              <button aria-label="Close form" onClick={() => setModal("")}>
                <X size={21} />
              </button>
            </header>
            <form onSubmit={submit}>
              {modal === "project.create" && (
                <>
                  {field("name", "Project name")}
                  {field(
                    "description",
                    "Intent",
                    false,
                    "What will this project accomplish?",
                    true,
                  )}
                  {field(
                    "repository",
                    "Repository reference",
                    false,
                    "https://…",
                  )}
                </>
              )}
              {modal === "task.create" && (
                <>
                  <label>
                    Project
                    <select name="project_id" required defaultValue={project}>
                      <option value="" disabled>
                        Select a project
                      </option>
                      {state.projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {!state.projects.length && (
                    <p className="gate">Create a project first.</p>
                  )}
                  {field("title", "Task title")}
                  {field(
                    "description",
                    "Intent and context",
                    true,
                    "Describe the outcome.",
                    true,
                  )}
                  {field(
                    "criteria",
                    "Acceptance criteria",
                    true,
                    "One criterion per line",
                    true,
                  )}
                  {field(
                    "scope",
                    "Scope boundary",
                    true,
                    "One path or boundary per line",
                    true,
                  )}
                  <label>
                    Priority
                    <select name="priority">
                      <option value="normal">Normal</option>
                      <option value="high">High</option>
                      <option value="low">Low</option>
                    </select>
                  </label>
                  <fieldset>
                    <legend>Dependencies (optional)</legend>
                    {state.tasks.map((t) => (
                      <label className="checkbox" key={t.id}>
                        <input
                          type="checkbox"
                          name="dependencies"
                          value={t.id}
                        />
                        {t.title}
                      </label>
                    ))}
                  </fieldset>
                </>
              )}
              {modal === "artifact.add" && (
                <>
                  <p className="gate">
                    A new candidate supersedes previous evidence and reviews.
                  </p>
                  {field("title", "Artifact title")}
                  <label>
                    Kind
                    <select name="kind">
                      <option value="git_commit">Git commit</option>
                      <option value="document">Document</option>
                    </select>
                  </label>
                  {field(
                    "revision",
                    "Exact revision",
                    true,
                    "Full Git SHA or document SHA-256",
                  )}
                  {field(
                    "digest",
                    "Content SHA-256",
                    true,
                    "64 hexadecimal characters",
                  )}
                  {field(
                    "uri",
                    "Reference URI",
                    false,
                    "Recorded only; never fetched",
                  )}
                  {field("summary", "Summary", true, "What changed?", true)}
                </>
              )}
              {modal === "evidence.add" && (
                <>
                  <p className="gate">
                    Bound to current artifact: {current?.title}. Evidence is
                    supplied; Synbios does not run commands.
                  </p>
                  <label>
                    Kind
                    <select name="kind">
                      <option value="test">Test</option>
                      <option value="analysis">Analysis</option>
                      <option value="proof">Proof (shadow evidence)</option>
                    </select>
                  </label>
                  <label>
                    Result
                    <select name="status">
                      <option value="passed">Passed</option>
                      <option value="failed">Failed</option>
                      <option value="unavailable">Unavailable</option>
                    </select>
                  </label>
                  {field("command", "Command or procedure", false)}
                  {field(
                    "summary",
                    "Result summary",
                    true,
                    "What does this evidence establish?",
                    true,
                  )}
                  {field("tool", "Tool")}
                  {field("tool_version", "Tool version")}
                  {field(
                    "assumptions",
                    "Assumptions and limits",
                    false,
                    "One assumption per line",
                    true,
                  )}
                </>
              )}
              {modal === "review.create" && (
                <>
                  <p className="gate">
                    Reviewing {current?.title} at exact revision{" "}
                    {current?.revision}. Acceptance does not merge or deploy.
                  </p>
                  <label>
                    Decision
                    <select name="decision">
                      <option value="approved">Approve and accept</option>
                      <option value="changes_requested">Request changes</option>
                    </select>
                  </label>
                  {field(
                    "comment",
                    "Review rationale",
                    true,
                    "State your judgment.",
                    true,
                  )}
                </>
              )}
              {modal === "principal.create" && (
                <>
                  {field("name", "Principal name")}
                  <label>
                    Kind
                    <select name="kind">
                      <option value="agent">Agent</option>
                      <option value="human">Human administrator</option>
                    </select>
                  </label>
                  <p className="gate">
                    Human principals administer all local work. Credential shown
                    once.
                  </p>
                </>
              )}
              {modal === "grant.create" && (
                <>
                  <label>
                    Principal
                    <select required name="principal_id">
                      <option value="">Select principal</option>
                      {state.principals
                        .filter((p) => p.active)
                        .map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} ({p.kind})
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Task
                    <select required name="task_id">
                      <option value="">Select task</option>
                      {state.tasks.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <fieldset>
                    <legend>Capabilities</legend>
                    {["claim", "work", "artifact", "evidence", "submit"].map(
                      (c) => (
                        <label className="checkbox" key={c}>
                          <input
                            type="checkbox"
                            name="capabilities"
                            value={c}
                          />
                          {label(c)}
                        </label>
                      ),
                    )}
                  </fieldset>
                </>
              )}
              {modal === "verify" && (
                <>
                  <p className="gate">
                    Checks internal bundle consistency. Does not authenticate
                    identity, external facts, or dependency acceptance outside
                    this bundle.
                  </p>
                  {field(
                    "bundle",
                    "Portable bundle JSON",
                    true,
                    "Paste exported bundle",
                    true,
                  )}
                </>
              )}
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              <footer>
                <button type="button" onClick={() => setModal("")}>
                  Cancel
                </button>
                <button
                  className="primary"
                  disabled={
                    busy || (modal === "task.create" && !state.projects.length)
                  }
                >
                  {busy
                    ? "Saving…"
                    : modal === "verify"
                      ? "Verify bundle"
                      : "Save to record"}
                  <ArrowRight size={16} />
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}
      {secret && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="secret-title"
          >
            <KeyRound size={32} />
            <h2 id="secret-title">One credential. Shown once.</h2>
            <p>
              Copy this token now and give it securely to the intended
              principal. It cannot be retrieved again.
            </p>
            <pre className="secret">{secret}</pre>
            <button
              onClick={() => {
                void navigator.clipboard
                  .writeText(secret)
                  .then(() => setNotice("Credential copied."))
                  .catch(() =>
                    setError(
                      "Clipboard unavailable. Select and copy the credential manually.",
                    ),
                  );
              }}
            >
              <Copy size={15} />
              Copy credential
            </button>
            <button className="primary" onClick={() => setSecret("")}>
              I have saved it <Check size={16} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
function Logo() {
  return (
    <div className="logo">
      <span>
        <Hexagon size={29} />
        <i />
      </span>
      synbios<span className="logo-period">.</span>
    </div>
  );
}
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge status-" + status}>
      <i />
      {label(status)}
    </span>
  );
}
function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <Hexagon size={35} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
