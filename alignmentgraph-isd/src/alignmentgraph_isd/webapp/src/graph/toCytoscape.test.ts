import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS, edgeLayer, isElementNode, layerCounts, shortLabel, toCytoscape } from './toCytoscape'
import type { AlignmentGraphPayload, GraphEdge } from '../api/types'

/**
 * A miniature dump with the same structure as a real one: element and section
 * nodes, all three edge layers, an aligned objective and an unaligned one.
 * Relations follow the current C1–C5 / P1–P11 registry; note that C5 is
 * core relations established by PROVENANCE — the case the old mechanism-based
 * layering silently hid.
 */
function fixture(): AlignmentGraphPayload {
  const edge = (
    relation_id: string, type: string, source: string, target: string, established_by: string,
  ): GraphEdge => ({ relation_id, type, source, target, established_by, evidence: '', rationale: '' })

  return {
    nodes: [
      { id: 'course_goal_0', type: 'course_goal' },
      { id: 'gap:GAP-01', type: 'gap' },
      { id: 'objective:LO-01', type: 'objective' },
      { id: 'objective:LO-02', type: 'objective' },
      { id: 'assessment_plan_0', type: 'assessment_plan' },
      { id: 'assessment:AT-01', type: 'assessment' },
      { id: 'activity:ACT-01', type: 'activity' },
      { id: 'content:MOD-01', type: 'content' },
      { id: 'material:MAT-01', type: 'material' },
      { id: 'improvement_0', type: 'improvement' },
    ],
    edges: [
      // alignment layer = the CORE relations C1–C5, whatever established them
      edge('C1', 'C1-decomposes_to', 'course_goal_0', 'objective:LO-01', 'provenance'),
      edge('C2', 'C2-assessed_by', 'objective:LO-01', 'assessment:AT-01', 'id'),
      edge('C3', 'C3-practiced_by', 'objective:LO-01', 'activity:ACT-01', 'id'),
      edge('C5', 'C5-supports', 'content:MOD-01', 'activity:ACT-01', 'provenance'),
      // provenance layer = the secondary relations P1–P11 — including P3,
      // which is TYPE-established but still secondary
      edge('P1', 'P1-informs', 'gap:GAP-01', 'objective:LO-01', 'provenance'),
      edge('P3', 'P3-realizes', 'assessment_plan_0', 'assessment:AT-01', 'type'),
      edge('P5', 'P5-covers', 'content:MOD-01', 'material:MAT-01', 'provenance'),
      // scaffolding: no relation id, dropped by the DOT export too
      edge('', 'narrates', 'improvement_0', 'objective:LO-01', ''),
    ],
    objective_alignment: {
      'objective:LO-01': { measured: true, supported: true, bloom_ok: true, aligned: true },
      'objective:LO-02': { measured: false, supported: false, bloom_ok: false, aligned: false },
    },
    relation_coverage: {},
    metadata: {},
  }
}

const nodes = (elements: ReturnType<typeof toCytoscape>) => elements.filter((e) => e.group === 'nodes')
const edges = (elements: ReturnType<typeof toCytoscape>) => elements.filter((e) => e.group === 'edges')
const ids = (elements: ReturnType<typeof toCytoscape>) => elements.map((e) => e.data.id as string)

describe('node id conventions', () => {
  it('tells element nodes from section nodes by the separator', () => {
    expect(isElementNode('objective:LO-01')).toBe(true)
    expect(isElementNode('objective_0')).toBe(false)
  })

  it('labels element nodes by their item id and sections by their type', () => {
    expect(shortLabel('objective:LO-01', 'objective')).toBe('LO-01')
    expect(shortLabel('objective_0', 'objective')).toBe('objective')
  })
})

describe('edge layers', () => {
  it('classifies by relation class (C = core alignment, P = secondary), not by mechanism', () => {
    const graph = fixture()
    expect(edgeLayer(graph.edges[0])).toBe('alignment') // C1, provenance-established
    expect(edgeLayer(graph.edges[1])).toBe('alignment') // C2, id-established
    expect(edgeLayer(graph.edges[3])).toBe('alignment') // C5, provenance-established
    expect(edgeLayer(graph.edges[4])).toBe('provenance') // P1
    expect(edgeLayer(graph.edges[5])).toBe('provenance') // P3, TYPE-established but secondary
    expect(edgeLayer(graph.edges[7])).toBe('scaffolding') // no relation id
  })

  it('counts each layer for the controls', () => {
    expect(layerCounts(fixture())).toEqual({ alignment: 4, provenance: 3, scaffolding: 1 })
  })
})

