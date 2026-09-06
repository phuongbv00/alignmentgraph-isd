import type {
  AgentContext,
  AlignmentGraphPayload,
  Brief,
  BriefResponse,
  Finding,
  GraphNode,
  Health,
  LLMConnectionInput,
  LLMConnections,
  Message,
  ModelList,
  PlanTurn,
  ProgramDetail,
  ProgramSummary,
  RunDetail,
} from './types'

const BASE = '/api'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    // The API always fails with {"detail": ...}; fall back to the status text
    // if something upstream produced a non-JSON error body.
    let detail = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/health'),

  listConnections: () => request<LLMConnections>('/connections'),
  createConnection: (connection: LLMConnectionInput) =>
    request<LLMConnections>('/connections', { method: 'POST', body: JSON.stringify(connection) }),
  updateConnection: (id: string, connection: LLMConnectionInput) =>
    request<LLMConnections>(`/connections/${id}`, {
      method: 'PUT',
      body: JSON.stringify(connection),
    }),
  activateConnection: (id: string) =>
    request<LLMConnections>(`/connections/${id}/activate`, { method: 'POST' }),
  deleteConnection: (id: string) =>
    request<LLMConnections>(`/connections/${id}`, { method: 'DELETE' }),
  // The key stays on the server: this is addressed by connection id, never by
  // posting a base URL and key from the browser.
  listConnectionModels: (id: string) => request<ModelList>(`/connections/${id}/models`),

  listPrograms: () => request<ProgramSummary[]>('/programs'),
  createProgram: (title = '') =>
    request<ProgramDetail>('/programs', { method: 'POST', body: JSON.stringify({ title }) }),
  getProgram: (id: string) => request<ProgramDetail>(`/programs/${id}`),
  renameProgram: (id: string, title: string) =>
    request<ProgramSummary>(`/programs/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteProgram: (id: string) => request<void>(`/programs/${id}`, { method: 'DELETE' }),

  listMessages: (id: string) => request<Message[]>(`/programs/${id}/messages`),
  sendMessage: (id: string, content: string) =>
    request<PlanTurn>(`/programs/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),

  putBrief: (id: string, brief: Brief) =>
    request<BriefResponse>(`/programs/${id}/brief`, {
      method: 'PUT',
      body: JSON.stringify({ brief }),
    }),
  commitBrief: (id: string) =>
    request<BriefResponse>(`/programs/${id}/brief/commit`, { method: 'POST' }),
  importBrief: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<BriefResponse>(`/programs/${id}/brief/import`, { method: 'POST', body: form })
  },

  startRun: (id: string) =>
    request<{ run_id: string; status: string }>(`/programs/${id}/runs`, { method: 'POST' }),
  getRun: (runId: string) => request<RunDetail>(`/runs/${runId}`),
  cancelRun: (runId: string) => request<{ status: string }>(`/runs/${runId}/cancel`, { method: 'POST' }),

  getGraph: (runId: string, view: 'light' | 'full' = 'light') =>
    request<AlignmentGraphPayload>(`/runs/${runId}/graph?view=${view}`),
  getNode: (runId: string, nodeId: string) =>
    request<GraphNode>(`/runs/${runId}/nodes/${encodeURIComponent(nodeId)}`),
  getArtifact: (runId: string, name: string) =>
    request<unknown>(`/runs/${runId}/artifacts/${name}`),

  eventsUrl: (runId: string, after = 0) => `${BASE}/runs/${runId}/events?after=${after}`,

  getViolations: (runId: string) => request<Finding[]>(`/runs/${runId}/violations`),

  getContexts: (runId: string) => request<AgentContext[]>(`/runs/${runId}/contexts`),

  /** ONE context, whole. The live stream carries the rows without their
   *  transcripts or tool schemas — those are the large half and a context is
   *  republished after every turn — so opening a row is where they are
   *  fetched, and re-fetched as it grows. */
  getContext: (runId: string, contextId: string) =>
    request<AgentContext[]>(`/runs/${runId}/contexts?context=${encodeURIComponent(contextId)}`)
      .then((rows) => rows[0] ?? null),

  /** One agent's transcript, or the whole run's, as readable Markdown.
   *  JSON for tooling is already at `getContexts`; this is the artifact a
   *  person reads end to end. */
  transcriptExportUrl: (runId: string, contextId?: string) =>
    `${BASE}/runs/${runId}/transcript/export`
    + (contextId === undefined ? '' : `?context=${encodeURIComponent(contextId)}`),

  /** The trajectory as one file. A plain URL, not a `request()` call: the
   *  server sets the filename in Content-Disposition, and fetching the JSON
   *  into memory only to re-serialize it here would drop that and re-encode a
   *  file that is already exactly what should land on disk. */
  trajectoryExportUrl: (runId: string) => `${BASE}/runs/${runId}/trajectory/export`,

  /** The violation ledger as CSV, one row per finding. CSV because
   *  `getViolations` already serves the JSON a tool would want, and the ledger
   *  is a table: what is still open, why, who owns it, which check said so. */
  violationsExportUrl: (runId: string) => `${BASE}/runs/${runId}/violations/export`,
}
