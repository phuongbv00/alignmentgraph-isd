import { CircleCheck, Loader2 } from 'lucide-react'
import { BriefCard } from './BriefCard'
import { ChatPanel } from './ChatPanel'
import type { BriefPreview, Message } from '../api/types'

interface Props {
  preview: BriefPreview
  missingFields: string[]
  committedAt: string | null
  messages: Message[]
  onSend: (content: string) => Promise<void>
  onImport: (file: File) => Promise<void>
  onCommit: () => Promise<void>
  onOpenBrief: () => void
  chatDisabled: boolean
  chatDisabledReason: string
  warnings: string[]
  committing: boolean
}

/**
 * Where a design brief comes from, and what it settled on.
 *
 * A brief arrives one of two ways, and they want different treatment. An
 * imported file arrives whole, so it is committed on the spot and shown as the
 * program's brief. One built through the conversation is a draft until the
 * designer says otherwise — it changes with every answer, and showing a
 * half-formed version as *the* brief would be a lie about what the agent is
 * going to be given.
 */
export function BriefTab({
  preview, missingFields, committedAt, messages, onSend, onImport, onCommit,
  onOpenBrief, chatDisabled, chatDisabledReason, warnings, committing,
}: Props) {
  const committed = Boolean(committedAt)
  const hasDraft = preview.is_runnable || preview.learning_goals_total > 0 || Boolean(preview.title)

  return (
    <>
      {committed && (
        <BriefCard
          preview={preview}
          missingFields={missingFields}
          committedAt={committedAt}
          onOpen={onOpenBrief}
        />
      )}

      {!committed && hasDraft && (
        <>
          <BriefCard
            preview={preview}
            missingFields={missingFields}
            draft
            onOpen={onOpenBrief}
          />
          <div className="commit-bar">
            <span className="small muted">
              {preview.is_runnable
                ? 'Commit this to make it the program\'s design brief.'
                : 'Keep going — a title, a domain and a couple of learning goals is enough to commit.'}
            </span>
            <button
              className="btn primary small icon-label"
              onClick={() => void onCommit()}
              disabled={!preview.is_runnable || committing}
            >
              {committing ? <Loader2 size={13} className="spin" /> : <CircleCheck size={13} />}
              {committing ? 'Committing…' : 'Commit brief'}
            </button>
          </div>
        </>
      )}

      <ChatPanel
        messages={messages}
        onSend={onSend}
        onImport={onImport}
        disabled={chatDisabled}
        disabledReason={chatDisabledReason}
        warnings={warnings}
      />
    </>
  )
}
