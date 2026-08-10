// cytoscape-dagre ships no types. It is registered once via cytoscape.use()
// and configured through the layout options object, so a bare module
// declaration is all this needs.
declare module 'cytoscape-dagre' {
  import type { Ext } from 'cytoscape'
  const extension: Ext
  export default extension
}
