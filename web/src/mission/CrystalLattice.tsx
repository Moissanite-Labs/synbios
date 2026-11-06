/**
 * Crystal Lattice merged: the chosen Exofab design, ported to live mission data.
 * Geometry, gradients, viewBox, ring census and node vocabulary are from
 * Exofab PR #17 (ee02b4b) / PR #20 (8adbd74), site/index.html.
 * The faint outer mesh is structural; solid / growing lines are real dependencies.
 */
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { Principal, Project, Stage, Task } from "./types";

export const LATTICE_STAGES = [
  { key: "idea", title: "Idea" },
  { key: "shape", title: "Shape" },
  { key: "prototype", title: "Prototype" },
  { key: "build", title: "Build" },
  { key: "ship", title: "Ship" },
] as const;

const S = 31;
const R3 = Math.sqrt(3);
const directions = [
  [1, 0],
  [1, -1],
  [0, -1],
  [-1, 0],
  [-1, 1],
  [0, 1],
];

/** Original axial hexagon geometry; do not replace it with a radial layout. */
function ring(k: number): [number, number][] {
  if (!k) return [[0, 0]];
  const result: [number, number][] = [];
  let q = directions[4][0] * k;
  let r = directions[4][1] * k;
  for (let i = 0; i < 6; i++) {
    for (let j = 0; j < k; j++) {
      result.push([q, r]);
      q += directions[i][0];
      r += directions[i][1];
    }
  }
  return result;
}

const px = (q: number, r: number): [number, number] => [
  S * R3 * (q + r / 2),
  S * 1.5 * r,
];
const ringHex = (k: number) =>
  ring(k)
    .filter((_, index) => index % k === 0)
    .map(([q, r]) => px(q, r).join(","))
    .join(" ");
const capacity = (k: number) => (k ? 6 * k : 1);

export function latticeStage(task: Task): number {
  const stage = String(task.stage || "build");
  // Early project records used "plan"; the chosen design calls this ring Shape.
  const key = stage === "plan" ? "shape" : stage;
  const index = LATTICE_STAGES.findIndex((item) => item.key === key);
  return index < 0 ? 3 : index;
}

function needsDecision(task: Task): boolean {
  if (["accepted", "cancelled"].includes(task.status)) return false;
  return (
    task.status === "in_review" ||
    !!task.decisions?.some((decision) => decision.status === "open")
  );
}

type Node = {
  id: string;
  k: number;
  i: number;
  x: number;
  y: number;
  task?: Task;
  principal?: Principal;
  state: "ghost" | "done" | "pending" | "forming" | "planned";
};

type Props = {
  tasks: Task[];
  principals: Principal[];
  project?: Project;
  selected: string;
  highlighted: string | null;
  onSelect: (id: string) => void;
  onStage: (stage: Stage) => void;
  onMissionSelect?: () => void;
};

