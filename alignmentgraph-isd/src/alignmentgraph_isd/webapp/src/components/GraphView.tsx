import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import { Eye, EyeOff, Maximize2 } from 'lucide-react'
import { buildStylesheet, LEGEND } from '../graph/stylesheet'
import { DEFAULT_FILTERS, layerCounts, toCytoscape, type GraphFilters } from '../graph/toCytoscape'
import type { AlignmentGraphPayload, GraphEdge, Selection } from '../api/types'

cytoscape.use(dagre)

interface Props {
  graph: AlignmentGraphPayload | null
  graphRev: number
  /** Which run the graph belongs to; the viewport is fitted once per run. */
  runId: string | null
  selection: Selection
  onSelect: (selection: Selection) => void
}

const LAYOUT = {
  name: 'dagre',
  // Left to right, matching the DOT export's rankdir.
  rankDir: 'LR',
  nodeSep: 18,
  rankSep: 140,
  animate: false,
  fit: false,
  padding: 30,
} as const

/** Smallest zoom at which node labels are still readable. */
const MIN_READABLE_ZOOM = 0.65

export function GraphView({ graph, graphRev, runId, selection, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const cy = useRef<cytoscape.Core | null>(null)
  const hasFitted = useRef(false)
  const [filters, setFilters] = useState<GraphFilters>(DEFAULT_FILTERS)
  const [showLegend, setShowLegend] = useState(true)

  const counts = useMemo(() => layerCounts(graph), [graph])
  const elements = useMemo(() => toCytoscape(graph, filters), [graph, filters])

  // Held in a ref so the instance below can be created exactly once. Callers
  // pass an inline handler, which changes identity on every render; as an
  // effect dependency that would tear down and rebuild the whole canvas each
  // time, and the layout would run against an instance already destroyed.
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  // Fit once per RUN, not once per mount. Selecting another run in the sidebar
  // swaps the elements under a canvas that keeps the old pan and zoom, and the
  // new graph is laid out somewhere else entirely — so without this the reader
  // switches run and gets a blank canvas over a node count that says otherwise.
  // The filters deliberately survive the switch: comparing two runs means
  // looking at both through the same one.
  useEffect(() => { hasFitted.current = false }, [runId])

  useEffect(() => {
    if (!container.current) return
    const instance = cytoscape({
      container: container.current,
      style: buildStylesheet(),
      minZoom: 0.15,
      maxZoom: 3,
    })
    cy.current = instance

    instance.on('tap', 'node', (event) => {
      selectRef.current({ kind: 'graph-node', id: event.target.id() })
    })
    instance.on('tap', 'edge', (event) => {
      const data = event.target.data()
      selectRef.current({
        kind: 'graph-edge',
        id: data.id,
        edge: {
          type: data.label,
          source: data.source,
          target: data.target,
          evidence: data.evidence ?? '',
          rationale: data.rationale ?? '',
          relation_id: data.relationId ?? '',
          established_by: data.establishedBy ?? '',
        } satisfies GraphEdge,
      })
    })
    instance.on('tap', (event) => {
      if (event.target === instance) selectRef.current({ kind: 'none' })
    })

    return () => {
      instance.destroy()
      cy.current = null
    }
  }, [])

  // Re-render on new elements. Batched, and the viewport is only fitted once:
  // re-fitting on every live update would yank the view out from under someone
  // reading it while the run is still going.
  useEffect(() => {
    const instance = cy.current
    if (!instance) return

    const timer = setTimeout(() => {
      instance.batch(() => {
        instance.elements().remove()
        instance.add(elements as cytoscape.ElementDefinition[])
      })
      if (elements.length > 0) {
        instance.layout(LAYOUT).run()
        if (!hasFitted.current) {
          instance.fit(undefined, 40)
          // A run puts most of its nodes in one rank, so the graph is tall and
          // narrow and fitting all of it shrinks the labels past reading. Below
          // this zoom, show a legible slice and let the viewer pan instead.
          if (instance.zoom() < MIN_READABLE_ZOOM) {
            instance.zoom({ level: MIN_READABLE_ZOOM, renderedPosition: { x: 0, y: 0 } })
            const objectives = instance.nodes('.type-objective.element')
            instance.center(objectives.nonempty() ? objectives : instance.nodes())
          }
          hasFitted.current = true
        }
      }
    }, 120)

    return () => clearTimeout(timer)
  }, [elements, graphRev])

  // Keep the canvas selection in step with selections made in other panels.
  useEffect(() => {
    const instance = cy.current
    if (!instance) return
    instance.elements().unselect()
    if (selection.kind === 'graph-node' || selection.kind === 'graph-edge') {
      const element = instance.getElementById(selection.id)
      if (element.nonempty()) element.select()
    }
  }, [selection])

  const visibleNodes = elements.filter((e) => e.group === 'nodes').length
  const visibleEdges = elements.filter((e) => e.group === 'edges').length

  return (
    <>
      <div className="graph-controls">
        <label>
          <input
            type="checkbox"
            checked={filters.alignment}
            onChange={(e) => setFilters({ ...filters, alignment: e.target.checked })}
          />
          Alignment ({counts.alignment})
        </label>
        <label>
          <input
            type="checkbox"
            checked={filters.provenance}
            onChange={(e) => setFilters({ ...filters, provenance: e.target.checked })}
          />
          Provenance ({counts.provenance})
        </label>
        <label>
          <input
            type="checkbox"
            checked={filters.scaffolding}
            onChange={(e) => setFilters({ ...filters, scaffolding: e.target.checked })}
          />
          Scaffolding ({counts.scaffolding})
        </label>

        <span className="muted">
          showing {visibleNodes} nodes, {visibleEdges} edges
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button className="btn small icon-label" onClick={() => cy.current?.fit(undefined, 40)}>
            <Maximize2 size={13} /> Fit
          </button>
          <button className="btn small icon-label" onClick={() => setShowLegend((v) => !v)}>
            {showLegend ? <EyeOff size={13} /> : <Eye size={13} />}
            {showLegend ? 'Hide legend' : 'Legend'}
          </button>
        </div>
      </div>

      <div className="graph-wrap">
        <div className="graph-canvas" ref={container} />

        {!graph && (
          <div className="empty" style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>
            The alignment graph appears here as the agent builds it.
          </div>
        )}

        {showLegend && graph && (
          <div className="legend">
            <div className="muted" style={{ marginBottom: 4 }}>Edges</div>
            {LEGEND.edges.map((item) => (
              <div className="legend-row" key={item.label}>
                <span className="swatch" style={{ background: item.colour }} />
                <span>{item.label}</span>
              </div>
            ))}
            <div className="muted" style={{ margin: '8px 0 4px' }}>Nodes</div>
            {LEGEND.nodes.map((item) => (
              <div className="legend-row" key={item.label}>
                <span className="swatch node" style={{ background: item.colour }} />
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
