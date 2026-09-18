import { describe, expect, it } from 'vitest'
import {
  alignmentBadge, DEFAULT_FILTERS, edgeId, edgeLayer, isElementNode, layerCounts,
  shortLabel, toCytoscape,
} from './toCytoscape'
import type { AlignmentGraphPayload, GraphEdge } from '../api/types'

/**
 * A miniature dump with the same structure as a real one: element and section
 * nodes, all three edge layers, an aligned objective and an unaligned one.
 * Relations follow the current C1–C4 / P1–P14 registry; note that C1 is a
 * core relation established by PROVENANCE — the case a mechanism-based
 * layering would silently hide. The C5 edge is what an ARCHIVED dump carries
 * (its module is typed `content`): it still reads as core alignment, because
 * the layer ships with the edge and is never re-derived here.
 */
function fixture(): AlignmentGraphPayload {
  const edge = (
    relation_id: string, type: string, source: string, target: string, established_by: string,
  ): GraphEdge => ({
    relation_id, type, source, target, established_by, evidence: '', rationale: '',
    // Exactly what the harness ships, composed once there.
    id: `${relation_id || 'scaffold'}|${source}|${target}|${type}`,
    layer: !relation_id ? 'scaffolding' : relation_id.startsWith('C') ? 'alignment' : 'provenance',
    tier: !relation_id ? '' : relation_id.startsWith('C') ? 'core' : 'secondary',
    invalid: false,
    invalid_reason: '',
  })

  const node = (id: string, type: string) => ({
    id, type,
    label: id.includes(':') ? id.split(':').slice(1).join(':') : type,
    kind: (id.includes(':') ? 'element' : 'section') as 'element' | 'section',
    detail: '', level: '', repaired: false,
  })

  // The verbs and wording are the registry's, as the harness ships them.
  const legs = (assessed: boolean, practiced: boolean, prepares: boolean) => [
    { relation_id: 'C2', verb: 'assessed_by', ok: assessed,
      label: 'learning outcome assessed by assessment task' },
    { relation_id: 'C3', verb: 'practiced_by', ok: practiced,
      label: 'learning outcome practiced by activity' },
    { relation_id: 'C4', verb: 'prepares_for', ok: prepares,
      label: 'activity prepares for assessment task' },
  ]

  return {
    nodes: [
      node('course_goal_0', 'course_goal'),
      node('gap:GAP-01', 'gap'),
      node('objective:LO-01', 'objective'),
      node('objective:LO-02', 'objective'),
      node('assessment_plan_0', 'assessment_plan'),
      node('assessment:AT-01', 'assessment'),
      node('activity:ACT-01', 'activity'),
      node('content:MOD-01', 'content'),
      node('module:MOD-02', 'module'),
      node('material:MAT-01', 'material'),
      node('improvement_0', 'improvement'),
    ],
    edges: [
      // alignment layer = the CORE relations, whatever established them
      edge('C1', 'C1-decomposes_to', 'course_goal_0', 'objective:LO-01', 'provenance'),
      edge('C2', 'C2-assessed_by', 'objective:LO-01', 'assessment:AT-01', 'id'),
      edge('C3', 'C3-practiced_by', 'objective:LO-01', 'activity:ACT-01', 'id'),
      edge('C5', 'C5-supports', 'content:MOD-01', 'activity:ACT-01', 'provenance'),
      // provenance layer = the secondary relations P1–P14 — including P3,
      // which is TYPE-established but still secondary
      edge('P1', 'P1-informs', 'gap:GAP-01', 'objective:LO-01', 'provenance'),
      edge('P3', 'P3-realizes', 'assessment_plan_0', 'assessment:AT-01', 'type'),
      edge('P5', 'P5-covers', 'content:MOD-01', 'material:MAT-01', 'provenance'),
      edge('P13', 'P13-delivered_through', 'module:MOD-02', 'activity:ACT-01', 'id'),
      // scaffolding: no relation id, dropped by the DOT export too
      edge('', 'narrates', 'improvement_0', 'objective:LO-01', ''),
    ],
    objective_alignment: {
      'objective:LO-01': {
        assessed_by: true, practiced_by: true, prepares_for: true,
        bloom_ok: true, aligned: true, legs: legs(true, true, true),
      },
      'objective:LO-02': {
        assessed_by: false, practiced_by: false, prepares_for: false,
        bloom_ok: false, aligned: false, legs: legs(false, false, false),
      },
    },
    relation_coverage: {},
    schema_version: 2,
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
    expect(edgeLayer(graph.edges[3])).toBe('alignment') // C5, from an archived dump
    expect(edgeLayer(graph.edges[4])).toBe('provenance') // P1
    expect(edgeLayer(graph.edges[5])).toBe('provenance') // P3, TYPE-established but secondary
    expect(edgeLayer(graph.edges[7])).toBe('provenance') // P13: a module's relations are secondary
    expect(edgeLayer(graph.edges[8])).toBe('scaffolding') // no relation id
  })

  it('counts each layer for the controls', () => {
    expect(layerCounts(fixture())).toEqual({ alignment: 4, provenance: 4, scaffolding: 1 })
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
    expect(ids(nodes(elements))).not.toContain('module:MOD-02')
  })

  it('draws a module with the provenance layer, and an archived one where its dump put it', () => {
    // CORE alignment; the old mechanism-based rule hid it from the default
    // view. (The AT↔rubric leg this also used to cover went with the rubric
    // node type: a criterion is a field of the item it marks, not a node.)
    // are provenance-ESTABLISHED but core relations; the old mechanism-based
    // layering dropped them, which hid every content module and the whole
    const elements = toCytoscape(fixture(), DEFAULT_FILTERS)
    expect(ids(nodes(elements))).toContain('content:MOD-01')
    const relationIds = edges(elements).map((e) => e.data.relationId)
    expect(relationIds).toContain('C5')
    const withProvenance = toCytoscape(fixture(), { ...DEFAULT_FILTERS, provenance: true })
    expect(ids(nodes(withProvenance))).toContain('module:MOD-02')
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
    expect(nodes(everything)).toHaveLength(11)
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

    expect(unaligned.classes).toContain('unaligned')
    expect(unaligned.classes).toContain('bloom-warning')
  })

  it('shows which leg is missing ON the node, not only in the inspector', () => {
    // The badge was computed here for months and rendered nowhere: no
    // stylesheet selector read `data(badge)` and the canvas has no tooltips.
    // So the app said "green or amber" where the DOT export said `✓ MSP`.
    const elements = toCytoscape(fixture(), DEFAULT_FILTERS)
    const aligned = nodes(elements).find((n) => n.data.id === 'objective:LO-01')!
    const unaligned = nodes(elements).find((n) => n.data.id === 'objective:LO-02')!

    expect(aligned.data.label).toBe('LO-01\n✓✓✓')
    expect(unaligned.data.label).toBe('LO-02\n✗✗✗')
    // One glyph per leg, in the order the harness declares them.
    expect(alignmentBadge(fixture().objective_alignment['objective:LO-01'])).toBe('✓✓✓')
    // A node with no alignment flags gets a plain label, not an empty badge line.
    expect(nodes(elements).find((n) => n.data.id === 'assessment:AT-01')!.data.label).toBe('AT-01')
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

/**
 * A payload as it looked BEFORE the harness shipped display semantics
 * (2026-09-11): no node `label`/`kind`, no edge `id`/`layer`/`tier`/`invalid`,
 * no `legs`, no `legend`. 36 such dumps sit in the benchmark results tree.
 *
 * The server upgrades one of these on read, so this is not the normal path —
 * but the `??` fallbacks in `toCytoscape` are the only thing standing between
 * a raw archived file and a blank canvas, and a fallback nothing exercises is
 * a fallback that has already stopped working.
 */
function legacyFixture(): AlignmentGraphPayload {
  const current = fixture()
  return {
    ...current,
    nodes: current.nodes.map(({ id, type }) => ({ id, type })),
    edges: current.edges.map(({ relation_id, type, source, target, established_by }) => ({
      relation_id, type, source, target, established_by, evidence: '', rationale: '',
    })),
    objective_alignment: Object.fromEntries(
      Object.entries(current.objective_alignment).map(([id, flags]) => {
        const { legs: _legs, ...rest } = flags
        return [id, rest]
      }),
    ),
    schema_version: undefined,
  }
}

describe('a payload archived before the display fields existed', () => {
  it('still draws the same graph', () => {
    const modern = toCytoscape(fixture(), DEFAULT_FILTERS)
    const legacy = toCytoscape(legacyFixture(), DEFAULT_FILTERS)

    expect(ids(legacy)).toEqual(ids(modern))
    expect(legacy.map((e) => e.classes)).toEqual(modern.map((e) => e.classes))
    expect(legacy.map((e) => e.data.label)).toEqual(modern.map((e) => e.data.label))
  })

  it('composes the same edge ids the canvas selects by', () => {
    // Including the `scaffold` prefix, which the inspector's own copy of this
    // dropped — so opening a `narrates` edge from a node's relation list
    // selected nothing on the canvas.
    const scaffolding = legacyFixture().edges.find((e) => !e.relation_id)!
    expect(edgeId(scaffolding)).toBe(`scaffold|${scaffolding.source}|${scaffolding.target}|narrates`)
  })

  it('still classifies its layers and its badge', () => {
    const legacy = legacyFixture()
    expect(edgeLayer(legacy.edges.find((e) => e.relation_id === 'C2')!)).toBe('alignment')
    expect(edgeLayer(legacy.edges.find((e) => e.relation_id === 'P1')!)).toBe('provenance')
    expect(edgeLayer(legacy.edges.find((e) => !e.relation_id)!)).toBe('scaffolding')
    expect(alignmentBadge(legacy.objective_alignment['objective:LO-01'])).toBe('✓✓✓')
  })

  it('shortens a badge rather than inventing a ✗ for a leg it never had', () => {
    // `prepares` arrived on 2026-09-10; a dump from before it says nothing
    // about that leg, and a ✗ would be an answer the run never gave.
    expect(alignmentBadge({
      measured: true, supported: true, bloom_ok: true, aligned: true,
    })).toBe('✓✓')
    // ...and reads the current names just as well.
    expect(alignmentBadge({
      assessed_by: true, practiced_by: false, bloom_ok: true, aligned: false,
    })).toBe('✓✗')
  })
})
