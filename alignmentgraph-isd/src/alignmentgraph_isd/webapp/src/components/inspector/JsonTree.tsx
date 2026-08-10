import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface Props {
  value: unknown
  name?: string
  /** Levels open on first render. Deeper branches start collapsed, because a
   *  section node's payload is an entire ADDIE phase. */
  defaultOpenDepth?: number
  depth?: number
}

export function JsonTree({ value, name, defaultOpenDepth = 1, depth = 0 }: Props) {
  const [open, setOpen] = useState(depth < defaultOpenDepth)

  if (value === null) return <Leaf name={name} className="json-null" text="null" />
  if (typeof value === 'string') return <Leaf name={name} className="json-string" text={`"${value}"`} />
  if (typeof value === 'number') return <Leaf name={name} className="json-number" text={String(value)} />
  if (typeof value === 'boolean') return <Leaf name={name} className="json-boolean" text={String(value)} />

  const isArray = Array.isArray(value)
  const entries = isArray
    ? (value as unknown[]).map((item, index) => [String(index), item] as const)
    : Object.entries(value as Record<string, unknown>)

  if (entries.length === 0) {
    return <Leaf name={name} className="json-null" text={isArray ? '[]' : '{}'} />
  }

  return (
    <li>
      <button className="json-toggle" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        {name && <span className="json-key">{name}</span>}
        {name && ': '}
        <span className="muted">
          {isArray ? `[${entries.length}]` : `{${entries.length}}`}
        </span>
      </button>
      {open && (
        <ul>
          {entries.map(([key, item]) => (
            <JsonTree
              key={key}
              name={key}
              value={item}
              depth={depth + 1}
              defaultOpenDepth={defaultOpenDepth}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

function Leaf({ name, className, text }: { name?: string; className: string; text: string }) {
  return (
    <li>
      {name && (
        <>
          <span className="json-key">{name}</span>
          {': '}
        </>
      )}
      <span className={className}>{text}</span>
    </li>
  )
}

export function JsonRoot({ value, defaultOpenDepth = 1 }: { value: unknown; defaultOpenDepth?: number }) {
  return (
    <div className="json-tree">
      <ul style={{ paddingLeft: 0, borderLeft: 'none' }}>
        <JsonTree value={value} defaultOpenDepth={defaultOpenDepth} />
      </ul>
    </div>
  )
}

/**
 * A string that is probably JSON, shown as a tree.
 *
 * The trajectory records prompts and model output as truncated strings, and
 * most of the output is JSON — as one long line it is unreadable, and the
 * truncation means it often will not parse. So: parse when possible, fall back
 * to text when not, and never let a parse failure hide the content.
 */
export function MaybeJson({ text }: { text: string }) {
  const trimmed = (text ?? '').trim()
  if (!trimmed) return <div className="small muted">(empty)</div>

  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return <JsonRoot value={JSON.parse(trimmed)} defaultOpenDepth={2} />
    } catch {
      // Truncated mid-object, which is the normal case for a summary field.
    }
  }
  return <div className="small mono prewrap">{text}</div>
}

/** A section that can be folded away. Long payloads make the panel unusable
 *  otherwise, but they are the whole point of opening a step. */
export function Collapsible({
  title, children, defaultOpen = true, note,
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
  note?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="collapsible">
      <button className="collapsible-head" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>{title}</span>
        {note && <span className="muted small" style={{ marginLeft: 'auto' }}>{note}</span>}
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  )
}
