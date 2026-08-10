import type { AlignmentGraphPayload, GraphEdge } from '../api/types'

/**
 * Turning an alignment-graph dump into something legible.
 *
 * A real run is ~58 nodes and ~127 edges, and left unfiltered dagre draws a
 * hairball: 25 of those edges are internal scaffolding with no relation id
 * (the DOT export drops them too), and of the rest the great majority are
 * provenance edges fanning out of the single `needs_context_0` hub.
 *
 * So edges come in three layers, switched independently:
 *
 *  - `alignment` — established by matching ids or types (R3/R4/R5/R6/R9/R12).
 *    This is constructive alignment itself: which assessment measures which
 *    objective, which activity supports it, which summative item evaluates it.
 *    On by default, because it is the thing worth looking at.
 *  - `provenance` — where an artifact came from (R1/R2/R7/R8/R10/R11/R13).
 *  - `scaffolding` — the relation-less structural edges.
 */

export type EdgeLayer = 'alignment' | 'provenance' | 'scaffolding'

export interface GraphFilters {
  alignment: boolean
  provenance: boolean
  scaffolding: boolean
}

export const DEFAULT_FILTERS: GraphFilters = {
  alignment: true,
  provenance: false,
  scaffolding: false,
}

export interface CyElement {
  group: 'nodes' | 'edges'
  data: Record<string, unknown>
  classes?: string
}

export function edgeLayer(edge: GraphEdge): EdgeLayer {
  if (!edge.relation_id) return 'scaffolding'
  return edge.established_by === 'id' || edge.established_by === 'type' ? 'alignment' : 'provenance'
}

/** Element nodes carry one artifact item (`objective:LO-01`); section nodes
 *  (`objective_0`) carry a whole ADDIE section. The distinction is the `:`. */
export function isElementNode(id: string): boolean {
  return id.includes(':')
}

export function shortLabel(id: string, type: string): string {
  if (isElementNode(id)) return id.split(':').slice(1).join(':')
  return type || id
}

export function toCytoscape(
  graph: AlignmentGraphPayload | null,
  filters: GraphFilters = DEFAULT_FILTERS,
): CyElement[] {
  if (!graph) return []

  const alignment = graph.objective_alignment ?? {}
  const visibleEdges = (graph.edges ?? []).filter((edge) => filters[edgeLayer(edge)])

  // A node earns its place by being an objective (always — objectives are the
  // spine of the graph and an orphaned one is exactly what a viewer must see)
  // or by touching a visible edge. Same rule the DOT export uses.
  const touched = new Set<string>()
  for (const edge of visibleEdges) {
    touched.add(edge.source)
    touched.add(edge.target)
  }

  const elements: CyElement[] = []
  const present = new Set<string>()

  for (const node of graph.nodes ?? []) {
    const isObjectiveElement = node.type === 'objective' && isElementNode(node.id)
    if (!isObjectiveElement && !touched.has(node.id)) continue

    const flags = alignment[node.id]
    present.add(node.id)
    elements.push({
      group: 'nodes',
      data: {
        id: node.id,
        label: shortLabel(node.id, node.type),
        type: node.type,
        kind: isElementNode(node.id) ? 'element' : 'section',
        // Rendered as a ✓/✗ badge: measured / supported / evaluated.
        badge: flags ? `${flags.measured ? '✓' : '✗'}${flags.supported ? '✓' : '✗'}${flags.evaluated ? '✓' : '✗'}` : '',
        aligned: flags ? flags.aligned : null,
        bloomOk: flags ? flags.bloom_ok : null,
      },
      classes: nodeClasses(node.type, node.id, flags?.aligned, flags?.bloom_ok),
    })
  }

  for (const edge of visibleEdges) {
    // Dropped rather than rendered dangling: an edge to a node that failed the
    // visibility rule above would draw into empty space.
    if (!present.has(edge.source) || !present.has(edge.target)) continue
    const targetFlags = alignment[edge.target]
    // A "measures" edge into an objective whose Bloom level does not hold up is
    // the single most important defect the graph can show, so it is called out
    // in red rather than left to the badge alone.
    const bloomViolation = edge.relation_id === 'R3' && targetFlags?.bloom_ok === false

    elements.push({
      group: 'edges',
      data: {
        id: `${edge.relation_id || 'scaffold'}|${edge.source}|${edge.target}|${edge.type}`,
        source: edge.source,
        target: edge.target,
        label: edge.type,
        relationId: edge.relation_id,
        establishedBy: edge.established_by,
        evidence: edge.evidence,
        rationale: edge.rationale,
      },
      classes: [
        `by-${edge.established_by || 'none'}`,
        edge.relation_id === 'R5' ? 'evaluates' : '',
        bloomViolation ? 'bloom-violation' : '',
      ]
        .filter(Boolean)
        .join(' '),
    })
  }

  return elements
}

function nodeClasses(
  type: string,
  id: string,
  aligned?: boolean | null,
  bloomOk?: boolean | null,
): string {
  const classes = [`type-${type || 'unknown'}`, isElementNode(id) ? 'element' : 'section']
  if (aligned === true) classes.push('aligned')
  if (aligned === false) classes.push('unaligned')
  if (bloomOk === false) classes.push('bloom-warning')
  return classes.join(' ')
}

/** Counts for the controls, so the effect of each toggle is visible up front. */
export function layerCounts(graph: AlignmentGraphPayload | null): Record<EdgeLayer, number> {
  const counts: Record<EdgeLayer, number> = { alignment: 0, provenance: 0, scaffolding: 0 }
  for (const edge of graph?.edges ?? []) counts[edgeLayer(edge)] += 1
  return counts
}
