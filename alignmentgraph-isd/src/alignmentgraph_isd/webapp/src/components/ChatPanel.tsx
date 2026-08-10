import { useEffect, useRef, useState } from 'react'
import { Loader2, Send, TriangleAlert, Upload } from 'lucide-react'
import type { Message } from '../api/types'

interface Props {
  messages: Message[]
  onSend: (content: string) => Promise<void>
  onImport: (file: File) => Promise<void>
  disabled: boolean
  disabledReason: string
  warnings: string[]
}

/**
 * The two ways to get a design brief in: describe it, or import one.
 *
 * Both land in the same place — a `DesignBrief` on the program — so the demo
 * can show either the conversational path or a reproducible scenario file from
 * the benchmark, without the rest of the app knowing which was used.
 */
export function ChatPanel({ messages, onSend, onImport, disabled, disabledReason, warnings }: Props) {
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const logEnd = useRef<HTMLDivElement>(null)
  const composer = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, sending])

  // Grow the box to fit what has been typed, up to the cap in the stylesheet.
  // Describing a program takes a paragraph, and typing it into a one-line slit
  // that scrolls its own start out of view is miserable.
  useEffect(() => {
    const el = composer.current
    if (!el) return
    // Collapsed first because scrollHeight only ever reports the content height
    // of the *current* box, so without this the field could grow but never
    // shrink back when text is deleted.
    el.style.height = 'auto'
    // Measured in every state, empty included: leaving the empty box to the
    // `rows` default and only measuring once text exists makes the field jump
    // by a couple of pixels on the first keystroke.
    el.style.height = `${el.scrollHeight}px`
  }, [draft])

  const send = async () => {
    const content = draft.trim()
    if (!content || sending) return
    setSending(true)
    setError('')
    try {
      await onSend(content)
      setDraft('')
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setSending(false)
    }
  }

  const pickFile = async (file: File | undefined) => {
    if (!file) return
    setError('')
    try {
      await onImport(file)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    }
  }

  return (
    <>
      <div className="scroll">
        <div className="chat-log">
          {messages.length === 0 && (
            <div className="empty">
              Describe the training program you want designed — subject, who it is for, what
              learners should be able to do afterwards.
              <br />
              <br />
              Or import a scenario file to start from a prepared brief.
            </div>
          )}

          {messages.map((message) => (
            <div key={`${message.seq}-${message.role}`} className={`bubble ${message.role}`}>
              {message.content}
              {message.role === 'assistant' && hasPatch(message) && (
                <div className="patch-note">
                  Updated: {Object.keys(message.payload.brief_patch ?? {}).join(', ')}
                </div>
              )}
            </div>
          ))}

          {sending && <div className="bubble assistant thinking">Thinking…</div>}
          <div ref={logEnd} />
        </div>
      </div>

      <div className="composer">
        {warnings.map((warning, index) => (
          <div key={index} className="small muted" style={{ marginBottom: 6 }}>{warning}</div>
        ))}
        {error && (
          <div className="small icon-label" style={{ color: 'var(--bad)', marginBottom: 6 }}>
            <TriangleAlert size={13} /> {error}
          </div>
        )}

        <div className="composer-row">
          <textarea
            ref={composer}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void send()
              }
            }}
            placeholder={disabled ? disabledReason : 'Describe the training program. Enter to send · Shift+Enter for a new line'}
            disabled={disabled || sending}
            rows={3}
          />
          <button
            className="btn btn-icon primary"
            onClick={() => void send()}
            disabled={disabled || sending || !draft.trim()}
          >
            {sending ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
          </button>
        </div>

        <div className="composer-actions">
          <input
            ref={fileInput}
            type="file"
            accept=".json,application/json"
            style={{ display: 'none' }}
            onChange={(event) => {
              void pickFile(event.target.files?.[0])
              event.target.value = ''
            }}
          />
          <button className="btn small icon-label" onClick={() => fileInput.current?.click()}>
            <Upload size={13} /> Import scenario file…
          </button>
          <span className="small muted">
            A benchmark scenario JSON, or any design brief in the same shape.
          </span>
        </div>
      </div>
    </>
  )
}

function hasPatch(message: Message): boolean {
  return Object.keys(message.payload?.brief_patch ?? {}).length > 0
}
