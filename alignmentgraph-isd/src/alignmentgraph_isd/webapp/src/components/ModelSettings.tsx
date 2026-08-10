import { useEffect, useState } from 'react'
import { CircleAlert, CircleCheck, X } from 'lucide-react'
import { api } from '../api/client'
import type { LLMSettings } from '../api/types'

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
    api_spec: 'openai_compatible',
    api_key: 'ollama',
    hint: 'Any non-empty key; Ollama ignores it.',
  },
  {
    label: 'vLLM / self-hosted',
    base_url: 'http://localhost:8000/v1',
    api_spec: 'openai_compatible',
    api_key: 'not-needed',
    hint: 'The base URL of your served model, ending in /v1.',
  },
  {
    label: 'OpenRouter',
    base_url: 'https://openrouter.ai/api/v1',
    api_spec: 'openai_compatible',
    api_key: '',
    hint: 'Needs a real API key.',
  },
  {
    label: 'Anthropic',
    base_url: '',
    api_spec: 'anthropic',
    api_key: '',
    hint: 'Needs a real API key.',
  },
]

export function ModelSettings({ onClose, onSaved }: Props) {
  const [form, setForm] = useState({
    model_name: '',
    api_spec: 'openai_compatible',
    base_url: '',
    api_key: '',
    temperature: '' as string,
    max_tokens: '' as string,
  })
  const [current, setCurrent] = useState<LLMSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [hint, setHint] = useState('')

  useEffect(() => {
    api.getLLMSettings()
      .then((value) => {
        setCurrent(value)
        setForm({
          model_name: value.model_name,
          api_spec: value.api_spec || 'openai_compatible',
          base_url: value.base_url,
          api_key: '',
          temperature: value.temperature === null ? '' : String(value.temperature),
          max_tokens: value.max_tokens === null ? '' : String(value.max_tokens),
        })
      })
      .catch((exc) => setResult({ ok: false, message: String(exc.message ?? exc) }))
      .finally(() => setLoading(false))
  }, [])

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    setForm((f) => ({
      ...f,
      base_url: preset.base_url,
      api_spec: preset.api_spec,
      api_key: preset.api_key || f.api_key,
    }))
    setHint(preset.hint)
  }

  const save = async () => {
    setSaving(true)
    setResult(null)
    try {
      const saved = await api.putLLMSettings({
        model_name: form.model_name.trim(),
        api_spec: form.api_spec,
        base_url: form.base_url.trim(),
        // Left out entirely when untouched, which the server reads as "keep the
        // stored key" — it never sent us the key to echo back.
        ...(form.api_key === '' ? {} : { api_key: form.api_key }),
        temperature: form.temperature === '' ? null : Number(form.temperature),
        max_tokens: form.max_tokens === '' ? null : Number(form.max_tokens),
      })
      setCurrent(saved)
      setForm((f) => ({ ...f, api_key: '' }))
      setResult(
        saved.error
          ? { ok: false, message: saved.error }
          : { ok: true, message: `${saved.model_name} is ready.` },
      )
      onSaved()
    } catch (exc) {
      setResult({ ok: false, message: String((exc as Error).message) })
    } finally {
      setSaving(false)
    }
  }

  const reset = async () => {
    setSaving(true)
    setResult(null)
    try {
      const cleared = await api.deleteLLMSettings()
      setCurrent(cleared)
      setForm({
        model_name: cleared.model_name,
        api_spec: cleared.api_spec || 'openai_compatible',
        base_url: cleared.base_url,
        api_key: '',
        temperature: '',
        max_tokens: '',
      })
      setResult({ ok: !cleared.error, message: cleared.error || 'Using the environment settings.' })
      onSaved()
    } catch (exc) {
      setResult({ ok: false, message: String((exc as Error).message) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <span>Model settings</span>
          <button className="btn small btn-icon" onClick={onClose} title="Close" aria-label="Close">
            <X size={15} />
          </button>
        </div>

        <div className="scroll modal-body">
          {loading ? (
            <div className="muted small">Loading…</div>
          ) : (
            <>
              {current && (
                <div className="small muted" style={{ marginBottom: 12 }}>
                  {current.source === 'database' && 'Configured here, in the app.'}
                  {current.source === 'environment' && (
                    <>Currently coming from <code>AGENT_MODEL_*</code> in the environment. Saving below overrides it.</>
                  )}
                  {current.source === 'none' && 'No model configured yet.'}
                </div>
              )}

              <div className="section-title">Quick setup</div>
              <div className="preset-row">
                {PRESETS.map((preset) => (
                  <button key={preset.label} className="btn small" onClick={() => applyPreset(preset)}>
                    {preset.label}
                  </button>
                ))}
              </div>
              {hint && <div className="small muted" style={{ marginTop: 6 }}>{hint}</div>}

              <div className="section-title">Model</div>
              <label className="field">
                <span>Model name</span>
                <input
                  value={form.model_name}
                  onChange={(e) => setForm({ ...form, model_name: e.target.value })}
                  placeholder="qwen3.5:2b, Qwen/Qwen3.5-4B, claude-sonnet-4-5…"
                  autoFocus
                />
              </label>

              <label className="field">
                <span>API type</span>
                <select
                  value={form.api_spec}
                  onChange={(e) => setForm({ ...form, api_spec: e.target.value })}
                >
                  <option value="openai_compatible">OpenAI-compatible (Ollama, vLLM, OpenRouter…)</option>
                  <option value="anthropic">Anthropic</option>
                </select>
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
                <span>API key</span>
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  placeholder={current?.has_api_key ? '•••••••• (stored — leave blank to keep)' : 'Required by most endpoints'}
                />
              </label>
              <div className="small muted" style={{ marginTop: -4, marginBottom: 10 }}>
                Stored in clear text in this app's local database. Use a
                throwaway key if that matters to you.
              </div>

              <div className="section-title">Optional</div>
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
                  <span>Max tokens</span>
                  <input
                    type="number" min="1"
                    value={form.max_tokens}
                    onChange={(e) => setForm({ ...form, max_tokens: e.target.value })}
                    placeholder="4096"
                  />
                </label>
              </div>

              {result && (
                <div className={`probe ${result.ok ? 'ok' : 'bad'}`}>
                  {result.ok ? <CircleCheck size={14} /> : <CircleAlert size={14} />}
                  <span>{result.message}</span>
                </div>
              )}
            </>
          )}
        </div>

        <div className="modal-actions">
          {current?.source === 'database' && (
            <button className="btn small" onClick={() => void reset()} disabled={saving}>
              Forget and use the environment
            </button>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <button className="btn" onClick={onClose}>Cancel</button>
            <button
              className="btn primary"
              onClick={() => void save()}
              disabled={saving || !form.model_name.trim()}
            >
              {saving ? 'Checking…' : 'Save and check'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
