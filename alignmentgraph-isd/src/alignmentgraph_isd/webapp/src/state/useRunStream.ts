import { useEffect, useReducer, useRef } from 'react'
import { api } from '../api/client'
import type { AgentContextRow, AlignmentGraphPayload, DeepAction, Finding, HelloPayload, RunEvent, RunStats, RunStatus } from '../api/types'

/**
 * Following one run over server-sent events.
 *
 * Two details carry most of the weight:
 *
 *  - **Position is tracked by `seq`, not by arrival.** The server assigns it
 *    from a single thread, so it is the true causal order; the timestamps on
 *    the underlying trace are written in bursts and are not reliably monotonic
 *    across streams. On reconnect the cursor is what makes the resume gapless.
 *  - **The stream must be closed by us on a terminal event.** `EventSource`
 *    reconnects on any close it did not initiate, so a finished run would
 *    otherwise be re-fetched forever.
 */

export interface RunStreamState {
  runId: string | null
  status: RunStatus | 'idle'
  error: string
  modelName: string
  stats: RunStats
  /** The deep trajectory, accumulated as it streams. */
  actions: DeepAction[]
  lastSeq: number
  graph: AlignmentGraphPayload | null
  graphRev: number
  /** Context ROWS without their transcripts — the live list. The
   *  transcript is fetched per row, so watching a run costs one small
   *  frame per turn instead of every transcript re-sent. */
  contextRows: AgentContextRow[]
  /** The run's ledger. Arrives once, at the end: a finding's outcome is
   *  not known until the last look has settled it. */
  findings: Finding[]
  phase: { name: string; index: number; total: number } | null
  /** Set while a model call is in flight, so the UI can run an elapsed timer
   *  through the tens of seconds when nothing else happens. */
  llmStartedAt: number | null
  connected: boolean
  replay: boolean
}

const EMPTY: RunStreamState = {
  runId: null,
  status: 'idle',
  error: '',
  modelName: '',
  stats: {},
  actions: [],
  lastSeq: 0,
  graph: null,
  graphRev: 0,
  contextRows: [],
  findings: [],
  phase: null,
  llmStartedAt: null,
  connected: false,
  replay: false,
}

type Action =
  | { type: 'reset'; runId: string | null }
  | { type: 'hello'; payload: HelloPayload }
  | { type: 'event'; event: RunEvent }
  | { type: 'graph'; graph: AlignmentGraphPayload }
  | { type: 'contexts'; rows: AgentContextRow[] }
  | { type: 'violations'; findings: Finding[] }
  | { type: 'connected'; value: boolean }

function reducer(state: RunStreamState, action: Action): RunStreamState {
  switch (action.type) {
    case 'reset':
      return { ...EMPTY, runId: action.runId }

    case 'hello':
      return {
        ...state,
        runId: action.payload.run_id,
        status: action.payload.status,
        error: action.payload.error ?? '',
        modelName: action.payload.model_name ?? '',
        stats: action.payload.stats ?? {},
        replay: Boolean(action.payload.replay),
        connected: true,
      }

    case 'connected':
      return { ...state, connected: action.value }

    case 'graph':
      return { ...state, graph: action.graph, graphRev: state.graphRev + 1 }
    case 'contexts':
      return { ...state, contextRows: action.rows }
    case 'violations':
      return { ...state, findings: action.findings }

    case 'event': {
      const { event } = action
      // The server never resends, but a reconnect racing an in-flight frame
      // could; ignoring anything at or behind the cursor makes that harmless.
      if (event.seq <= state.lastSeq) return state

      const next: RunStreamState = {
        ...state,
        lastSeq: event.seq,
      }

      // The deep trajectory travels inside the event envelope; unwrap it into
      // its own list so the detailed view does not have to filter the whole
      // stream on every render.
      if (event.kind === 'action') {
        return { ...next, actions: [...state.actions, event.payload as DeepAction] }
      }

      switch (event.kind) {
        case 'phase_started':
          return {
            ...next,
            phase: {
              name: String(event.payload.phase ?? ''),
              index: Number(event.payload.index ?? 0),
              total: Number(event.payload.total ?? 0),
            },
          }
        case 'llm_started':
          return { ...next, llmStartedAt: Date.now() }
        case 'llm_finished':
          return { ...next, llmStartedAt: null }
        // Accepted, but not over: the harness stops at its next event, so the
        // run keeps going for the rest of any in-flight model call.
        case 'run_cancelling':
          return { ...next, status: 'cancelling' }
        case 'run_finished':
        case 'run_failed':
        case 'run_cancelled':
          return {
            ...next,
            status: (event.payload.status as RunStatus) ?? 'succeeded',
            error: String(event.payload.error ?? ''),
            stats: (event.payload.stats as RunStats) ?? next.stats,
            phase: null,
            llmStartedAt: null,
          }
        default:
          return next
      }
    }
  }
}

export function useRunStream(runId: string | null): RunStreamState {
  const [state, dispatch] = useReducer(reducer, EMPTY)
  // Read inside the effect without making it a dependency: re-subscribing on
  // every event would tear the stream down and rebuild it constantly.
  const cursor = useRef(0)
  cursor.current = state.lastSeq

  useEffect(() => {
    dispatch({ type: 'reset', runId })
    cursor.current = 0
    if (!runId) return

    const source = new EventSource(api.eventsUrl(runId, 0))
    let closed = false

    const close = () => {
      if (!closed) {
        closed = true
        source.close()
        dispatch({ type: 'connected', value: false })
      }
    }

    source.addEventListener('hello', (message) => {
      const payload = JSON.parse((message as MessageEvent).data) as HelloPayload
      dispatch({ type: 'hello', payload })
      // Do NOT close here even for an already-terminal replay: `hello` is
      // only the first SSE frame, and the hundreds of events that follow it
      // in the same response have not necessarily been received yet — SSE
      // delivers messages as the browser parses them, not all at once when
      // the response completes. Closing on `hello` raced that delivery and
      // truncated the replay at an arbitrary point (2026-08-27 bug: the same
      // finished run showed a different action count on every reload).
      // `onEvent` below closes once the real terminal event arrives, by
      // which point everything before it is guaranteed already dispatched.
    })

    source.addEventListener('violations', (message) => {
      dispatch({ type: 'violations', findings: JSON.parse((message as MessageEvent).data) })
    })

    source.addEventListener('contexts', (message) => {
      dispatch({ type: 'contexts', rows: JSON.parse((message as MessageEvent).data) })
    })

    source.addEventListener('graph', (message) => {
      dispatch({ type: 'graph', graph: JSON.parse((message as MessageEvent).data) })
    })

    const onEvent = (message: MessageEvent) => {
      const event = JSON.parse(message.data) as RunEvent
      dispatch({ type: 'event', event })
      if (event.kind === 'run_finished' || event.kind === 'run_failed' || event.kind === 'run_cancelled') {
        // Terminal: close from this side or the browser reconnects forever.
        setTimeout(close, 0)
      }
    }

    const kinds = [
      'run_started', 'phase_started', 'phase_finished', 'llm_started', 'llm_finished',
      'action',
      'agent_step', 'node_edit', 'llm_call', 'validation_event', 'check_event',
      'repair_event', 'retrieval_event', 'run_cancelling',
      'run_finished', 'run_failed', 'run_cancelled',
    ]
    for (const kind of kinds) source.addEventListener(kind, onEvent as EventListener)

    source.onerror = () => {
      dispatch({ type: 'connected', value: false })
      // EventSource retries on its own and resends Last-Event-ID, so the
      // server picks up exactly where this connection left off.
    }

    return close
  }, [runId])

  return state
}
