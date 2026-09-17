import { useCallback, useEffect, useState } from 'react'
import { CircleAlert, CircleCheck, Plus, RefreshCw, Trash2, X } from 'lucide-react'
import { api } from '../api/client'
import type { LLMConnection, LLMConnections } from '../api/types'

interface Props {
  onClose: () => void
  onSaved: () => void
}

/** Presets for the endpoints this is actually pointed at, so the common cases
 *  are one click rather than three fields typed from memory. */
const PRESETS = [
  {
    label: 'Ollama (local)',
    base_url: 'http://localhost:11434/v1',
    api_key: 'ollama',
    hint: 'Any non-empty key; Ollama ignores it.',
  },
  {
    label: 'vLLM / self-hosted',
    base_url: 'http://localhost:8000/v1',
    api_key: 'not-needed',
    hint: 'The base URL of your served model, ending in /v1.',
  },
  {
    label: 'OpenRouter',
    base_url: 'https://openrouter.ai/api/v1',
    api_key: '',
    hint: 'Needs a real API key.',
  },
  {
    label: 'OpenAI',
    base_url: 'https://api.openai.com/v1',
    api_key: '',
    hint: 'Needs a real API key.',
  },
]

interface FormState {
  name: string
  base_url: string
  api_key: string
  model_name: string
  temperature: string
  max_tokens: string
  context_window: string
}

const BLANK: FormState = {
  name: '',
  base_url: '',
  api_key: '',
  model_name: '',
  temperature: '',
  max_tokens: '',
  context_window: '',
}

const formOf = (connection: LLMConnection): FormState => ({
  name: connection.name,
  base_url: connection.base_url,
  api_key: '',
  model_name: connection.model_name,
  temperature: connection.temperature === null ? '' : String(connection.temperature),
  max_tokens: connection.max_tokens === null ? '' : String(connection.max_tokens),
  context_window: connection.context_window === null ? '' : String(connection.context_window),
})

/** Connections to OpenAI-compatible endpoints, one of them active.
 *
 *  A model is picked from the endpoint's own /models list rather than typed, so
 *  the id is one the endpoint actually serves. That list needs the credentials,
 *  which never leave the server — hence the connection is saved first and the
 *  list is fetched by its id.
 */
