import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Download, Wrench } from 'lucide-react'
import { api } from '../api/client'
import { agentHue, agentShortName, phaseLabel } from '../lib/phaseTimeline'
import type { AgentContext, AgentContextRow, ContextMessage } from '../api/types'

interface Props {
  /** Transcripts, fetched whole. Complete but behind: refetched at a phase
   *  boundary and when the run ends, because each carries every message. */
  contexts: AgentContext[]
  /** The same contexts WITHOUT their transcripts, arriving live on the stream
   *  after every turn. These lead — a row appears the moment its agent starts
   *  — and the transcript catches up. */
  rows: AgentContextRow[]
  /** Null before the first run of this program. */
  runId: string | null
}

/** One entry per context: the live head, and the transcript if it has arrived.
 *
 *  The live rows lead so the list is honest about what is happening now; the
 *  transcript is whatever the last fetch brought, and the row's own turn count
 *  says how far ahead the agent has moved since. A body shorter than that
 *  count reads as stale rather than passing for current. */
function merge(rows: AgentContextRow[], contexts: AgentContext[]) {
  const fetched = new Map(contexts.map((context) => [context.id, context]))
  if (rows.length === 0) {
    return contexts.map((context) => ({ head: context as AgentContextRow, body: context }))
  }
  return rows.map((row) => ({ head: row, body: fetched.get(row.id) ?? null }))
}

/**
 * What each agent was SHOWN — the other half of the run.
 *
 * The Trajectory tab answers "what did the agents DO". This answers "what were
 * they looking at when they did it", which is the first question about any
 * output that surprises you and the one nothing recorded until now: `autonomy`
 * carried `context_len`, a number, while the transcript itself lived only in
 * the loop's memory and was gone when the run ended.
 *
 * A LIST, one row per agent, because the comparison that matters is down the
 * column: how much context each one carried, and where it went. The multi arm
 * fills it with one row per stage plus one per Developer work set; the single
 * arm with exactly one row holding every stage. That contrast is the
 * decomposition axis as a shape rather than a number in a table.
 */
export function ContextGrid({ contexts, rows, runId }: Props) {
  const [openId, setOpenId] = useState<string | null>(null)
  const entries = useMemo(() => merge(rows, contexts), [rows, contexts])

  if (entries.length === 0) {
    return (
      <div className="empty">
        Each agent's context appears here as it starts, and grows as it works —
        its system prompt, the transcript it is accumulating, and the tools it
        was given.
      </div>
    )
  }

  return (
    <div className="scroll">
      <div className="ctx-toolbar">
        <span className="muted small">
          {entries.length} agent context{entries.length === 1 ? '' : 's'}
        </span>
        {runId && (
          <a
            className="btn small icon-label"
            href={api.transcriptExportUrl(runId)}
            download
            title="Download every agent's transcript as Markdown — system turn, every message in order, and the tool schemas"
          >
            <Download size={12} />
            Export all transcripts
          </a>
        )}
      </div>
      <div className="ctx-list">
        {entries.map(({ head, body }) => {
          const id = head.id
          return (
            <ContextRow
              key={id}
              head={head}
              body={body}
              runId={runId}
              open={openId === id}
              onToggle={() => setOpenId(openId === id ? null : id)}
            />
          )
        })}
      </div>
    </div>
  )
}

