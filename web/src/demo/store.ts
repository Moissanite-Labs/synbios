/**
 * In-browser demo forge store. Mirrors synbios.store rules for static hosting.
 * Data resets when the tab is closed; not a substitute for the local Python backend.
 */
import fixture from "./fixture.json";

type JsonObject = Record<string, unknown>;

export class DemoError extends Error {
  status: number;
  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

const CAPABILITIES = new Set([
  "claim",
  "work",
  "artifact",
  "evidence",
  "submit",
]);

const COMMAND_FIELDS: Record<string, Set<string>> = {
  "project.create": new Set(["name", "description", "repository"]),
  "principal.create": new Set(["name", "kind"]),
  "principal.revoke": new Set(["principal_id"]),
  "grant.create": new Set(["principal_id", "task_id", "capabilities"]),
  "grant.revoke": new Set(["grant_id"]),
  "task.create": new Set([
    "project_id",
    "title",
    "description",
    "criteria",
    "scope",
    "priority",
    "dependencies",
  ]),
  "task.claim": new Set(["task_id"]),
  "task.transition": new Set(["task_id", "status"]),
  "artifact.add": new Set([
    "task_id",
    "title",
    "kind",
    "revision",
    "digest",
    "uri",
    "summary",
  ]),
  "evidence.add": new Set([
    "task_id",
    "artifact_id",
    "artifact_digest",
    "revision",
    "kind",
    "status",
    "command",
    "summary",
    "tool",
    "tool_version",
    "assumptions",
  ]),
  "review.create": new Set([
    "task_id",
    "artifact_id",
    "revision",
    "decision",
    "comment",
  ]),
};

function pyCanonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(pyCanonical);
  if (value && typeof value === "object") {
    const sorted: JsonObject = {};
    for (const key of Object.keys(value as JsonObject).sort()) {
      sorted[key] = pyCanonical((value as JsonObject)[key]);
    }
    return sorted;
  }
  return value;
}

