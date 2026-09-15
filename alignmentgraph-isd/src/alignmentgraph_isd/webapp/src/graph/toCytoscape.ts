import type { AlignmentGraphPayload, GraphEdge, GraphNode, ObjectiveAlignment } from '../api/types'

/**
 * Turning an alignment-graph dump into something legible.
 *
 * A real run is dozens of nodes and >100 edges, and left unfiltered dagre
 * draws a hairball: the structural edges carry no relation id (the DOT export
 * drops them too), and the secondary relations fan out of a handful of hubs.
 *
 * So edges come in three layers, switched independently, split exactly the way
 * `alignment.py::REGISTRY` splits its relations:
 *
 *  - `alignment` — the CORE relations C1–C5, the construct-validity backbone:
 *    goal decomposes to LO, LO assessed by AT / practiced by TLA, TLA prepares
 *    for AT, content module supports TLA. On by default, because it is the
 *    thing worth looking at. The layer is the relation CLASS, not the
 *    establishment mechanism — C1/C5 are provenance-established but are still
 *    core alignment (the old mechanism-based rule silently hid content modules
 *    from this view).
 *  - `provenance` — the secondary relations P1–P11: traceability only, never
 *    claimed as construct-validity evidence.
 *  - `scaffolding` — the relation-less structural edges (`narrates` etc.).
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

/** The layer an edge is on. The harness ships this (`edge.layer`), read off
 *  `alignment.REGISTRY`; the prefix test below is the fallback for a payload
 *  archived before that field existed. Guessing from the id's first letter is
 *  what this replaced — a secondary relation numbered C would have landed in
 *  the alignment layer. */
export function edgeLayer(edge: GraphEdge): EdgeLayer {
  if (edge.layer) return edge.layer
  if (!edge.relation_id || edge.relation_id.startsWith('S')) return 'scaffolding'
  return edge.relation_id.startsWith('C') ? 'alignment' : 'provenance'
}

/** Element nodes carry one artifact item (`objective:LO-01`); section nodes
 *  (`objective_0`) carry a whole ADDIE section. The harness decides this
 *  (`node.kind`, from `AlignmentGraph.is_element`); the `:` test is the
 *  fallback for an archived payload. */
export function isElementNode(id: string): boolean {
  return id.includes(':')
}

function nodeKind(node: GraphNode): 'element' | 'section' {
  return node.kind ?? (isElementNode(node.id) ? 'element' : 'section')
}

/** The `id` cytoscape selects an element by. Shipped as `edge.id`; composed
 *  here only for an archived payload, in the ONE form both this file and the
 *  inspector must agree on — they did not, and a scaffolding edge opened from
 *  the inspector selected nothing. */
export function edgeId(edge: GraphEdge): string {
  return edge.id ?? `${edge.relation_id || 'scaffold'}|${edge.source}|${edge.target}|${edge.type}`
}

/** ✓/✗ per leg of the constructive-alignment triad, in the order the harness
 *  declares them — the same legs, in the same order, that the DOT export
 *  prints as `MSP`. */
export function alignmentBadge(flags: ObjectiveAlignment | undefined): string {
  if (!flags) return ''
  if (flags.legs) return flags.legs.map((leg) => (leg.ok ? '✓' : '✗')).join('')
  // Archived payload with no `legs` list: the scalars, under whichever of the
  // two names that dump used. A leg it says nothing about is left out rather
  // than shown as a ✗ — an answer that run never gave.
  return [
    flags.assessed_by ?? flags.measured,
    flags.practiced_by ?? flags.supported,
    flags.prepares_for ?? flags.prepares,
  ].filter((ok) => ok !== undefined).map((ok) => (ok ? '✓' : '✗')).join('')
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
  const violations = graph.node_violations ?? {}
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
    const badge = alignmentBadge(flags)
    present.add(node.id)
    elements.push({
      group: 'nodes',
      data: {
        id: node.id,
        // The badge rides IN the label: it is the one thing on an objective a
        // reader wants without clicking — which leg is missing — and it was
        // computed here for months while nothing rendered it, so the app said
        // only "green or amber" where the DOT export said `✓ MSP`.
        label: badge ? `${node.label ?? shortLabel(node.id, node.type)}\n${badge}`
                     : (node.label ?? shortLabel(node.id, node.type)),
        type: node.type,
      },
      classes: nodeClasses(
        node.type, nodeKind(node), flags?.aligned, flags?.bloom_ok,
        (violations[node.id] ?? []).length > 0),
    })
  }

  for (const edge of visibleEdges) {
    // Dropped rather than rendered dangling: an edge to a node that failed the
    // visibility rule above would draw into empty space.
    if (!present.has(edge.source) || !present.has(edge.target)) continue
    // An assessed_by/practiced_by edge out of an objective whose Bloom level
    // does not hold up is the single most important defect the graph can show,
    // so it is called out in red rather than left to the badge alone. The
    // harness decides it (`edge.invalid`), judging C2 on the assessment rule
    // and C3 on the activity rule; the fallback below is the archived payload's
    // coarser union, which reddened a `practiced_by` edge for a shallow ITEM.
    const sourceFlags = alignment[edge.source]
    const bloomViolation = edge.invalid ?? (
      (edge.relation_id === 'C2' || edge.relation_id === 'C3') && sourceFlags?.bloom_ok === false)

    elements.push({
      group: 'edges',
      data: {
        id: edgeId(edge),
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
        // Secondary (P*) relations render dotted, mirroring the DOT export's
        // solid-core / dotted-secondary distinction. `tier` comes from the
        // registry; the prefix is the archived-payload fallback.
        (edge.tier ?? (edge.relation_id?.startsWith('P') ? 'secondary' : '')) === 'secondary'
          ? 'secondary' : '',
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
  kind: 'element' | 'section',
  aligned?: boolean | null,
  bloomOk?: boolean | null,
  hasViolation = false,
): string {
  const classes = [`type-${type || 'unknown'}`, kind]
  if (aligned === true) classes.push('aligned')
  if (aligned === false) classes.push('unaligned')
  if (bloomOk === false) classes.push('bloom-warning')
  // `aligned`/`bloom-warning` come from `objective_alignment`, which is built
  // by walking the OBJECTIVE nodes — so an activity linked to no objective, a
  // material whose module does not exist, an item with no answer key had no
  // signal here at all. This one covers every node type.
  if (hasViolation) classes.push('has-violation')
  return classes.join(' ')
}

/** Counts for the controls, so the effect of each toggle is visible up front. */
export function layerCounts(graph: AlignmentGraphPayload | null): Record<EdgeLayer, number> {
  const counts: Record<EdgeLayer, number> = { alignment: 0, provenance: 0, scaffolding: 0 }
  for (const edge of graph?.edges ?? []) counts[edgeLayer(edge)] += 1
  return counts
}