function ContextRow({
  head, body, runId, open, onToggle,
}: {
  head: AgentContextRow
  /** Null until the transcript has been fetched — the row is live before that. */
  body: AgentContext | null
  runId: string | null
  open: boolean
  onToggle: () => void
}) {
  const context = head
  const hue = agentHue(context.agent)
  // The OPEN row is the live one: its transcript and tool schemas are fetched
  // when it opens and re-fetched as it grows, which is cheap because it is one
  // row. A closed row costs nothing but its head, which the stream already
  // carries.
  const [fetched, setFetched] = useState<AgentContext | null>(null)
  useEffect(() => {
    if (!open || !runId) return
    let cancelled = false
    api.getContext(runId, head.id)
      .then((full) => { if (!cancelled && full) setFetched(full) })
      .catch(() => { /* the run may have ended between the frame and the fetch */ })
    return () => { cancelled = true }
  }, [open, runId, head.id, head.turns])

  const shown = fetched ?? body
  const { system, turns } = useMemo(() => split(shown?.messages ?? []), [shown?.messages])
  const liveTurns = head.turns ?? turns.length
  // A Developer's label is `stage:SET-ID`; the set is what distinguishes it
  // from the others its stage dispatched.
  const [stage, setId] = context.label.split(':')

  return (
    <div className={`ctx-row${open ? ' open' : ''}`}>
      <button className="ctx-head" onClick={onToggle}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span className="pt-pill" style={{ background: hue.bg, color: hue.fg }}>
          {agentShortName(context.agent)}
        </span>
        <span className="ctx-title">
          {setId ? <>{phaseLabel(stage)} <span className="mono small">{setId}</span></> : phaseLabel(stage)}
        </span>
        <span className="muted small ctx-meta">
          {fmt(usedOf(context))} {hasTokens(context) ? 'tok' : 'chars'} · {liveTurns} turn
          {liveTurns === 1 ? '' : 's'}
        </span>
      </button>

      {open && (
        <div className="ctx-body">
          {runId && (
            <div className="ctx-row-actions">
              {/* The AGENT RUN id, not a position and not the label: a stage
                  that was regenerated publishes one context per attempt and
                  they share a label, while a position is only stable once the
                  run is over. */}
              <a
                className="btn small icon-label"
                href={api.transcriptExportUrl(runId, head.id)}
                download
                title="Download this agent's transcript as Markdown"
              >
                <Download size={12} />
                Export this transcript
              </a>
            </div>
          )}
          <Budget context={context} />

          <Section
            part="system"
            title="System prompt"
            note="instructions and rules for the model"
          >
            <pre className="ctx-pre">{system}</pre>
          </Section>

          <Section
            part="schemas"
            title="Tool schemas"
            note="what the tools look like — sent every request, but not part of the transcript"
          >
            <div className="ctx-tools">
              {(shown?.tools ?? []).map((tool, i) => (
                <details key={i} className="ctx-tool">
                  <summary>
                    <Wrench size={11} />
                    <span className="mono">{tool.function?.name ?? '?'}</span>
                    <span className="muted small">{tool.function?.description ?? ''}</span>
                  </summary>
                  <pre className="ctx-pre">{JSON.stringify(tool.function?.parameters ?? {}, null, 2)}</pre>
                </details>
              ))}
            </div>
          </Section>

          <Section
            part="messages"
            title="Transcript"
            note={
              (head.compacted ?? 0) > 0
                ? `${turns.length} turns, ${head.compacted} of them compacted out of the live `
                  + 'context to stay under the window'
                : `${turns.length} turns, each block coloured by the part it counts toward`
            }
          >
            <div className="ctx-turns">
              {turns.map((message, i) => <Turn key={i} message={message} index={i} />)}
            </div>
          </Section>
        </div>
      )}
    </div>
  )
}

