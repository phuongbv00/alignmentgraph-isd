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

const ORCH = 'Orchestrator'

/**
 * A miniature agentic run in the shape the harness actually emits
 * (`core/runner.py`): stages in sequence, a stage that fans out to
 * Developers INSIDE its own phase, then the reconciliation pass, then
 * aggregation.
 */
function fixture(): DeepAction[] {
  tick = 0
  return [
    action('phase_started', ORCH, 'outcomes', { index: 2, total: 8 }),
    action('llm_call', 'OutcomeDesignerAgent', 'outcomes', {}),
    action('agent_step', 'OutcomeDesignerAgent', 'outcomes', { agent_action: 'design_outcomes' }),
    action('node_write', 'OutcomeDesignerAgent', 'outcomes', { op: 'add', node_type: 'course_goal' }),
    action('node_write', 'OutcomeDesignerAgent', 'outcomes', { op: 'add', node_type: 'objective' }),
    action('node_write', 'OutcomeDesignerAgent', 'outcomes', { op: 'add', node_type: 'objective' }),
    action('node_read', 'OutcomeDesignerAgent', 'outcomes', { query: 'element_nodes' }),
    action('edge_write', 'OutcomeDesignerAgent', 'outcomes', { op: 'add', relation_id: 'C1' }),
    action('check', 'OutcomeDesignerAgent', 'outcomes', { round: 1, violation_count: 2 }),
    action('repair', 'OutcomeDesignerAgent', 'outcomes', { violation_type: 'bloom' }),
    action('check', 'OutcomeDesignerAgent', 'outcomes', { round: 2, violation_count: 0 }),
    action('phase_finished', ORCH, 'outcomes', { duration_ms: 42000 }),

    // Fan-out: the Designer plans the split, then the Developer writes each
    // work set — under its own identity, inside the Designer's phase.
    action('phase_started', ORCH, 'assessment', { index: 3, total: 8 }),
    action('llm_call', 'AssessmentDesignerAgent', 'assessment', {}),
    action('agent_step', 'AssessmentDesignerAgent', 'assessment', { agent_action: 'design_assessment' }),
    action('dev_plan', ORCH, 'assessment', {
      family: 'assessment_designer', set_count: 2, source: 'llm',
      sets: [{ set_id: 'S1' }, { set_id: 'S2' }],
    }),
    action('llm_call', 'AssessmentDeveloperAgent', 'assessment', {}),
    action('node_write', 'AssessmentDeveloperAgent', 'assessment', { op: 'add', node_type: 'assessment' }),
    action('submit_rejected', 'AssessmentDeveloperAgent', 'assessment', { input_summary: 'missing field' }),
    action('llm_call', 'AssessmentDeveloperAgent', 'assessment', {}),
    action('node_write', 'AssessmentDeveloperAgent', 'assessment', { op: 'add', node_type: 'rubric' }),
    action('phase_finished', ORCH, 'assessment', { duration_ms: 61000 }),

    action('phase_started', ORCH, 'reconcile', { index: 7, total: 8 }),
    action('reconcile', 'AssessmentDesignerAgent', 'reconcile', {
      family: 'assessment_designer', routed: 3, violation_types: ['item_completeness', 'coverage'],
    }),
    action('repair', 'AssessmentDesignerAgent', 'reconcile', { violation_type: 'coverage' }),
    action('phase_finished', ORCH, 'reconcile', { duration_ms: 9000 }),

    action('phase_started', ORCH, 'aggregate', { index: 8, total: 8 }),
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
      'outcomes', 'assessment', 'reconcile', 'aggregate',
    ])
    expect(blocks.map((b) => b.kind)).toEqual([
      'generation', 'generation', 'generation', 'aggregate',
    ])
  })

  it('summarises a generation phase into its story beats', () => {
    const [outcomes] = buildPhaseTimeline(fixture())
    expect(outcomes.agent).toBe('OutcomeDesignerAgent')
    expect(outcomes.modelCalls).toBe(1)
    expect(outcomes.writes).toEqual({ course_goal: 1, objective: 2 })
    expect(outcomes.edgesDrawn).toBe(1)
    expect(outcomes.checkRounds).toEqual([2, 0])
    expect(outcomes.repairs).toBe(1)
    expect(outcomes.graphOps).toBe(1)
    expect(outcomes.durationMs).toBe(42000)
    // No fan-out: this stage writes its own artifacts.
    expect(outcomes.workSets).toBe(0)
  })

  it('keeps a fanned-out stage named after its Designer, not its last Developer', () => {
    const assessment = buildPhaseTimeline(fixture())[1]
    // The Developer acts last in the block; naming the card after the last
    // actor would credit the stage to a sub-agent that only wrote one set.
    expect(assessment.agent).toBe('AssessmentDesignerAgent')
    expect(assessment.agents).toEqual([
      'AssessmentDesignerAgent', 'Orchestrator', 'AssessmentDeveloperAgent',
    ])
  })

  it('folds a dev plan into the dispatching stage', () => {
    const assessment = buildPhaseTimeline(fixture())[1]
    expect(assessment.workSets).toBe(2)
    expect(assessment.workSetIds).toEqual(['S1', 'S2'])
    // Developer turns and their submissions belong to the stage that
    // dispatched them: one block, both tiers.
    expect(assessment.modelCalls).toBe(3)
    expect(assessment.writes).toEqual({ assessment: 1, rubric: 1 })
    expect(assessment.recoveries).toEqual({ submit_rejected: 1 })
  })

  it('keeps the reconciliation pass out of the last stage', () => {
    const [, assessment, reconcile] = buildPhaseTimeline(fixture())
    expect(reconcile.routedViolations).toBe(3)
    expect(reconcile.routedViolationTypes).toEqual(['item_completeness', 'coverage'])
    expect(reconcile.repairs).toBe(1)
    // The pass runs after every stage; its repairs must not inflate the work
    // the last stage is shown to have done.
    expect(assessment.repairs).toBe(0)
    expect(assessment.routedViolations).toBe(0)
  })

  it('folds the residual audit into the aggregate block', () => {
    const aggregate = buildPhaseTimeline(fixture())[3]
    expect(aggregate.auditGapCount).toBe(2)
    expect(aggregate.auditGappedRelations).toEqual(['C4', 'P6'])
    expect(aggregate.auditReady).toBe(false)
  })

  it('leaves audit fields null on blocks nothing landed in', () => {
    const outcomes = buildPhaseTimeline(fixture())[0]
    expect(outcomes.auditGapCount).toBeNull()
  })

  it('counts a prose write as an artifact, keyed by its document', () => {
    const blocks = buildPhaseTimeline([
      action('phase_started', ORCH, 'outcomes', { index: 2, total: 8 }),
      action('llm_call', 'OutcomeDesignerAgent', 'outcomes', {}),
      action('doc_write', 'OutcomeDesignerAgent', 'outcomes', { key: 'objective', field_count: 3 }),
      action('phase_finished', ORCH, 'outcomes', { duration_ms: 1000 }),
    ])
    // The prose arm builds no graph, so without this a prose block would
    // report model turns and nothing produced.
    expect(blocks[0].writes).toEqual({ objective: 1 })
  })

  it('leaves sequential blocks ungrouped', () => {
    // The current design never overlaps phases — stages run in sequence and a
    // stage's Developers run one work set at a time. The grouping stays for
    // archived runs from the concurrent pipeline, which replay through here.
    expect(buildPhaseTimeline(fixture()).map((b) => b.parallelGroup))
      .toEqual([null, null, null, null])
  })

  it('groups overlapping phases into one parallel group, routing work by phase', () => {
    const actions = [
      action('phase_started', ORCH, 'content', { index: 5, total: 8 }),
      action('phase_started', ORCH, 'activities', { index: 4, total: 8 }),
      action('llm_call', 'ContentDesignerAgent', 'content', {}),
      action('llm_call', 'ActivityDesignerAgent', 'activities', {}),
      action('phase_finished', ORCH, 'content', { duration_ms: 30000 }),
      action('phase_finished', ORCH, 'activities', { duration_ms: 31000 }),
    ]
    const [content, activities] = buildPhaseTimeline(actions)
    expect(content.parallelGroup).not.toBeNull()
    expect(content.parallelGroup).toBe(activities.parallelGroup)
    expect(content.modelCalls).toBe(1)
    expect(activities.modelCalls).toBe(1)
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
  it('offers a filter chip for every agent that acted, Developers included', () => {
    expect(timelineAgents(buildPhaseTimeline(fixture()))).toEqual([
      'OutcomeDesignerAgent', 'AssessmentDesignerAgent',
      'Orchestrator', 'AssessmentDeveloperAgent',
    ])
  })

  it('summarises writes compactly with a cap', () => {
    expect(writesSummary({ objective: 5, course_goal: 1 })).toBe('5× objective, 1× course_goal')
    expect(writesSummary({ a: 4, b: 3, c: 2, d: 1 }, 2)).toBe('4× a, 3× b +2 more')
  })

  it('gives a Developer its dispatching Designer\'s hue, and unknowns a fallback', () => {
    expect(agentHue('OutcomeDesignerAgent')).not.toEqual(agentHue('AssessmentDesignerAgent'))
    expect(agentHue('AssessmentDeveloperAgent')).toEqual(agentHue('AssessmentDesignerAgent'))
    expect(agentHue('SomethingElse')).toEqual(agentHue('AnotherUnknown'))
  })
})

describe('phaseLabel', () => {
  it('names the ADDIE stages the harness emits', () => {
    expect(phaseLabel('outcomes')).toBe('Goals & objectives')
    expect(phaseLabel('implementation')).toBe('Delivery plan')
    // The single arm reports one phase for the whole run: it is one ReAct loop
    // over every stage, and that absence of per-stage brackets IS the axis.
    expect(phaseLabel('design')).toBe('Whole design (one agent, one loop)')
  })

  it('falls back to a readable form for anything unrecognised', () => {
    expect(phaseLabel('some_new_phase')).toBe('Some new phase')
  })
})
