import { describe, expect, it } from 'vitest'
import {
  agentHue, buildPhaseTimeline, phaseLabel,
  timelineAgents, writesSummary,
} from './phaseTimeline'
import type { DeepAction } from '../api/types'

let tick = 0
function action(name: string, agent: string, phase: string, context: Record<string, unknown> = {}): DeepAction {
  tick += 1
  return {
    timestamp: new Date(2026, 0, 1, 12, 0, 0, tick).toISOString(),
    agent,
    action: name,
    context: { phase, ...context },
  }
}

const ORCH = 'WorkflowOrchestrator'

/** A miniature run: outcome phase → parallel content/rubric fan-out → aggregate. */
function fixture(): DeepAction[] {
  tick = 0
  return [
    action('phase_started', ORCH, 'outcome_designer', { index: 1, total: 4 }),
    action('llm_call', 'OutcomeDesignerAgent', 'outcome_designer', {}),
    action('agent_step', 'OutcomeDesignerAgent', 'outcome_designer', { agent_action: 'design_objectives' }),
    action('node_write', 'OutcomeDesignerAgent', 'outcome_designer', { op: 'add', node_type: 'course_goal' }),
    action('node_write', 'OutcomeDesignerAgent', 'outcome_designer', { op: 'add', node_type: 'objective' }),
    action('node_write', 'OutcomeDesignerAgent', 'outcome_designer', { op: 'add', node_type: 'objective' }),
    action('node_read', 'OutcomeDesignerAgent', 'outcome_designer', { query: 'element_nodes' }),
    action('edge_write', 'OutcomeDesignerAgent', 'outcome_designer', { op: 'add', relation_id: 'C1' }),
    action('check', 'OutcomeDesignerAgent', 'outcome_designer', { round: 1, violation_count: 2 }),
    action('repair', 'OutcomeDesignerAgent', 'outcome_designer', { violation_type: 'bloom' }),
    action('check', 'OutcomeDesignerAgent', 'outcome_designer', { round: 2, violation_count: 0 }),
    action('phase_finished', ORCH, 'outcome_designer', { duration_ms: 42000 }),

    // Fan-out: rubric starts while content is still open, actions interleave.
    action('phase_started', ORCH, 'content_designer', { index: 2, total: 4 }),
    action('phase_started', ORCH, 'rubric_designer', { index: 3, total: 4 }),
    action('llm_call', 'ContentDesignerAgent', 'content_designer', {}),
    action('llm_call', 'RubricDesignerAgent', 'rubric_designer', {}),
    action('node_write', 'RubricDesignerAgent', 'rubric_designer', { op: 'add', node_type: 'rubric' }),
    action('agent_step', 'ContentDesignerAgent', 'content_designer', { agent_action: 'design_content' }),
    action('agent_step', 'RubricDesignerAgent', 'rubric_designer', { agent_action: 'design_rubrics' }),
    action('retry', 'RubricDesignerAgent', 'rubric_designer', { input_summary: 'invalid JSON' }),
    action('phase_finished', ORCH, 'content_designer', { duration_ms: 30000 }),
    action('phase_finished', ORCH, 'rubric_designer', { duration_ms: 31000 }),

    action('phase_started', ORCH, 'aggregate', { index: 4, total: 4 }),
    action('validate', 'ADDIEOutputAggregator', 'aggregate', { scope: 'addie_output', error_count: 0 }),
    action('audit', ORCH, 'aggregate', {
      residual_gap_count: 2, gapped_relations: ['C4', 'P6'], ready_to_aggregate: false,
    }),
    action('phase_finished', ORCH, 'aggregate', { duration_ms: 500 }),
  ]
}