async function chainDigest(value: unknown): Promise<string> {
  const text = JSON.stringify(pyCanonical(value));
  const hash = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(hash)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function hashToken(token: string): Promise<string> {
  const hash = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(token),
  );
  return [...new Uint8Array(hash)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function now(): string {
  return new Date().toISOString();
}

function uid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

type InternalState = {
  projects: JsonObject[];
  tasks: JsonObject[];
  principals: JsonObject[];
  grants: JsonObject[];
  credentials: Record<string, string>;
};

type Event = JsonObject;

export const demoTokens = fixture.tokens;

export class DemoStore {
  private state: InternalState;
  private events: Event[];

  constructor() {
    this.state = {
      ...(structuredClone(fixture.state) as Omit<InternalState, "credentials">),
      credentials: structuredClone(fixture.credentials),
    };
    this.events = structuredClone(fixture.events) as Event[];
  }

  async snapshot(token: string): Promise<JsonObject> {
    await this.load();
    const actor = await this.auth(token);
    const result: JsonObject = {
      projects: structuredClone(this.state.projects),
      tasks: structuredClone(this.state.tasks),
      principals: structuredClone(this.state.principals),
      grants: structuredClone(this.state.grants),
    };
    for (const task of result.tasks as JsonObject[]) {
      const artifacts = task.artifacts as JsonObject[];
      const current = artifacts.length ? artifacts[artifacts.length - 1] : null;
      for (const evidence of task.evidence as JsonObject[]) {
        evidence.stale = !current || evidence.artifact_id !== current.id;
      }
    }
    return {
      ...result,
      version: 1,
      actor,
      events: structuredClone(this.events),
      integrity: { valid: true, event_count: this.events.length },
      metrics: {
        tasks: this.state.tasks.length,
        accepted: this.state.tasks.filter((t) => t.status === "accepted")
          .length,
      },
    };
  }

  async command(
    token: string,
    action: string,
    payload: JsonObject,
  ): Promise<JsonObject> {
    await this.load();
    const actor = await this.auth(token);
    const [result] = await this.runCommand(actor, action, payload);
    return structuredClone(result) as JsonObject;
  }

  async export(token: string, taskId: string): Promise<JsonObject> {
    const snapshot = await this.snapshot(token);
    const tasks = snapshot.tasks as JsonObject[];
    const task = structuredClone(
      this.find(tasks, taskId, "Task"),
    ) as JsonObject;
    for (const evidence of task.evidence as JsonObject[]) {
      delete evidence.stale;
    }
    const involved = new Set<string>();
    involved.add(String(task.created_by));
    if (task.assignee_id) involved.add(String(task.assignee_id));
    for (const key of ["artifacts", "evidence", "reviews"] as const) {
      for (const row of task[key] as JsonObject[]) {
        involved.add(String(row.created_by));
      }
    }
    const events = (snapshot.events as Event[]).filter(
      (event) => event.task_id === taskId,
    );
    const bundle: JsonObject = {
      version: 1,
      format: "synbios-task",
      exported_at: now(),
      task,
      project: this.find(
        snapshot.projects as JsonObject[],
        String(task.project_id),
        "Project",
      ),
      principals: (snapshot.principals as JsonObject[]).filter((principal) =>
        involved.has(String(principal.id)),
      ),
      events,
      audit_chain: (snapshot.events as Event[]).map((event) => ({
        seq: event.seq,
        hash: event.hash,
        previous_hash: event.previous_hash,
      })),
      limitations: [
        "Local tamper detection only; not signed identity or proof of completeness. Unrelated event payloads are omitted; their commitments are not independently verifiable.",
        "Evidence is reported by principals; proof is shadow evidence, not platform-verified truth.",
        "GitHub Pages demo: in-browser mock only; data is not persisted.",
      ],
    };
    bundle.bundle_digest = await chainDigest(
      Object.fromEntries(
        Object.entries(bundle).filter(([key]) => key !== "bundle_digest"),
      ),
    );
    return bundle;
  }

  private async load(): Promise<void> {
    let previous = "0".repeat(64);
    for (let index = 0; index < this.events.length; index++) {
      const event = this.events[index];
      if (typeof event.seq !== "number" || event.seq !== index + 1) {
        throw new DemoError(
          "Store integrity failure: Broken audit sequence",
          409,
        );
      }
      if (event.previous_hash !== previous) {
        throw new DemoError(
          "Store integrity failure: Broken audit sequence",
          409,
        );
      }
      const body = { ...event };
      delete body.hash;
      if ((await chainDigest(body)) !== event.hash) {
        throw new DemoError(
          "Store integrity failure: Audit hash mismatch",
          409,
        );
      }
      previous = String(event.hash);
    }
    const stateDigest = await chainDigest(this.state);
    if (this.events.length) {
      const last = this.events[this.events.length - 1].payload as JsonObject;
      if (last.state_digest !== stateDigest) {
        throw new DemoError(
          "Store integrity failure: State does not match audit",
          409,
        );
      }
    }
  }

  private async auth(token: string): Promise<JsonObject> {
    if (typeof token !== "string" || !token) {
      throw new DemoError("Authentication required", 401);
    }
    const hashed = await hashToken(token);
    let principalId: string | undefined;
    for (const [stored, pid] of Object.entries(this.state.credentials)) {
      if (stored === hashed) {
        principalId = pid;
        break;
      }
    }
    const principal = this.state.principals.find(
      (row) => row.id === principalId && row.active,
    );
    if (!principal) {
      throw new DemoError("Invalid credential", 401);
    }
    return principal;
  }

  private async save(
    actor: JsonObject,
    action: string,
    entity: JsonObject,
    task: JsonObject | null,
  ): Promise<void> {
    const payload: JsonObject = {
      state_digest: await chainDigest(this.state),
      entity,
    };
    if (task) payload.task = task;
    const event: Event = {
      seq: this.events.length + 1,
      id: uid(),
      type: action,
      actor_id: actor.id,
      task_id: task ? task.id : null,
      created_at: now(),
      payload,
      previous_hash: this.events.length
        ? this.events[this.events.length - 1].hash
        : "0".repeat(64),
    };
    const body = { ...event };
    delete body.hash;
    event.hash = await chainDigest(body);
    this.events.push(event);
  }

  private async runCommand(
    actor: JsonObject,
    action: string,
    payload: JsonObject,
  ): Promise<[JsonObject, JsonObject | null]> {
    if (!(action in COMMAND_FIELDS)) {
      throw new DemoError("Unknown command", 404);
    }
    const allowed = COMMAND_FIELDS[action];
    const extra = Object.keys(payload).filter((key) => !allowed.has(key));
    if (extra.length) {
      throw new DemoError("Unknown command fields: " + extra.sort().join(", "));
    }
    const human = actor.kind === "human";
    const humanOnly = () => {
      if (!human) throw new DemoError("Human authority required", 403);
    };
    let task: JsonObject | null = null;
    let result: JsonObject;

    if (
      [
        "project.create",
        "principal.create",
        "principal.revoke",
        "grant.create",
        "grant.revoke",
        "task.create",
      ].includes(action)
    ) {
      humanOnly();
    }

    if (action === "project.create") {
      result = {
        id: uid(),
        name: this.text(payload.name, "name"),
        description: this.text(payload.description, "description", true),
        repository: this.text(payload.repository, "repository", true),
        created_at: now(),
      };
      this.state.projects.push(result);
    } else if (action === "principal.create") {
      result = await this.createPrincipal(
        String(payload.name),
        this.choice(payload.kind, ["human", "agent"], "kind"),
      );
    } else if (action === "principal.revoke") {
      result = this.find(
        this.state.principals,
        String(payload.principal_id),
        "Principal",
      );
      if (result.id === actor.id) {
        throw new DemoError("Cannot revoke your own credential", 409);
      }
      if (!result.active) {
        throw new DemoError("Principal already revoked", 409);
      }
      const activeHumans = this.state.principals.filter(
        (row) => row.active && row.kind === "human",
      ).length;
      if (result.kind === "human" && activeHumans <= 1) {
        throw new DemoError("Cannot revoke the last active human", 409);
      }
      result.active = false;
      this.state.credentials = Object.fromEntries(
        Object.entries(this.state.credentials).filter(
          ([, pid]) => pid !== result.id,
        ),
      );
    } else if (action === "grant.create") {
      this.find(
        this.state.principals,
        String(payload.principal_id),
        "Principal",
      );
      this.find(this.state.tasks, String(payload.task_id), "Task");
      const caps = this.strings(payload.capabilities, "capabilities", true);
      if (!caps.every((cap) => CAPABILITIES.has(cap))) {
        throw new DemoError("Unknown capability");
      }
      result = {
        id: uid(),
        principal_id: payload.principal_id,
        task_id: payload.task_id,
        capabilities: [...new Set(caps)],
        created_by: actor.id,
        created_at: now(),
        revoked_at: null,
      };
      this.state.grants.push(result);
    } else if (action === "grant.revoke") {
      result = this.find(this.state.grants, String(payload.grant_id), "Grant");
      if (result.revoked_at) {
        throw new DemoError("Grant already revoked", 409);
      }
      result.revoked_at = now();
    } else if (action === "task.create") {
      this.find(this.state.projects, String(payload.project_id), "Project");
      const deps = this.strings(payload.dependencies ?? [], "dependencies");
      for (const dep of deps) this.find(this.state.tasks, dep, "Dependency");
      result = {
        id: uid(),
        project_id: payload.project_id,
        title: this.text(payload.title, "title"),
        description: this.text(payload.description, "description", true),
        criteria: this.strings(payload.criteria, "criteria", true),
        scope: this.strings(payload.scope, "scope", true),
        status: "open",
        priority: this.choice(
          payload.priority,
          ["low", "normal", "high"],
          "priority",
          "normal",
        ),
        assignee_id: null,
        dependencies: [...new Set(deps)],
        created_by: actor.id,
        created_at: now(),
        updated_at: now(),
        artifacts: [],
        evidence: [],
        reviews: [],
      };
      this.state.tasks.push(result);
      task = result;
    } else if (
      [
        "task.claim",
        "task.transition",
        "artifact.add",
        "evidence.add",
        "review.create",
      ].includes(action)
    ) {
      task = this.find(this.state.tasks, String(payload.task_id), "Task");
      if (task.status === "accepted") {
        throw new DemoError("Accepted tasks are immutable", 409);
      }
      const capabilityMap: Record<string, string | null> = {
        "task.claim": "claim",
        "artifact.add": "artifact",
        "evidence.add": "evidence",
        "review.create": null,
        "task.transition": payload.status === "in_review" ? "submit" : "work",
      };
      const capability = capabilityMap[action];
      if (
        !human &&
        (capability === null ||
          !this.state.grants.some(
            (grant) =>
              grant.principal_id === actor.id &&
              grant.task_id === task!.id &&
              !grant.revoked_at &&
              (grant.capabilities as string[]).includes(String(capability)),
          ))
      ) {
        throw new DemoError("Task capability required", 403);
      }
      if (action === "task.claim") {
        if (task.status !== "open" || task.assignee_id) {
          throw new DemoError("Task is not available to claim", 409);
        }
        task.status = "claimed";
        task.assignee_id = actor.id;
        result = task;
      } else if (action === "task.transition") {
        const status = this.choice(
          payload.status,
          ["in_progress", "in_review", "cancelled", "open"],
          "status",
        );
        const allowed: Record<string, Set<string>> = {
          open: new Set(["cancelled"]),
          claimed: new Set(["in_progress", "cancelled", "open"]),
          in_progress: new Set(["in_review", "cancelled", "open"]),
          in_review: new Set(["cancelled", "open"]),
          changes_requested: new Set([
            "in_progress",
            "in_review",
            "cancelled",
            "open",
          ]),
          cancelled: new Set(["open"]),
        };
        if (!allowed[String(task.status)]?.has(status)) {
          throw new DemoError("Invalid task transition", 409);
        }
        if (status === "cancelled" || status === "open") humanOnly();
        if (status === "in_review") this.ready(task);
        task.status = status;
        if (status === "open") task.assignee_id = null;
        result = task;
      } else if (action === "artifact.add") {
        if (task.status === "cancelled") {
          throw new DemoError("Reopen cancelled task first", 409);
        }
        const kind = this.choice(
          payload.kind,
          ["git_commit", "document"],
          "kind",
        );
        const revision = this.text(payload.revision, "revision");
        const sha = this.text(payload.digest, "digest");
        const revPattern =
          kind === "git_commit"
            ? /^[0-9a-fA-F]{40}|[0-9a-fA-F]{64}$/
            : /^[0-9a-fA-F]{64}$/;
        if (!/^[0-9a-fA-F]{64}$/.test(sha) || !revPattern.test(revision)) {
          throw new DemoError("Invalid revision or SHA-256 digest");
        }
        result = {
          id: uid(),
          task_id: task.id,
          title: this.text(payload.title, "title"),
          kind,
          revision: revision.toLowerCase(),
          digest: sha.toLowerCase(),
          uri: this.text(payload.uri, "uri", true),
          summary: this.text(payload.summary, "summary", true),
          created_by: actor.id,
          created_at: now(),
        };
        (task.artifacts as JsonObject[]).push(result);
        if (task.status === "in_review") task.status = "in_progress";
      } else if (action === "evidence.add") {
        const artifact = this.find(
          task.artifacts as JsonObject[],
          String(payload.artifact_id),
          "Artifact",
        );
        if (
          payload.artifact_digest !== artifact.digest ||
          payload.revision !== artifact.revision
        ) {
          throw new DemoError("Evidence binding mismatch", 409);
        }
        if (task.status === "cancelled") {
          throw new DemoError("Reopen cancelled task first", 409);
        }
        result = {
          id: uid(),
          task_id: task.id,
          artifact_id: artifact.id,
          artifact_digest: artifact.digest,
          revision: artifact.revision,
          kind: this.choice(
            payload.kind,
            ["test", "proof", "analysis"],
            "kind",
          ),
          status: this.choice(
            payload.status,
            ["passed", "failed", "unavailable"],
            "status",
          ),
          command: this.text(payload.command, "command", true),
          summary: this.text(payload.summary, "summary"),
          tool: this.text(payload.tool, "tool"),
          tool_version: this.text(payload.tool_version, "tool_version"),
          assumptions: this.strings(payload.assumptions ?? [], "assumptions"),
          created_by: actor.id,
          created_at: now(),
        };
        (task.evidence as JsonObject[]).push(result);
      } else {
        humanOnly();
        if (task.status !== "in_review") {
          throw new DemoError("Task must be in review", 409);
        }
        const artifacts = task.artifacts as JsonObject[];
        const artifact = artifacts.length
          ? artifacts[artifacts.length - 1]
          : null;
        if (
          !artifact ||
          payload.artifact_id !== artifact.id ||
          payload.revision !== artifact.revision
        ) {
          throw new DemoError("Review must bind exact current candidate", 409);
        }
        if (artifact.created_by === actor.id) {
          throw new DemoError("Independent human reviewer required", 403);
        }
        const decision = this.choice(
          payload.decision,
          ["approved", "changes_requested"],
          "decision",
        );
        if (decision === "approved") this.ready(task);
        result = {
          id: uid(),
          task_id: task.id,
          artifact_id: artifact.id,
          revision: artifact.revision,
          decision,
          comment: this.text(payload.comment, "comment", true),
          created_by: actor.id,
          created_at: now(),
        };
        (task.reviews as JsonObject[]).push(result);
        task.status =
          decision === "approved" ? "accepted" : "changes_requested";
      }
      task.updated_at = now();
    } else {
      throw new DemoError("Unknown command", 404);
    }

    await this.save(actor, action, result, task);
    return [result, task];
  }

  private async createPrincipal(
    name: string,
    kind: string,
  ): Promise<JsonObject> {
    const principal: JsonObject = {
      id: uid(),
      name: this.text(name, "name"),
      kind,
      active: true,
      created_at: now(),
    };
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    const token = btoa(String.fromCharCode(...bytes))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    this.state.principals.push(principal);
    this.state.credentials[await hashToken(token)] = String(principal.id);
    return { principal, token };
  }

  private ready(task: JsonObject): JsonObject {
    const artifacts = task.artifacts as JsonObject[];
    if (!artifacts.length) {
      throw new DemoError("Current artifact required", 409);
    }
    const current = artifacts[artifacts.length - 1];
    const tests = (task.evidence as JsonObject[]).filter(
      (row) => row.artifact_id === current.id && row.kind === "test",
    );
    if (
      !tests.some((row) => row.status === "passed") ||
      tests.some((row) => row.status === "failed")
    ) {
      throw new DemoError(
        "Passing current test evidence without failures required",
        409,
      );
    }
    for (const dep of task.dependencies as string[]) {
      if (
        this.find(this.state.tasks, dep, "Dependency").status !== "accepted"
      ) {
        throw new DemoError("Dependencies must be accepted", 409);
      }
    }
    return current;
  }

  private find<T extends JsonObject>(
    items: T[],
    identifier: string,
    label: string,
  ): T {
    const item = items.find((row) => row.id === identifier);
    if (!item) throw new DemoError(label + " not found", 404);
    return item;
  }

  private text(value: unknown, field: string, optional = false): string {
    if (typeof value !== "string" || (!optional && !value.trim())) {
      throw new DemoError("Invalid " + field);
    }
    if (value.length > 50000) throw new DemoError("Invalid " + field);
    return value;
  }

  private strings(value: unknown, field: string, required = false): string[] {
    if (
      !Array.isArray(value) ||
      (required && !value.length) ||
      value.length > 1000
    ) {
      throw new DemoError("Invalid " + field);
    }
    return value.map((entry) => this.text(entry, field));
  }

  private choice(
    value: unknown,
    options: string[],
    field: string,
    defaultValue?: string,
  ): string {
    const resolved =
      value === undefined && defaultValue !== undefined ? defaultValue : value;
    if (typeof resolved !== "string" || !options.includes(resolved)) {
      throw new DemoError("Invalid " + field);
    }
    return resolved;
  }
}

let singleton: DemoStore | null = null;

export function getDemoStore(): DemoStore {
  if (!singleton) singleton = new DemoStore();
  return singleton;
}

export async function demoRequest(
  path: string,
  method: string,
  token: string,
  body?: unknown,
): Promise<JsonObject> {
  const store = getDemoStore();
  try {
    if (method === "GET" && path === "state") {
      return store.snapshot(token);
    }
    if (
      method === "GET" &&
      path.startsWith("tasks/") &&
      path.endsWith("/export")
    ) {
      const taskId = decodeURIComponent(
        path.slice("tasks/".length, -"/export".length),
      );
      return store.export(token, taskId);
    }
    if (method === "POST" && path.startsWith("commands/")) {
      const action = path.slice("commands/".length);
      if (!body || typeof body !== "object" || Array.isArray(body)) {
        throw new DemoError("Payload must be an object");
      }
      return store.command(token, action, body as JsonObject);
    }
    if (method === "POST" && path === "bundles/verify") {
      return verifyBundle(body);
    }
    throw new DemoError("Unknown API route", 404);
  } catch (error) {
    if (error instanceof DemoError) throw error;
    throw new DemoError(String(error), 500);
  }
}

async function verifyBundle(bundle: unknown): Promise<JsonObject> {
  const errors: string[] = [];
  try {
    if (
      !bundle ||
      typeof bundle !== "object" ||
      typeof (bundle as JsonObject).version !== "number" ||
      (bundle as JsonObject).version !== 1 ||
      (bundle as JsonObject).format !== "synbios-task"
    ) {
      throw new Error("Unsupported bundle");
    }
    const record = bundle as JsonObject;
    const events = record.events;
    if (!Array.isArray(events) || !events.length) {
      throw new Error("Missing audit");
    }
    const links = record.audit_chain;
    if (!Array.isArray(links) || !links.length) {
      throw new Error("Missing audit commitments");
    }
    let previous = "0".repeat(64);
    for (let index = 0; index < links.length; index++) {
      const link = links[index] as JsonObject;
      if (
        typeof link.seq !== "number" ||
        link.seq !== index + 1 ||
        link.previous_hash !== previous ||
        typeof link.hash !== "string" ||
        !/^[0-9a-f]{64}$/.test(String(link.hash))
      ) {
        throw new Error("Broken audit commitments");
      }
      previous = String(link.hash);
    }
    let lastSeq = 0;
    for (const event of events as JsonObject[]) {
      if (
        typeof event.seq !== "number" ||
        !(lastSeq < event.seq && event.seq <= links.length)
      ) {
        throw new Error(
          "Task events must have unique increasing positive sequence numbers",
        );
      }
      lastSeq = event.seq as number;
      const body = { ...event };
      delete body.hash;
      if ((await chainDigest(body)) !== event.hash) {
        throw new Error("Task event hash mismatch");
      }
      const link = links[(event.seq as number) - 1] as JsonObject;
      if (
        event.seq !== link.seq ||
        event.hash !== link.hash ||
        event.previous_hash !== link.previous_hash
      ) {
        throw new Error("Event commitment mismatch");
      }
    }
    const digestValue = await chainDigest(
      Object.fromEntries(
        Object.entries(record).filter(([key]) => key !== "bundle_digest"),
      ),
    );
    if (record.bundle_digest !== digestValue) {
      throw new Error("Bundle digest mismatch");
    }
  } catch (error) {
    errors.push(error instanceof Error ? error.message : String(error));
  }
  return { valid: !errors.length, errors };
}