export function ModelSettings({ onClose, onSaved }: Props) {
  const [connections, setConnections] = useState<LLMConnection[]>([])
  const [activeId, setActiveId] = useState('')
  // null = the unsaved "new connection" draft.
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(BLANK)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [models, setModels] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  // Typing the id instead of picking it. Not every OpenAI-compatible endpoint
  // answers /models — some gateways route by name without one, some sit behind
  // a proxy that blocks it — and there the dropdown is a dead end. Set
  // automatically when the list comes back unusable, and freely by hand.
  const [manual, setManual] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [hint, setHint] = useState('')

  const selected = connections.find((c) => c.id === selectedId) ?? null
  const isNew = selectedId === null

  /** Adopt a server response: the list is authoritative, including which row is active. */
  const adopt = useCallback((payload: LLMConnections, focus?: string) => {
    setConnections(payload.connections)
    setActiveId(payload.active_id)
    const next =
      focus ??
      (payload.connections.some((c) => c.id === payload.active_id)
        ? payload.active_id
        : payload.connections[0]?.id)
    if (next) {
      const row = payload.connections.find((c) => c.id === next)
      if (row) {
        setSelectedId(row.id)
        setForm(formOf(row))
        return row.id
      }
    }
    setSelectedId(null)
    setForm(BLANK)
    return null
  }, [])

  useEffect(() => {
    api
      .listConnections()
      .then((payload) => {
        const focused = adopt(payload)
        if (payload.error) setResult({ ok: false, message: payload.error })
        return focused
      })
      .catch((exc) => setResult({ ok: false, message: String(exc.message ?? exc) }))
      .finally(() => setLoading(false))
  }, [adopt])

  /** The endpoint's model list. Only a saved connection has one — the server
   *  reads the key from the row, so there is nothing to ask before it exists. */
  const loadModels = useCallback(async (id: string, announce: boolean) => {
    setLoadingModels(true)
    try {
      const payload = await api.listConnectionModels(id)
      setModels(payload.models)
      if (payload.models.length === 0) setManual(true)
      // Only an explicit reload switches back: an automatic one must not pull
      // someone out of a field they deliberately chose to type in.
      else if (announce) setManual(false)
      if (payload.error) setResult({ ok: false, message: payload.error })
      else if (announce)
        setResult({ ok: true, message: `${payload.models.length} models available.` })
    } catch (exc) {
      setModels([])
      setManual(true)
      setResult({ ok: false, message: String((exc as Error).message) })
    } finally {
      setLoadingModels(false)
    }
  }, [])

  useEffect(() => {
    setModels([])
    if (selectedId) void loadModels(selectedId, false)
  }, [selectedId, loadModels])

  const select = (id: string | null) => {
    setResult(null)
    setHint('')
    // A draft has nothing to list yet, so it starts typed — that way a model
    // can be named before the first save rather than only after it.
    setManual(id === null)
    setSelectedId(id)
    const row = id === null ? null : connections.find((c) => c.id === id)
    setForm(row ? formOf(row) : BLANK)
  }

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    setForm((f) => ({
      ...f,
      name: f.name || preset.label,
      base_url: preset.base_url,
      api_key: preset.api_key || f.api_key,
    }))
    setHint(preset.hint)
  }

  const payload = () => ({
    name: form.name.trim(),
    base_url: form.base_url.trim(),
    // Left out entirely when untouched, which the server reads as "keep the
    // stored key" — it never sent us the key to echo back.
    ...(form.api_key === '' ? {} : { api_key: form.api_key }),
    model_name: form.model_name.trim(),
    // A blank field is sent as null, which clears it: the server writes every
    // field it is given, and only an absent api_key means "keep".
    temperature: form.temperature === '' ? null : Number(form.temperature),
    max_tokens: form.max_tokens === '' ? null : Number(form.max_tokens),
    context_window: form.context_window === '' ? null : Number(form.context_window),
  })

  /** Run a mutation and adopt its response, which is the whole list back.
   *
   *  `focus` picks the row to land on from that response, because the row to
   *  show afterwards is not always the one that was open: a create has no id
   *  yet and a delete has just removed one.
   */
  const mutate = async (
    call: () => Promise<LLMConnections>,
    focus: (next: LLMConnections) => string | undefined,
    message: string,
  ) => {
    const before = selectedId
    setSaving(true)
    setResult(null)
    try {
      const next = await call()
      const landed = adopt(next, focus(next))
      setForm((f) => ({ ...f, api_key: '' }))
      setResult(next.error ? { ok: false, message: next.error } : { ok: true, message })
      // Landing on a different row re-runs the models effect; staying on the
      // same one does not, and an edited base URL or key means a new list.
      if (landed && landed === before) void loadModels(landed, false)
      onSaved()
    } catch (exc) {
      setResult({ ok: false, message: String((exc as Error).message) })
    } finally {
      setSaving(false)
    }
  }

  const save = () => {
    if (!isNew) {
      return mutate(() => api.updateConnection(selectedId, payload()), () => selectedId, 'Saved.')
    }
    // The server mints the id, so the new row is the one that was not there before.
    const known = new Set(connections.map((c) => c.id))
    return mutate(
      () => api.createConnection(payload()),
      (next) => next.connections.find((c) => !known.has(c.id))?.id,
      'Connection added.',
    )
  }

  const remove = () => {
    if (isNew) return
    const label = selected?.name || 'this connection'
    if (!window.confirm(`Delete "${label}"? This cannot be undone.`)) return
    return mutate(() => api.deleteConnection(selectedId), () => undefined, 'Connection removed.')
  }

  const activate = () => {
    if (isNew) return
    return mutate(
      () => api.activateConnection(selectedId),
      () => selectedId,
      'Active connection changed.',
    )
  }

  // The stored model stays selectable even when the endpoint will not list its
  // models, so a working configuration is not lost to a temporary outage.
  const options = form.model_name && !models.includes(form.model_name)
    ? [form.model_name, ...models]
    : models

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <span>Model settings</span>
          <button className="btn small btn-icon" onClick={onClose} title="Close" aria-label="Close">
            <X size={15} />
          </button>
        </div>

        {loading ? (
          <div className="modal-body muted small">Loading…</div>
        ) : (
          <div className="conn-layout">
            <div className="conn-list scroll">
              {connections.map((connection) => (
                <button
                  key={connection.id}
                  className={[
                    'conn-item',
                    connection.id === selectedId ? 'selected' : '',
                    connection.id === activeId ? 'active' : '',
                  ].filter(Boolean).join(' ')}
                  onClick={() => select(connection.id)}
                >
                  <span className="conn-name">{connection.name || 'Unnamed'}</span>
                  <span className="conn-sub">
                    {connection.model_name || 'no model picked'}
                  </span>
                  {connection.id === activeId && <span className="conn-badge">Active</span>}
                </button>
              ))}
              <button
                className={`conn-item add${isNew ? ' selected' : ''}`}
                onClick={() => select(null)}
              >
                <Plus size={14} /> Add connection
              </button>
            </div>

            <div className="scroll modal-body conn-form">
              {/* One label per input and nothing else: four section headings
                  over six fields read as more structure than there is. */}
              <div className="preset-row">
                <span className="small muted">Start from</span>
                {PRESETS.map((preset) => (
                  <button key={preset.label} className="btn small" onClick={() => applyPreset(preset)}>
                    {preset.label}
                  </button>
                ))}
              </div>
              {hint && <div className="small muted" style={{ marginTop: 6 }}>{hint}</div>}

              <label className="field">
                <span>Name</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Local Ollama, RunPod 4B…"
                  autoFocus
                />
              </label>

              <label className="field">
                <span>Base URL</span>
                <input
                  value={form.base_url}
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                  placeholder="http://localhost:11434/v1"
                />
              </label>

              <label className="field">
                <span>API key <em className="muted">stored in clear text, locally</em></span>
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  placeholder={
                    selected?.has_api_key
                      ? '•••••••• (stored — leave blank to keep)'
                      : 'Required by most endpoints'
                  }
                />
              </label>

              <label className="field">
                <span>
                  Model
                  {/* Only says anything when there is something to say: where
                      the list comes from is the Base URL directly above. */}
                  {loadingModels && <em className="muted">loading…</em>}
                  {!loadingModels && !isNew && models.length === 0 && (
                    <em className="muted">this endpoint listed none</em>
                  )}
                  <button type="button" className="field-toggle"
                          onClick={() => setManual((value) => !value)}
                          disabled={manual && models.length === 0}>
                    {manual ? 'Pick from the list' : 'Type it in'}
                  </button>
                </span>
                <div className="field-row">
                  {manual ? (
                    <input
                      value={form.model_name}
                      onChange={(e) => setForm({ ...form, model_name: e.target.value })}
                      placeholder="qwen3.5:2b, Qwen/Qwen3.5-4B…"
                    />
                  ) : (
                    <select
                      value={form.model_name}
                      onChange={(e) => setForm({ ...form, model_name: e.target.value })}
                    >
                      <option value="">Select a model…</option>
                      {options.map((model) => (
                        <option key={model} value={model}>{model}</option>
                      ))}
                    </select>
                  )}
                  <button
                    className="btn small btn-icon"
                    disabled={isNew || loadingModels}
                    onClick={() => selectedId && void loadModels(selectedId, true)}
                    title={isNew ? 'Save the connection to read its models'
                                 : 'Reload the model list'}
                    aria-label="Reload the model list"
                  >
                    <RefreshCw size={14} />
                  </button>
                </div>
              </label>

              <div className="field-row">
                <label className="field">
                  <span>Temperature</span>
                  <input
                    type="number" step="0.1" min="0" max="2"
                    value={form.temperature}
                    onChange={(e) => setForm({ ...form, temperature: e.target.value })}
                    placeholder="0.0"
                  />
                </label>
                <label className="field">
                  {/* "Max tokens" alone reads as the total budget, which is the
                      field next to it. Naming the half it caps is the fix. */}
                  <span>Max output tokens</span>
                  <input
                    type="number" min="1"
                    value={form.max_tokens}
                    onChange={(e) => setForm({ ...form, max_tokens: e.target.value })}
                    placeholder="4096"
                  />
                </label>
                <label className="field">
                  <span>Context window</span>
                  <input
                    type="number" min="256"
                    value={form.context_window}
                    onChange={(e) => setForm({ ...form, context_window: e.target.value })}
                    placeholder="e.g. 16384"
                  />
                </label>
              </div>
              <div className="small muted" style={{ marginTop: -4 }}>
                The window is everything the endpoint serves, prompt and reply
                together; the output cap is the reply's share of it, and the
                transcript is trimmed to leave that much room. Leave the window
                blank and the harness falls back to a fixed budget unrelated to
                this model.
              </div>

              {result && (
                <div className={`probe ${result.ok ? 'ok' : 'bad'}`}>
                  {result.ok ? <CircleCheck size={14} /> : <CircleAlert size={14} />}
                  <span>{result.message}</span>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="modal-actions">
          {!isNew && (
            <>
              <button className="btn small btn-icon" onClick={() => void remove()} disabled={saving}
                title="Delete this connection" aria-label="Delete this connection">
                <Trash2 size={14} />
              </button>
              {selectedId !== activeId && (
                <button className="btn small" onClick={() => void activate()} disabled={saving}>
                  Set as active
                </button>
              )}
            </>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <button className="btn" onClick={onClose}>Close</button>
            <button
              className="btn primary"
              onClick={() => void save()}
              disabled={saving || !form.name.trim()}
            >
              {saving ? 'Saving…' : isNew ? 'Add and check' : 'Save and check'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