/** The window, itemised — which part of the context is what. */
function Budget({ context }: { context: AgentContextRow }) {
  const budget = budgetOf(context)
  const used = usedOf(context)
  const parts = breakdown(context)
  return (
    <section className="ctx-budget">
      <div className="ctx-budget-head">
        <span>Context window</span>
        <span className="muted">
          {fmt(used)} / {fmt(budget)} {unit(context)} ({Math.round((used / budget) * 100)}%)
        </span>
      </div>
      <span className="ctx-bar wide">
        {parts.map((part) => (
          <span
            key={part.key}
            className={`ctx-bar-seg seg-${part.key}`}
            style={{ width: `${(part.tokens / budget) * 100}%` }}
          />
        ))}
      </span>
      <ul className="ctx-legend">
        {parts.map((part) => (
          <li key={part.key}>
            <span className={`ctx-dot seg-${part.key}`} />
            <span className="ctx-legend-name">
              {part.name} <span className="muted small">— {part.note}</span>
            </span>
            <span className="muted">{fmt(part.tokens)}</span>
            <span className="muted ctx-legend-pct">
              {((part.tokens / budget) * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
      {context.ratio_measured === false && (
        <p className="muted small ctx-note">
          Token counts are an estimate until the provider reports its first
          prompt size.
        </p>
      )}
    </section>
  )
}

/** A true PARTITION of the whole REQUEST: the four sum to what is sent, so the
 *  bar cannot lie about what filled the window. */
function breakdown(context: AgentContextRow) {
  // Falls back to the character split for a run recorded before token
  // accounting existed, so an old run still renders — under its own unit.
  const t = context.tokens ?? {
    system: 0, messages: Math.max(0, context.chars), tools: 0,
  }
  return [
    {
      key: 'system', name: 'System prompt', tokens: t.system ?? 0,
      note: 'persona, stage order and the design brief',
    },
    {
      key: 'messages', name: 'Messages', tokens: t.messages ?? 0,
      note: 'the conversation itself — user and assistant text',
    },
    {
      key: 'tools', name: 'Tool calls & results', tokens: t.tools ?? 0,
      note: 'names, arguments the model asked for, and the data returned',
    },
    {
      // Not in the message list, but sent on EVERY request and charged to the
      // same window — a bar that left it out understated what the call costs.
      key: 'schemas', name: 'Tool schemas', tokens: context.schema_tokens ?? 0,
      note: 'the bound function signatures the model chooses from',
    },
  ]
}

/** Whether this snapshot carries token accounting at all. A run recorded
 *  before it did has only characters, and showing those under a "tokens" label
 *  is how 24,000 characters read as "24.0k tokens". */
function hasTokens(context: AgentContextRow): boolean {
  return context.total_tokens !== undefined && context.token_budget !== undefined
}

function unit(context: AgentContextRow): string {
  return hasTokens(context) ? 'tokens' : 'chars'
}

function usedOf(context: AgentContextRow): number {
  if (!hasTokens(context)) return context.chars
  // The whole request: the transcript AND the schemas bound alongside it.
  return (context.total_tokens as number) + (context.schema_tokens ?? 0)
}

function budgetOf(context: AgentContextRow): number {
  return hasTokens(context)
    ? (context.token_budget as number)
    : (context.budget ?? usedOf(context))
}

function Section({ part, title, note, children }: {
  part?: string; title: string; note: string; children: React.ReactNode
}) {
  return (
    <section className="ctx-section">
      <h4>
        {/* The dot ties a section to its slice of the bar. "Tool schemas" has
            one too — it is a segment now, not a footnote. */}
        {part && <span className={`ctx-dot seg-${part}`} />}
        {title} <span className="muted small">— {note}</span>
      </h4>
      {children}
    </section>
  )
}

/**
 * One message, as ONE OR TWO blocks — split the way the budget is.
 *
 * An assistant turn that calls a tool contributes to two different parts: its
 * text is Messages, its tool call is Tools. Rendering them as one block under
 * one colour made the transcript disagree with the bar directly above it, and
 * the tool call is usually the larger half — an assistant turn that submits an
 * artifact carries EMPTY content and the whole artifact in its call.
 */
/** A turn compaction has taken OUT of the live context.
 *
 *  Shown, not hidden: the tab answers "what was this agent shown", and a
 *  transcript reduced to what is still being sent answers that for the last
 *  call only. Marked, not merged in: it is no longer part of what the model
 *  sees, and it is not counted in the window meter beside it. */
function Turn({ message, index }: { message: ContextMessage; index: number }) {
  const calls = message.tool_calls ?? []
  const isResult = message.role === 'tool'
  const gone = message.compacted === true
  return (
    <div className={gone ? 'ctx-compacted' : undefined}>
      {gone && (
        <span className="ctx-badge" title="dropped from the live context to stay under the window — the model no longer sees this, and it is not counted in the meter above">
          compacted
        </span>
      )}
      {(message.content || (!calls.length && !isResult)) && (
        <Block
          part={isResult ? 'tools' : 'messages'}
          index={index}
          label={isResult ? `tool result · ${message.name ?? ''}` : message.role}
          body={message.content}
        />
      )}
      {calls.length > 0 && (
        <Block
          part="tools"
          index={index}
          label={`tool call · ${callNames(calls)}`}
          body={JSON.stringify(calls, null, 2)}
        />
      )}
    </div>
  )
}

/** Coloured by the PART it counts toward, using the same three colours as the
 *  bar — that correspondence is the whole point of showing both. */
function Block({ part, index, label, body }: {
  part: 'messages' | 'tools'; index: number; label: string; body: string
}) {
  return (
    <div className={`ctx-turn part-${part}`}>
      <span className="ctx-role mono small">
        <span className={`ctx-dot seg-${part}`} /> {index + 1}. {label}
      </span>
      {body && <pre className="ctx-pre">{body}</pre>}
    </div>
  )
}

function callNames(calls: unknown[]): string {
  return calls
    .map((c) => (c && typeof c === 'object' && 'name' in c ? String((c as { name: unknown }).name) : '?'))
    .join(', ')
}

function split(messages: ContextMessage[]): { system: string; turns: ContextMessage[] } {
  if (messages.length > 0 && messages[0].role === 'system') {
    return { system: messages[0].content, turns: messages.slice(1) }
  }
  return { system: '(no system turn recorded)', turns: messages }
}

function fmt(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value)
}
