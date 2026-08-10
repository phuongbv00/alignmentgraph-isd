import type {
  AlignmentGraphPayload,
  Brief,
  BriefResponse,
  GraphNode,
  Health,
  LLMSettings,
  LLMSettingsInput,
  Message,
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

  getLLMSettings: () => request<LLMSettings>('/settings/llm'),
  putLLMSettings: (settings: LLMSettingsInput) =>
    request<LLMSettings>('/settings/llm', { method: 'PUT', body: JSON.stringify(settings) }),
  deleteLLMSettings: () => request<LLMSettings>('/settings/llm', { method: 'DELETE' }),

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
}
