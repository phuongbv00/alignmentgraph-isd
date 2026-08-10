import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS, edgeLayer, isElementNode, layerCounts, shortLabel, toCytoscape } from './toCytoscape'
import type { AlignmentGraphPayload, GraphEdge } from '../api/types'

/**
 * A miniature dump with the same structure as a real one: element and section
 * nodes, all three edge layers, an aligned objective and an unaligned one.
 */
function fixture(): AlignmentGraphPayload {
  const edge = (
    relation_id: string, type: string, source: string, target: string, established_by: string,
  ): GraphEdge => ({ relation_id, type, source, target, established_by, evidence: '', rationale: '' })

  return {
    nodes: [
      { id: 'needs_context_0', type: 'needs_context' },
      { id: 'gap:GAP-01', type: 'gap' },
      { id: 'objective_0', type: 'objective' },
      { id: 'objective:LO-01', type: 'objective' },
      { id: 'objective:LO-02', type: 'objective' },
      { id: 'assessment_0', type: 'assessment' },
      { id: 'assessment:AT-01', type: 'assessment' },
      { id: 'activity:ACT-01', type: 'activity' },
      { id: 'summative:SA-01', type: 'summative' },
      { id: 'media:MED-01', type: 'media' },
    ],
    edges: [
      // alignment layer: matched ids / types
      edge('R3', 'R3-measures', 'assessment:AT-01', 'objective:LO-01', 'id'),
      edge('R4', 'R4-supports', 'activity:ACT-01', 'objective:LO-01', 'id'),
      edge('R5', 'R5-evaluates', 'summative:SA-01', 'objective:LO-01', 'id'),
      edge('R6', 'R6-realizes', 'assessment_0', 'assessment:AT-01', 'type'),
      // provenance layer
      edge('R1', 'R1-informs', 'gap:GAP-01', 'objective:LO-01', 'provenance'),
      edge('R1', 'R1-informs', 'gap:GAP-01', 'objective:LO-02', 'provenance'),
      edge('R11', 'R11-constrains', 'needs_context_0', 'media:MED-01', 'provenance'),
      // scaffolding: no relation id, dropped by the DOT export too
      edge('', 'rooted-in', 'objective:LO-01', 'objective_0', ''),
      edge('', 'rooted-in', 'assessment:AT-01', 'assessment_0', ''),
    ],
    objective_alignment: {
      'objective:LO-01': { measured: true, supported: true, evaluated: true, bloom_ok: true, aligned: true },
      'objective:LO-02': { measured: false, supported: false, evaluated: false, bloom_ok: false, aligned: false },
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
  it('classifies by how the relation was established', () => {
    const graph = fixture()
    expect(edgeLayer(graph.edges[0])).toBe('alignment') // established by id
    expect(edgeLayer(graph.edges[3])).toBe('alignment') // established by type
    expect(edgeLayer(graph.edges[4])).toBe('provenance')
    expect(edgeLayer(graph.edges[7])).toBe('scaffolding') // no relation id
  })

  it('counts each layer for the controls', () => {
    expect(layerCounts(fixture())).toEqual({ alignment: 4, provenance: 3, scaffolding: 2 })
  })
})

describe('toCytoscape', () => {
  it('shows only the alignment layer by default', () => {
    const elements = toCytoscape(fixture(), DEFAULT_FILTERS)
    expect(edges(elements)).toHaveLength(4)
    // The provenance hub and the media node it constrains are not pulled in.
    expect(ids(nodes(elements))).not.toContain('needs_context_0')
    expect(ids(nodes(elements))).not.toContain('media:MED-01')
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
    expect(ids(nodes(withProvenance))).toContain('needs_context_0')
    expect(ids(nodes(withProvenance))).toContain('media:MED-01')

    const everything = toCytoscape(fixture(), { alignment: true, provenance: true, scaffolding: true })
    expect(nodes(everything)).toHaveLength(10)
    expect(edges(everything)).toHaveLength(9)
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
    expect(aligned.data.badge).toBe('✓✓✓')

    expect(unaligned.classes).toContain('unaligned')
    expect(unaligned.classes).toContain('bloom-warning')
    expect(unaligned.data.badge).toBe('✗✗✗')
  })

  it('marks section nodes so they read as holding a whole ADDIE section', () => {
    const elements = toCytoscape(fixture(), { alignment: true, provenance: true, scaffolding: true })
    expect(nodes(elements).find((n) => n.data.id === 'assessment_0')!.classes).toContain('section')
    expect(nodes(elements).find((n) => n.data.id === 'assessment:AT-01')!.classes).toContain('element')
  })

  it('flags a measures edge into an objective whose Bloom level does not hold', () => {
    const graph = fixture()
    graph.edges.push({
      relation_id: 'R3', type: 'R3-measures', source: 'assessment:AT-01',
      target: 'objective:LO-02', established_by: 'id', evidence: '', rationale: '',
    })
    const elements = toCytoscape(graph, DEFAULT_FILTERS)
    const flagged = edges(elements).find((e) => e.data.target === 'objective:LO-02')!
    expect(flagged.classes).toContain('bloom-violation')
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
