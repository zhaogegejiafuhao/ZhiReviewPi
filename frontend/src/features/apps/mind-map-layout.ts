/**
 * Xmind 风格水平树布局算法
 *
 * 核心思路：两次遍历
 * 1. 自底向上：计算每个子树的总高度
 * 2. 自顶向下：根据子树高度分配坐标，子节点在父节点 y 范围内居中
 */

// ===== 布局参数 =====

const LEVEL_X_GAP = 240 // 层级间水平间距
const NODE_V_GAP = 50 // 同级节点垂直间距
const ROOT_X = 80 // 根节点起始 X
const ROOT_Y = 300 // 根节点起始 Y（居中）

const NODE_HEIGHTS: Record<number, number> = {
  0: 44,
  1: 36,
  2: 32,
  3: 28,
}

const NODE_MIN_WIDTHS: Record<number, number> = {
  0: 160,
  1: 120,
  2: 100,
  3: 80,
}

// ===== 类型定义 =====

export interface BackendNode {
  id: string
  name: string
  parent_id: string | null
  level: number
  keywords: string[]
  prerequisites: string[]
}

export interface MindMapNode extends BackendNode {
  x: number
  y: number
  width: number
  height: number
  group: string
}

export interface MindMapEdge {
  from: string
  to: string
  path: string
  isPrereq: boolean
}

// ===== 模块配色映射 =====

const MODULE_COLORS: Record<string, { stroke: string; light: string }> = {
  '\u6570\u4e0e\u4ee3\u6570': { stroke: '#7c3aed', light: '#a78bfa' },
  '\u56fe\u5f62\u4e0e\u51e0\u4f55': { stroke: '#059669', light: '#34d399' },
  '\u7edf\u8ba1\u4e0e\u6982\u7387': { stroke: '#ea580c', light: '#fb923c' },
  '\u7efc\u5408\u4e0e\u5b9e\u8df5': { stroke: '#475569', light: '#94a3b8' },
}

export function getModuleColor(group: string) {
  return MODULE_COLORS[group] || MODULE_COLORS['\u7efc\u5408\u4e0e\u5b9e\u8df5']
}

// ===== 布局算法 =====

function computeSubtreeHeight(
  nodeId: string,
  childrenMap: Map<string, string[]>,
  nodeMap: Map<string, BackendNode>,
  collapsedSet: Set<string>,
  cache: Map<string, number>
): number {
  if (cache.has(nodeId)) return cache.get(nodeId)!

  if (collapsedSet.has(nodeId)) {
    const level = nodeMap.get(nodeId)?.level ?? 3
    const h = NODE_HEIGHTS[level] || 28
    cache.set(nodeId, h)
    return h
  }

  const children = childrenMap.get(nodeId) || []
  if (children.length === 0) {
    const level = nodeMap.get(nodeId)?.level ?? 3
    const h = NODE_HEIGHTS[level] || 28
    cache.set(nodeId, h)
    return h
  }

  let totalHeight = 0
  for (let i = 0; i < children.length; i++) {
    totalHeight += computeSubtreeHeight(children[i], childrenMap, nodeMap, collapsedSet, cache)
    if (i < children.length - 1) {
      totalHeight += NODE_V_GAP
    }
  }

  cache.set(nodeId, totalHeight)
  return totalHeight
}

function assignCoordinates(
  nodeId: string,
  x: number,
  yCenter: number,
  childrenMap: Map<string, string[]>,
  nodeMap: Map<string, BackendNode>,
  collapsedSet: Set<string>,
  subtreeHeights: Map<string, number>,
  moduleMap: Map<string, string>,
  result: MindMapNode[]
): void {
  const node = nodeMap.get(nodeId)
  if (!node) return

  const level = node.level
  const height = NODE_HEIGHTS[level] || 28
  const width = NODE_MIN_WIDTHS[level] || 80
  const group = moduleMap.get(nodeId) || node.name

  result.push({
    ...node,
    x,
    y: yCenter - height / 2,
    width,
    height,
    group,
  })

  if (collapsedSet.has(nodeId)) return

  const children = childrenMap.get(nodeId) || []
  if (children.length === 0) return

  const childX = x + width + LEVEL_X_GAP
  let currentY = yCenter - subtreeHeights.get(nodeId)! / 2

  for (const childId of children) {
    const childSubtreeHeight = subtreeHeights.get(childId) || NODE_HEIGHTS[nodeMap.get(childId)?.level ?? 3]
    const childCenter = currentY + childSubtreeHeight / 2
    assignCoordinates(childId, childX, childCenter, childrenMap, nodeMap, collapsedSet, subtreeHeights, moduleMap, result)
    currentY += childSubtreeHeight + NODE_V_GAP
  }
}

