import type { StylesheetStyle } from 'cytoscape'

/**
 * The visual grammar, kept deliberately close to the package's own DOT export
 * (`core/viz.py`) so a screenshot from the app and one from `dot -Tsvg` read as
 * the same picture.
 *
 * `viz.py` only styles the seven types in `NodeType`, but a real dump contains
 * twenty — the analysis decomposition (gap, task, learner) and the design
 * scaffolding (content, media, storyboard, the various plans) are graph nodes
 * too. They get shapes here rather than falling into an undifferentiated blob.
 */

const SHAPES: Record<string, string> = {
  // Straight from viz._NODE_STYLE.
  objective: 'round-rectangle',
  assessment: 'ellipse',
  activity: 'ellipse',
  material: 'round-rectangle',
  evaluation: 'diamond',
  needs_context: 'hexagon',
  implementation_plan: 'hexagon',
  // The rest, grouped by role: analysis inputs are hexagons like their source,
  // evaluation outputs are diamonds, design scaffolding is plain rectangles.
  gap: 'hexagon',
  task: 'hexagon',
  learner: 'hexagon',
  summative: 'diamond',
  improvement: 'diamond',
  content: 'rectangle',
  media: 'rectangle',
  storyboard: 'rectangle',
  assessment_plan: 'rectangle',
  instructional_strategies: 'rectangle',
  non_instructional_strategies: 'rectangle',
  content_structure: 'rectangle',
  storyboard_plan: 'rectangle',
}

const FILLS: Record<string, string> = {
  assessment: '#dbeafe',
  activity: '#dcfce7',
  material: '#f3f4f6',
  evaluation: '#ede9fe',
  summative: '#ede9fe',
  improvement: '#f5f3ff',
  needs_context: '#f3f4f6',
  implementation_plan: '#f3f4f6',
  gap: '#fef2f2',
  task: '#f0fdfa',
  learner: '#fff7ed',
}

const FALLBACK_SHAPE = 'ellipse'
const FALLBACK_FILL = '#f3f4f6'

// Edge colour by how the relation was established, as in viz.py.
const EDGE_COLOURS = {
  id: '#16a34a',
  type: '#2563eb',
  provenance: '#9ca3af',
  none: '#d1d5db',
} as const

export function buildStylesheet(): StylesheetStyle[] {
  const typeStyles: StylesheetStyle[] = Object.keys({ ...SHAPES, ...FILLS }).map((type) => ({
    selector: `node.type-${type}`,
    style: {
      shape: (SHAPES[type] ?? FALLBACK_SHAPE) as never,
      'background-color': FILLS[type] ?? FALLBACK_FILL,
    },
  }))

  return [
    {
      selector: 'node',
      style: {
        shape: FALLBACK_SHAPE as never,
        'background-color': FALLBACK_FILL,
        label: 'data(label)',
        'font-size': 10,
        'font-family': 'ui-sans-serif, system-ui, sans-serif',
        color: '#111827',
        'text-valign': 'center',
        'text-halign': 'center',
        'text-wrap': 'wrap',
        'text-max-width': '120px',
        // Explicit rather than sized from the label: `width: 'label'` is
        // deprecated in cytoscape 3.30 and warns on every instantiation. Node
        // ids here are short and uniform (`LO-01`, `AT-03`), so a fixed box is
        // no loss and keeps the dagre ranks even.
        width: 88,
        height: 34,
        padding: '6px',
        'border-width': 1,
        'border-color': '#9ca3af',
      },
    },
    ...typeStyles,

    // Section nodes hold an entire ADDIE section; the double border says
    // "this one opens into a lot more" before you click it.
    {
      selector: 'node.section',
      style: { 'border-width': 3, 'border-style': 'double', 'border-color': '#6b7280' },
    },

    // Objectives are the spine: green when every alignment leg holds, amber
    // when one is missing. Same two colours as the DOT export.
    {
      selector: 'node.type-objective',
      style: {
        'background-color': '#e5e7eb',
        'font-weight': 'bold' as never,
        'border-color': '#4b5563',
      },
    },
    { selector: 'node.type-objective.aligned', style: { 'background-color': '#bbf7d0' } },
    { selector: 'node.type-objective.unaligned', style: { 'background-color': '#fde68a' } },
    {
      selector: 'node.bloom-warning',
      style: { 'border-color': '#dc2626', 'border-width': 2, 'border-style': 'dashed' },
    },

    {
      selector: 'edge',
      style: {
        width: 1.4,
        'line-color': EDGE_COLOURS.provenance,
        'target-arrow-color': EDGE_COLOURS.provenance,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
        'curve-style': 'bezier',
        label: 'data(label)',
        'font-size': 8,
        color: '#6b7280',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.85,
        'text-background-padding': '2px',
        'text-rotation': 'autorotate' as never,
      },
    },
    {
      selector: 'edge.by-id',
      style: { 'line-color': EDGE_COLOURS.id, 'target-arrow-color': EDGE_COLOURS.id, width: 2 },
    },
    {
      selector: 'edge.by-type',
      style: { 'line-color': EDGE_COLOURS.type, 'target-arrow-color': EDGE_COLOURS.type, width: 1.8 },
    },
    {
      selector: 'edge.by-provenance',
      style: { 'line-color': EDGE_COLOURS.provenance, 'target-arrow-color': EDGE_COLOURS.provenance },
    },
    {
      selector: 'edge.by-none',
      style: {
        'line-color': EDGE_COLOURS.none,
        'target-arrow-color': EDGE_COLOURS.none,
        'line-style': 'dotted',
        label: '',
      },
    },
    { selector: 'edge.evaluates', style: { 'line-style': 'dashed' } },
    {
      selector: 'edge.bloom-violation',
      style: {
        'line-color': '#dc2626',
        'target-arrow-color': '#dc2626',
        'line-style': 'dashed',
        width: 2.4,
      },
    },

    { selector: 'node:selected', style: { 'border-width': 4, 'border-color': '#2563eb' } },
    { selector: 'edge:selected', style: { width: 4, 'line-color': '#2563eb' } },
    // Dimming rather than hiding on hover-focus: position is information too.
    { selector: '.dimmed', style: { opacity: 0.15 } },
  ]
}

export const LEGEND = {
  edges: [
    { label: 'measures / supports / evaluates (matched ids)', colour: EDGE_COLOURS.id },
    { label: 'realises (matched types)', colour: EDGE_COLOURS.type },
    { label: 'provenance (derived from)', colour: EDGE_COLOURS.provenance },
    { label: 'Bloom mismatch on a measures edge', colour: '#dc2626' },
  ],
  nodes: [
    { label: 'objective, fully aligned', colour: '#bbf7d0' },
    { label: 'objective, missing a leg', colour: '#fde68a' },
    { label: 'assessment', colour: '#dbeafe' },
    { label: 'activity', colour: '#dcfce7' },
    { label: 'evaluation / summative', colour: '#ede9fe' },
  ],
}
