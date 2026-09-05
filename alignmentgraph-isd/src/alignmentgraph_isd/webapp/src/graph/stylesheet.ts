import type { StylesheetStyle } from 'cytoscape'

/**
 * The visual grammar, kept deliberately close to the package's own DOT export
 * (`core/alignment_graph/viz.py`) so a screenshot from the app and one from
 * `dot -Tsvg` read as the same picture.
 *
 * The type list mirrors `NodeType` exactly: the five core types (course goal,
 * objective, assessment, activity, content — the C1–C5 participants; the sixth
 * was RUBRIC, retired 2026-09-02)
 * plus the support types the P-relations touch. Cytoscape has no folder/note
 * shapes, so those map to the closest available polygon.
 */

const SHAPES: Record<string, string> = {
  // Core types, straight from viz._NODE_STYLE.
  course_goal: 'diamond',
  objective: 'round-rectangle',
  assessment: 'ellipse',
  activity: 'ellipse',
  content: 'rectangle', // viz: folder
  // Support types (visible mostly with the provenance layer on): analysis
  // inputs are hexagons, evaluation outputs diamonds, plans plain rectangles.
  gap: 'hexagon',
  topic: 'hexagon',
  learner_profile: 'hexagon',
  constraint: 'hexagon',
  improvement: 'diamond',
  media_selection: 'rectangle',
  material: 'rectangle', // viz: folder
  assessment_plan: 'rectangle',
  activity_plan: 'rectangle',
  implementation_plan: 'hexagon', // viz: component
}

const FILLS: Record<string, string> = {
  course_goal: '#fef3c7',
  assessment: '#dbeafe',
  activity: '#dcfce7',
  content: '#f3f4f6',
  material: '#f3f4f6',
  implementation_plan: '#f3f4f6',
  gap: '#fef2f2',
  topic: '#f0fdfa',
  learner_profile: '#fff7ed',
  constraint: '#fefce8',
  improvement: '#f5f3ff',
  media_selection: '#f3f4f6',
  assessment_plan: '#f3f4f6',
  activity_plan: '#f3f4f6',
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
    // ANY node carrying ANY violation. The two rules above are driven by
    // `objective_alignment`, which is built by walking the objective nodes —
    // so an activity linked to no objective, a material whose module does not
    // exist, an item with no answer key had no signal on this graph at all.
    // Amber rather than the Bloom red: it is "something is wrong here", not
    // the specific alignment failure above it, and a node can carry both.
    {
      selector: 'node.has-violation',
      style: { 'border-color': '#d97706', 'border-width': 2, 'border-style': 'dashed' },
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
    // Secondary (P1–P11) relations: dotted, as in the DOT export — core
    // relations stay solid so the constructive-alignment backbone reads first.
    { selector: 'edge.secondary', style: { 'line-style': 'dotted' } },
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

// Edge colour = HOW the relation was established (the evidence mechanism);
// the Alignment/Provenance toggles = WHICH relation class (C1–C5 core vs
// P1–P11 secondary, solid vs dotted). The two axes are independent: C1/C5/C6
// are core yet provenance-established, so a grey edge can still be core.
export const LEGEND = {
  edges: [
    { label: 'established by matched ids (assessed_by / practiced_by / prepares_for)', colour: EDGE_COLOURS.id },
    { label: 'established by matched types (realizes)', colour: EDGE_COLOURS.type },
    { label: 'established by provenance (decomposes_to / supports, …)', colour: EDGE_COLOURS.provenance },
    { label: 'Bloom mismatch on an assessed_by / practiced_by edge', colour: '#dc2626' },
  ],
  nodes: [
    { label: 'objective (LO), fully aligned', colour: '#bbf7d0' },
    { label: 'objective (LO), missing a leg', colour: '#fde68a' },
    { label: 'course goal', colour: '#fef3c7' },
    { label: 'assessment task (AT)', colour: '#dbeafe' },
    { label: 'activity (TLA)', colour: '#dcfce7' },
    { label: 'content module / material', colour: '#f3f4f6' },
  ],
}