describe('buildPhaseTimeline', () => {
  it('produces one block per phase execution, in start order', () => {
    const blocks = buildPhaseTimeline(fixture())
    expect(blocks.map((b) => b.phase)).toEqual([
      'outcome_designer', 'content_designer', 'rubric_designer', 'aggregate',
    ])
    expect(blocks.map((b) => b.kind)).toEqual([
      'generation', 'generation', 'generation', 'aggregate',
    ])
  })

  it('summarises a generation phase into its story beats', () => {
    const [outcome] = buildPhaseTimeline(fixture())
    expect(outcome.agent).toBe('OutcomeDesignerAgent')
    expect(outcome.modelCalls).toBe(1)
    expect(outcome.writes).toEqual({ course_goal: 1, objective: 2 })
    expect(outcome.edgesDrawn).toBe(1)
    expect(outcome.checkRounds).toEqual([2, 0])
    expect(outcome.repairs).toBe(1)
    expect(outcome.graphOps).toBe(1)
    expect(outcome.durationMs).toBe(42000)
  })

  it('folds the residual audit into the aggregate block', () => {
    const aggregate = buildPhaseTimeline(fixture())[3]
    expect(aggregate.auditGapCount).toBe(2)
    expect(aggregate.auditGappedRelations).toEqual(['C4', 'P6'])
    expect(aggregate.auditReady).toBe(false)
  })

  it('leaves audit fields null on blocks nothing landed in', () => {
    const outcome = buildPhaseTimeline(fixture())[0]
    expect(outcome.auditGapCount).toBeNull()
  })

  it('groups overlapping phases into one parallel group, with interleaved work routed by phase', () => {
    const blocks = buildPhaseTimeline(fixture())
    const content = blocks[1]
    const rubric = blocks[2]
    expect(content.parallelGroup).not.toBeNull()
    expect(content.parallelGroup).toBe(rubric.parallelGroup)
    // Interleaved actions landed in the right blocks.
    expect(content.modelCalls).toBe(1)
    expect(rubric.modelCalls).toBe(1)
    expect(rubric.writes).toEqual({ rubric: 1 })
    expect(rubric.recoveries).toEqual({ retry: 1 })
    // Sequential blocks stay ungrouped.
    expect(blocks[0].parallelGroup).toBeNull()
    expect(blocks[3].parallelGroup).toBeNull()
  })

  it('records the aggregate schema validation', () => {
    const aggregate = buildPhaseTimeline(fixture())[3]
    expect(aggregate.kind).toBe('aggregate')
    expect(aggregate.schemaErrors).toBe(0)
  })

  it('keeps every non-boundary action inside exactly one block', () => {
    const actions = fixture()
    const blocks = buildPhaseTimeline(actions)
    const folded = blocks.reduce((sum, block) => sum + block.actions.length, 0)
    const boundaries = actions.filter(
      (a) => a.action === 'phase_started' || a.action === 'phase_finished',
    ).length
    expect(folded).toBe(actions.length - boundaries)
  })

  it('returns nothing for an empty run', () => {
    expect(buildPhaseTimeline([])).toEqual([])
  })
})

describe('helpers', () => {
  it('lists specialists (generation blocks only) for the filter chips', () => {
    expect(timelineAgents(buildPhaseTimeline(fixture()))).toEqual([
      'OutcomeDesignerAgent', 'ContentDesignerAgent', 'RubricDesignerAgent',
    ])
  })

  it('summarises writes compactly with a cap', () => {
    expect(writesSummary({ objective: 5, course_goal: 1 })).toBe('5× objective, 1× course_goal')
    expect(writesSummary({ a: 4, b: 3, c: 2, d: 1 }, 2)).toBe('4× a, 3× b +2 more')
  })

  it('gives every known specialist a stable hue and unknowns a fallback', () => {
    expect(agentHue('OutcomeDesignerAgent')).not.toEqual(agentHue('AssessmentDesignerAgent'))
    expect(agentHue('SomethingElse')).toEqual(agentHue('AnotherUnknown'))
  })
})

describe('phaseLabel', () => {
  it('names the workflow phases in the designer\'s terms', () => {
    expect(phaseLabel('outcome_designer')).toBe('Goals & objectives')
    expect(phaseLabel('implementation_planner')).toBe('Delivery plan')
    expect(phaseLabel('monolithic_designer')).toBe('All artifacts (single agent)')
  })

  it('falls back to a readable form for anything unrecognised', () => {
    expect(phaseLabel('some_new_phase')).toBe('Some new phase')
  })
})