export default function CrystalLattice({
  tasks,
  principals,
  project,
  selected,
  highlighted,
  onSelect,
  onStage,
  onMissionSelect,
}: Props) {
  const [pages, setPages] = useState([0, 0, 0, 0, 0]);
  const [activeRing, setActiveRing] = useState<number | null>(null);
  const [tooltip, setTooltip] = useState<{
    title: string;
    label: string;
    left: number;
    top: number;
  } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const grouped = LATTICE_STAGES.map((_, k) =>
    tasks.filter((task) => latticeStage(task) === k),
  );
  const showGoal = !!project && grouped[0].length === 0;
  const selectedTask = tasks.find((task) => task.id === selected);
  const selectedRing = selectedTask ? latticeStage(selectedTask) : -1;
  const selectedIndex =
    selectedRing < 0
      ? -1
      : grouped[selectedRing].findIndex((task) => task.id === selected);
  // Selecting work from the list reveals its actual slot even on a later page.
  useEffect(() => {
    if (selectedRing < 0) return;
    const page = Math.floor(selectedIndex / capacity(selectedRing));
    setPages((previous) =>
      previous[selectedRing] === page
        ? previous
        : previous.map((value, k) => (k === selectedRing ? page : value)),
    );
  }, [selected, selectedRing, selectedIndex]);

  const currentPages = grouped.map((items, k) =>
    Math.min(pages[k], Math.max(0, Math.ceil(items.length / capacity(k)) - 1)),
  );
  const nodes: Node[] = [];
  grouped.forEach((items, k) => {
    const displayed = items.slice(
      currentPages[k] * capacity(k),
      (currentPages[k] + 1) * capacity(k),
    );
    ring(k).forEach(([q, r], i) => {
      const task = displayed[i];
      const [x, y] = px(q, r);
      nodes.push({
        id: `${k}-${i}`,
        k,
        i,
        x,
        y,
        task,
        principal: task
          ? principals.find((principal) => principal.id === task.assignee_id)
          : undefined,
        state: !task
          ? "ghost"
          : needsDecision(task)
            ? "pending"
            : task.status === "accepted"
              ? "done"
              : task.status === "in_progress"
                ? "forming"
                : "planned",
      });
    });
  });
  const byTask = new Map(
    nodes.filter((node) => node.task).map((node) => [node.task!.id, node]),
  );
  const selectedNode = byTask.get(selected);
  const focusedId = highlighted || selected;
  const focused = tasks.find((task) => task.id === focusedId);
  const isHighlighted = (node: Node) =>
    !!node.task &&
    (node.task.id === focusedId ||
      focused?.dependencies.includes(node.task.id) ||
      activeRing === node.k);
  const accepted = tasks.filter((task) => task.status === "accepted").length;
  const pending = tasks.filter(needsDecision).length;
  const forming = tasks.filter((task) => task.status === "in_progress").length;
  const undisplayedDependencies = selectedTask
    ? selectedTask.dependencies.filter((id) => !byTask.has(id)).length
    : 0;

  function positionTip(
    xValue: number,
    yValue: number,
    label: string,
    title: string,
  ) {
    if (!svgRef.current || !containerRef.current) return;
    const svgRect = svgRef.current.getBoundingClientRect();
    const containerRect = containerRef.current.getBoundingClientRect();
    const scale = svgRect.width / 408;
    const x = svgRect.left - containerRect.left + (xValue + 204) * scale + 14;
    const y = svgRect.top - containerRect.top + (yValue + 184) * scale - 18;
    setTooltip({
      title,
      label,
      left: Math.max(8, Math.min(x, containerRect.width - 250)),
      top: Math.max(8, y),
    });
  }

  function showTip(node: Node) {
    if (!node.task) return;
    positionTip(
      node.x,
      node.y,
      `${node.principal?.name || "Unassigned"} · ${node.task.status.replaceAll("_", " ")}`,
      node.task.title,
    );
  }

  function showMissionTip() {
    if (project)
      positionTip(
        0,
        0,
        "Mission goal",
        `${project.name}${project.description ? ` — ${project.description}` : ""}`,
      );
  }

  const selectMission = () =>
    onMissionSelect ? onMissionSelect() : onStage("idea");

  function shape(node: Node, r: number) {
    const { x, y, principal, state } = node;
    const unassigned = !principal;
    const outline = state === "pending" || state === "planned" || unassigned;
    const fill = outline
      ? "none"
      : principal?.kind === "human"
        ? "url(#gc)"
        : "url(#gs)";
    const stroke = outline
      ? state === "pending"
        ? "#e9f4ff"
        : unassigned
          ? "#a9b0b9"
          : principal?.kind === "human"
            ? "#f2ab6d"
            : "#7cc6f2"
      : undefined;
    const attributes = {
      className: "core",
      fill,
      stroke,
      strokeWidth: outline ? 1.4 : undefined,
      opacity: state === "forming" ? 0.6 : 1,
    };
    if (principal?.kind === "human")
      return <circle cx={x} cy={y} r={r} {...attributes} />;
    if (unassigned) {
      const points = Array.from({ length: 6 }, (_, index) => {
        const angle = (Math.PI / 3) * index;
        return `${x + r * Math.cos(angle)},${y + r * Math.sin(angle)}`;
      }).join(" ");
      return <polygon points={points} strokeLinejoin="round" {...attributes} />;
    }
    return (
      <polygon
        points={`${x},${y - r * 1.25} ${x + r * 1.25},${y} ${x},${y + r * 1.25} ${x - r * 1.25},${y}`}
        strokeLinejoin="round"
        {...attributes}
      />
    );
  }

  return (
    <section className="panel stagepanel col-c" aria-labelledby="lat-h">
      <div className="ph">
        <h2 id="lat-h">The crystal</h2>
        <span className="mono">
          {showGoal
            ? "goal at the core · work grows outward"
            : "each node is a piece of work"}
        </span>
      </div>
      <div className="lat" ref={containerRef}>
        <svg
          id="mission-lattice"
          ref={svgRef}
          viewBox="-204 -184 408 368"
          role="group"
          aria-label={`Mission lattice: ${showGoal ? "one mission goal, " : ""}${tasks.length} pieces of work, ${accepted} accepted, ${pending} awaiting a decision or review, ${forming} in progress. Rings grow from Idea to Ship. Lines connect dependencies.`}
        >
          <defs>
            <radialGradient id="gc" cx=".35" cy=".3">
              <stop offset="0" stopColor="#ffd9b5" />
              <stop offset=".6" stopColor="#f2ab6d" />
              <stop offset="1" stopColor="#a8632c" />
            </radialGradient>
            <radialGradient id="gs" cx=".35" cy=".3">
              <stop offset="0" stopColor="#dcf2ff" />
              <stop offset=".6" stopColor="#7cc6f2" />
              <stop offset="1" stopColor="#3a7ea8" />
            </radialGradient>
            <radialGradient id="halo">
              <stop offset="0" stopColor="#fff" stopOpacity=".35" />
              <stop offset="1" stopColor="#fff" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="spec" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#f2ab6d" />
              <stop offset=".3" stopColor="#f6e27a" />
              <stop offset=".55" stopColor="#8fe0b0" />
              <stop offset=".78" stopColor="#7cc6f2" />
              <stop offset="1" stopColor="#b9a2ff" />
            </linearGradient>
            <radialGradient id="bgglow">
              <stop offset="0" stopColor="#1b2633" stopOpacity=".95" />
              <stop offset=".55" stopColor="#111821" stopOpacity=".5" />
              <stop offset="1" stopColor="#08090a" stopOpacity="0" />
            </radialGradient>
          </defs>
          <ellipse cx="0" cy="0" rx="228" ry="198" fill="url(#bgglow)" />
          <g aria-hidden="true">
            {[1, 2, 3, 4].map((k) => (
              <polygon
                key={k}
                points={ringHex(k)}
                fill="none"
                stroke={k <= 2 ? "#232a31" : k === 3 ? "#1a1f24" : "#15191d"}
                strokeWidth="1"
                className={`guide${activeRing === k ? " gon" : ""}`}
                strokeDasharray={k === 4 ? "2 5" : "none"}
              />
            ))}
            {nodes.flatMap((a, i) =>
              nodes.slice(i + 1).flatMap((b) => {
                if (
                  a.k < 3 ||
                  b.k < 3 ||
                  a.task ||
                  b.task ||
                  Math.hypot(a.x - b.x, a.y - b.y) >= S * R3 + 1
                )
                  return [];
                return [
                  <line
                    key={`${a.id}-${b.id}`}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    className="edge ghost"
                  />,
                ];
              }),
            )}
          </g>
          <g aria-label="Work dependencies">
            {nodes.flatMap((node) =>
              (node.task?.dependencies || []).flatMap((dependencyId) => {
                const dependency = byTask.get(dependencyId);
                if (!dependency) return [];
                const light =
                  node.task?.id === focusedId || dependencyId === focusedId;
                const mx = ((node.x + dependency.x) / 2) * 0.55;
                const my = ((node.y + dependency.y) / 2) * 0.55;
                return [
                  <path
                    key={`${node.id}-${dependency.id}`}
                    d={`M${node.x},${node.y} Q${mx},${my} ${dependency.x},${dependency.y}`}
                    className={`thread${light ? " hl" : ""}`}
                    data-from={node.task?.id}
                    data-to={dependencyId}
                  >
                    <title>{`${node.task?.title} depends on ${dependency.task?.title}`}</title>
                  </path>,
                ];
              }),
            )}
          </g>
          <g>
            {nodes.map((node) => {
              const { task, principal, k, i, x, y, state } = node;
              if (showGoal && k === 0 && project) {
                const description = `Mission goal: ${project.name}${project.description ? `. ${project.description}` : ""}`;
                return (
                  <g
                    key="mission-goal"
                    className={`node planned${activeRing === 0 ? " hl" : ""}`}
                    data-mission-id={project.id}
                    data-slot="0-0"
                    role="button"
                    tabIndex={0}
                    aria-label={description}
                    onClick={selectMission}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        selectMission();
                      }
                    }}
                    onMouseEnter={showMissionTip}
                    onMouseLeave={() => setTooltip(null)}
                    onFocus={showMissionTip}
                    onBlur={() => setTooltip(null)}
                  >
                    <title>{description}</title>
                    <circle
                      cx="0"
                      cy="0"
                      r="18"
                      fill="url(#halo)"
                      className="halo"
                    />
                    <circle cx="0" cy="0" r="13" className="hlring" />
                    <circle cx="0" cy="0" r="14" fill="transparent" />
                    <polygon
                      points="8,0 4,6.928 -4,6.928 -8,0 -4,-6.928 4,-6.928"
                      className="core"
                      fill="none"
                      stroke="#e9f4ff"
                      strokeWidth="1.4"
                      strokeLinejoin="round"
                    />
                  </g>
                );
              }
              if (!task)
                return (
                  <circle
                    key={node.id}
                    cx={x}
                    cy={y}
                    r={k === 3 ? 2 : 1.6}
                    className="ghostn"
                    aria-hidden="true"
                  />
                );
              const name = principal?.name || "Unassigned";
              const description = `${task.title}; ${name}; ${task.status.replaceAll("_", " ")}${needsDecision(task) ? "; decision or review needed" : ""}`;
              return (
                <g
                  key={node.id}
                  className={`node ${state}${k === 2 ? " n2" : ""}${principal?.kind === "human" ? " hf" : ""}${isHighlighted(node) ? " hl" : ""}`}
                  style={{ "--i": i } as CSSProperties}
                  data-task-id={task.id}
                  data-slot={node.id}
                  role="button"
                  tabIndex={0}
                  aria-label={description}
                  aria-pressed={task.id === selected}
                  onClick={() => onSelect(task.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(task.id);
                    }
                  }}
                  onMouseEnter={() => showTip(node)}
                  onMouseLeave={() => setTooltip(null)}
                  onFocus={() => showTip(node)}
                  onBlur={() => setTooltip(null)}
                >
                  <title>{description}</title>
                  <circle
                    cx={x}
                    cy={y}
                    r="18"
                    fill="url(#halo)"
                    className="halo"
                  />
                  <circle cx={x} cy={y} r="13" className="hlring" />
                  <circle cx={x} cy={y} r="14" fill="transparent" />
                  {state === "pending" && (
                    <>
                      <circle cx={x} cy={y} r="9" className="pulse" />
                      <circle cx={x} cy={y} r="11" className="ring" />
                    </>
                  )}
                  {state === "forming" && (
                    <circle cx={x} cy={y} r="9" className="arc" />
                  )}
                  {shape(
                    node,
                    state === "pending"
                      ? 5.5
                      : state === "forming"
                        ? 4.5
                        : k === 0
                          ? 8
                          : 6,
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <div
          className={`tip${tooltip ? " on" : ""}`}
          style={tooltip ? { left: tooltip.left, top: tooltip.top } : undefined}
          aria-hidden="true"
        >
          {tooltip && (
            <>
              <span className="mono">{tooltip.label}</span>
              {tooltip.title}
            </>
          )}
        </div>
      </div>
      <ol className="census" aria-label="Rings of the crystal, one per stage">
        {LATTICE_STAGES.map((stage, k) => {
          const items = grouped[k];
          const humans = items.filter((task) =>
            principals.some(
              (principal) =>
                principal.id === task.assignee_id && principal.kind === "human",
            ),
          ).length;
          const agents = items.filter((task) =>
            principals.some(
              (principal) =>
                principal.id === task.assignee_id && principal.kind === "agent",
            ),
          ).length;
          const count = items.length;
          const missionGoal = showGoal && k === 0;
          return (
            <li key={stage.key}>
              <button
                className={`rk${selectedRing === k ? " now" : ""}${activeRing === k ? " on" : ""}`}
                onMouseEnter={() => setActiveRing(k)}
                onMouseLeave={() => setActiveRing(null)}
                onFocus={() => setActiveRing(k)}
                onBlur={() => setActiveRing(null)}
                onClick={() =>
                  missionGoal ? selectMission() : onStage(stage.key)
                }
                aria-label={
                  missionGoal
                    ? "Idea: one mission goal. Inspect the mission."
                    : `${stage.title}: ${count} ${count === 1 ? "piece" : "pieces"}. Show work in this stage.`
                }
              >
                <span className="n">00{k + 1}</span>
                <span className="t">{stage.title}</span>
                <span className="c">
                  {missionGoal
                    ? "1 mission goal"
                    : count
                      ? `${count} ${count === 1 ? "piece" : "pieces"}`
                      : "No work yet"}
                </span>
                <span className="split" aria-hidden="true">
                  {!!humans && <i className="h" style={{ flex: humans }} />}
                  {!!agents && <i className="a" style={{ flex: agents }} />}
                  {missionGoal && <i className="p" style={{ flex: 1 }} />}
                  {count > humans + agents && (
                    <i
                      className="p"
                      style={{ flex: count - humans - agents }}
                    />
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {grouped.some((items, k) => items.length > capacity(k)) && (
        <div
          className="lattice-pages"
          aria-label="Work on additional lattice pages"
          style={{ padding: "14px 24px 0" }}
        >
          {grouped.map((items, k) => {
            const total = Math.ceil(items.length / capacity(k));
            if (total <= 1) return null;
            const page = currentPages[k];
            const change = (next: number) => {
              setPages((previous) =>
                previous.map((value, index) => (index === k ? next : value)),
              );
              setTooltip(null);
            };
            return (
              <div
                key={k}
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  gap: 8,
                  marginTop: 6,
                }}
              >
                <span className="mono">
                  {LATTICE_STAGES[k].title} · {page + 1}/{total}
                </span>
                <button
                  className="mini"
                  disabled={page === 0}
                  onClick={() => change(page - 1)}
                  aria-label={`Previous ${LATTICE_STAGES[k].title} page`}
                >
                  Previous
                </button>
                <button
                  className="mini"
                  disabled={page + 1 >= total}
                  onClick={() => change(page + 1)}
                  aria-label={`Next ${LATTICE_STAGES[k].title} page`}
                >
                  Next
                </button>
                <span className="mono">
                  {Math.min(capacity(k), items.length - page * capacity(k))} of{" "}
                  {items.length} shown
                </span>
              </div>
            );
          })}
        </div>
      )}
      <div className="latfoot">
        <span>
          <b>{accepted}</b> accepted · <b>{pending}</b> needs a decision or
          review · <b>{forming}</b> in progress
        </span>
        <span>Rings: idea to ship. Threads: work dependencies.</span>
        {!tasks.length && (
          <span>
            {project
              ? "Your mission is at the core. Add work to grow its crystal."
              : "Set a mission, then add work to grow its crystal."}
          </span>
        )}
        {!!undisplayedDependencies && (
          <span>
            {undisplayedDependencies}{" "}
            {undisplayedDependencies === 1
              ? "dependency is"
              : "dependencies are"}{" "}
            on other ring pages; inspect the work panel for the complete list.
          </span>
        )}
        {selectedTask && !selectedNode && (
          <span>The selected work is on another page.</span>
        )}
      </div>
    </section>
  );
}
