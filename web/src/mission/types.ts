export type Principal = {
  id: string;
  name: string;
  kind: "human" | "agent";
  active: boolean;
  created_at: string;
};
export type Project = {
  id: string;
  name: string;
  description: string;
  repository: string;
  workspace?: string;
  revision?: number;
  created_at: string;
};
export type Artifact = {
  contract_revision?: number;
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
export type Evidence = {
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
  stale?: boolean;
  created_by?: string;
  created_at: string;
};
export type Review = {
  id: string;
  artifact_id: string;
  revision: string;
  decision: string;
  comment: string;
  created_by: string;
  created_at: string;
};
export type Stage = "idea" | "shape" | "prototype" | "build" | "ship";
export const stages: Stage[] = ["idea", "shape", "prototype", "build", "ship"];
export const stageNames = ["Idea", "Shape", "Prototype", "Build", "Ship"];
export type Report = {
  assignment_revision?: number;
  id: string;
  summary: string;
  progress: number | null;
  blocker: string;
  created_by: string;
  created_at: string;
};
export type Decision = {
  id: string;
  title: string;
  question: string;
  options: string[];
  status: "open" | "resolved" | "withdrawn";
  choice: string | null;
  note: string;
  created_by: string;
  created_at: string;
  resolved_by?: string;
  resolved_at?: string;
};
export type Blocker = {
  kind: string;
  summary: string;
  task_id?: string;
  decision_id?: string;
};
export type Task = {
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
  stage?: Stage;
  candidate_path?: string;
  revision?: number;
  assignment_revision?: number;
  contract_revision?: number;
  reports?: Report[];
  decisions?: Decision[];
  blockers?: Blocker[];
  created_at?: string;
  created_by?: string;
};
export type Event = {
  id: string;
  seq: number;
  type: string;
  actor_id: string;
  task_id: string | null;
  hash: string;
  created_at: string;
  payload?: Record<string, unknown>;
};
export type Snapshot = {
  actor: Principal;
  projects: Project[];
  tasks: Task[];
  principals: Principal[];
  grants: {
    id: string;
    principal_id: string;
    task_id: string;
    capabilities: string[];
    revoked_at: string | null;
  }[];
  coordinator_grants?: {
    id: string;
    principal_id: string;
    project_id: string;
    revoked_at: string | null;
  }[];
  events: Event[];
  integrity: { valid: boolean; event_count: number };
  metrics: Record<string, number>;
  scope_overlaps?: {
    task_ids?: string[];
    task_id?: string;
    other_task_id?: string;
    paths?: string[];
    [key: string]: unknown;
  }[];
  resources?: {
    telemetry: string;
    allocation: { principal_id: string; task_ids: string[] }[];
  };
};
export type Command = (
  action: string,
  payload: Record<string, unknown>,
) => Promise<Record<string, unknown> | null>;