function buildModuleMap(nodes: BackendNode[]): Map<string, string> {
  const moduleMap = new Map<string, string>()
  const modules = nodes.filter((n) => n.level === 1 && n.parent_id === 'root')
  for (const mod of modules) {
    moduleMap.set(mod.id, mod.name)
  }

  function assignGroup(nodeId: string, groupName: string) {
    const children = nodes.filter((n) => n.parent_id === nodeId)
    for (const child of children) {
      moduleMap.set(child.id, groupName)
      assignGroup(child.id, groupName)
    }
  }
  for (const mod of modules) {
    assignGroup(mod.id, mod.name)
  }

  const root = nodes.find((n) => n.level === 0)
  if (root) moduleMap.set(root.id, root.name)

  return moduleMap
}

export function computeMindMapLayout(
  nodes: BackendNode[],
  collapsedModules: Set<string> = new Set()
): MindMapNode[] {
  if (nodes.length === 0) return []

  const nodeMap = new Map<string, BackendNode>()
  for (const n of nodes) nodeMap.set(n.id, n)

  const childrenMap = new Map<string, string[]>()
  for (const n of nodes) {
    if (n.parent_id && n.parent_id !== 'root') {
      const siblings = childrenMap.get(n.parent_id) || []
      siblings.push(n.id)
      childrenMap.set(n.parent_id, siblings)
    } else if (n.parent_id === 'root') {
      const siblings = childrenMap.get('root') || []
      siblings.push(n.id)
      childrenMap.set('root', siblings)
    }
  }

  const moduleMap = buildModuleMap(nodes)

  const subtreeHeights = new Map<string, number>()
  const rootNode = nodes.find((n) => n.level === 0)
  if (rootNode) {
    computeSubtreeHeight('root', childrenMap, nodeMap, collapsedModules, subtreeHeights)
  }

  const result: MindMapNode[] = []
  if (rootNode) {
    assignCoordinates(
      'root',
      ROOT_X,
      ROOT_Y,
      childrenMap,
      nodeMap,
      collapsedModules,
      subtreeHeights,
      moduleMap,
      result
    )
  }

  // 偏移所有节点，使最小y值为正值（确保不会渲染在视口外）
  if (result.length > 0) {
    const minY = Math.min(...result.map((n) => n.y))
    if (minY < 0) {
      const offset = -minY + 40 // 40px 上边距
      for (const n of result) {
        n.y += offset
      }
    }
  }

  return result
}

export function computeBezierPath(from: MindMapNode, to: MindMapNode): string {
  const fromX = from.x + from.width
  const fromY = from.y + from.height / 2
  const toX = to.x
  const toY = to.y + to.height / 2

  const dx = toX - fromX
  const controlX1 = fromX + dx * 0.4
  const controlX2 = fromX + dx * 0.6

  return `M${fromX},${fromY} C${controlX1},${fromY} ${controlX2},${toY} ${toX},${toY}`
}

export function computeEdges(
  nodes: MindMapNode[],
  nodeMap: Map<string, MindMapNode>
): MindMapEdge[] {
  const edges: MindMapEdge[] = []
  const nodeIds = new Set(nodes.map((n) => n.id))

  for (const node of nodes) {
    if (node.parent_id && nodeIds.has(node.parent_id) && node.level >= 1) {
      const parent = nodeMap.get(node.parent_id)
      if (parent) {
        edges.push({
          from: node.parent_id,
          to: node.id,
          path: computeBezierPath(parent, node),
          isPrereq: false,
        })
      }
    }

    for (const prereqId of node.prerequisites) {
      if (nodeIds.has(prereqId)) {
        const prereq = nodeMap.get(prereqId)
        if (prereq) {
          edges.push({
            from: prereqId,
            to: node.id,
            path: computeBezierPath(prereq, node),
            isPrereq: true,
          })
        }
      }
    }
  }

  return edges
}

export function computeLayoutBounds(nodes: MindMapNode[]): {
  width: number
  height: number
  minX: number
  minY: number
  maxX: number
  maxY: number
} {
  if (nodes.length === 0) return { width: 800, height: 600, minX: 0, minY: 0, maxX: 800, maxY: 600 }

  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity

  for (const n of nodes) {
    minX = Math.min(minX, n.x)
    minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x + n.width)
    maxY = Math.max(maxY, n.y + n.height)
  }

  return {
    width: maxX - minX + 200,
    height: maxY - minY + 200,
    minX: minX - 100,
    minY: minY - 100,
    maxX: maxX + 100,
    maxY: maxY + 100,
  }
}