describe('toCytoscape', () => {
  it('shows only the alignment layer by default', () => {
    const elements = toCytoscape(fixture(), DEFAULT_FILTERS)
    expect(edges(elements)).toHaveLength(4)
    // Secondary-only nodes are not pulled in.
    expect(ids(nodes(elements))).not.toContain('gap:GAP-01')
    expect(ids(nodes(elements))).not.toContain('assessment_plan_0')
    expect(ids(nodes(elements))).not.toContain('material:MAT-01')
  })

  it('keeps content modules in the alignment view', () => {
    // CORE alignment; the old mechanism-based rule hid it from the default
    // view. (The AT↔rubric leg this also used to cover went with the rubric
    // node type: a criterion is a field of the item it marks, not a node.)
    // are provenance-ESTABLISHED but core relations; the old mechanism-based
    // layering dropped them, which hid every content module and the whole
    const elements = toCytoscape(fixture(), DEFAULT_FILTERS)
    expect(ids(nodes(elements))).toContain('content:MOD-01')
    const relationIds = edges(elements).map((e) => e.data.relationId)
    expect(relationIds).toContain('C5')
  })

  it('keeps every objective visible even with no edges at all', () => {
    // An orphaned objective is exactly what a viewer needs to see, so it must
    // not be filtered out along with its missing relations.
    const elements = toCytoscape(fixture(), { alignment: false, provenance: false, scaffolding: false })
    expect(ids(nodes(elements)).sort()).toEqual(['objective:LO-01', 'objective:LO-02'])
    expect(edges(elements)).toHaveLength(0)
  })

  it('adds nodes as the layers they touch are switched on', () => {
    const withProvenance = toCytoscape(fixture(), { ...DEFAULT_FILTERS, provenance: true })
    expect(ids(nodes(withProvenance))).toContain('gap:GAP-01')
    expect(ids(nodes(withProvenance))).toContain('assessment_plan_0')
    expect(ids(nodes(withProvenance))).toContain('material:MAT-01')

    const everything = toCytoscape(fixture(), { alignment: true, provenance: true, scaffolding: true })
    expect(nodes(everything)).toHaveLength(10)
    expect(edges(everything)).toHaveLength(8)
  })

  it('never emits an edge whose endpoints are not both visible', () => {
    for (const filters of [
      DEFAULT_FILTERS,
      { alignment: true, provenance: true, scaffolding: false },
      { alignment: false, provenance: true, scaffolding: true },
      { alignment: true, provenance: true, scaffolding: true },
    ]) {
      const elements = toCytoscape(fixture(), filters)
      const present = new Set(ids(nodes(elements)))
      for (const edge of edges(elements)) {
        expect(present.has(edge.data.source as string)).toBe(true)
        expect(present.has(edge.data.target as string)).toBe(true)
      }
    }
  })

  it('colours objectives by whether every alignment leg holds', () => {
    const elements = toCytoscape(fixture(), DEFAULT_FILTERS)
    const aligned = nodes(elements).find((n) => n.data.id === 'objective:LO-01')!
    const unaligned = nodes(elements).find((n) => n.data.id === 'objective:LO-02')!

    expect(aligned.classes).toContain('aligned')
    expect(aligned.classes).not.toContain('unaligned')
    expect(aligned.data.badge).toBe('✓✓')

    expect(unaligned.classes).toContain('unaligned')
    expect(unaligned.classes).toContain('bloom-warning')
    expect(unaligned.data.badge).toBe('✗✗')
  })

  it('marks section nodes so they read as holding a whole ADDIE section', () => {
    const elements = toCytoscape(fixture(), { alignment: true, provenance: true, scaffolding: true })
    expect(nodes(elements).find((n) => n.data.id === 'assessment_plan_0')!.classes).toContain('section')
    expect(nodes(elements).find((n) => n.data.id === 'assessment:AT-01')!.classes).toContain('element')
  })

  it('flags an assessed_by edge out of an objective whose Bloom level does not hold', () => {
    // C2/C3 are id-reverse: the LO is the edge SOURCE, so the flags are read
    // from the source side — the mirror of the DOT export's red-edge rule.
    const graph = fixture()
    graph.edges.push({
      relation_id: 'C2', type: 'C2-assessed_by', source: 'objective:LO-02',
      target: 'assessment:AT-01', established_by: 'id', evidence: '', rationale: '',
    })
    const elements = toCytoscape(graph, DEFAULT_FILTERS)
    const flagged = edges(elements).find((e) => e.data.source === 'objective:LO-02')!
    expect(flagged.classes).toContain('bloom-violation')
    // The healthy objective's own C2 edge stays unflagged.
    const healthy = edges(elements).find(
      (e) => e.data.source === 'objective:LO-01' && e.data.relationId === 'C2',
    )!
    expect(healthy.classes).not.toContain('bloom-violation')
  })

  it('renders secondary relations dotted via the secondary class', () => {
    const elements = toCytoscape(fixture(), { alignment: true, provenance: true, scaffolding: false })
    const secondary = edges(elements).find((e) => e.data.relationId === 'P1')!
    expect(secondary.classes).toContain('secondary')
    const core = edges(elements).find((e) => e.data.relationId === 'C2')!
    expect(core.classes).not.toContain('secondary')
  })

  it('gives every edge a stable unique id', () => {
    const elements = toCytoscape(fixture(), { alignment: true, provenance: true, scaffolding: true })
    const edgeIds = ids(edges(elements))
    expect(new Set(edgeIds).size).toBe(edgeIds.length)
  })

  it('returns nothing for a missing graph', () => {
    expect(toCytoscape(null)).toEqual([])
  })
})
