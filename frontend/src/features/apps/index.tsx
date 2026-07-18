import { useEffect, useMemo, useState } from 'react'
import { Download, FileText, Loader2, ChevronDown, ChevronRight, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { useRole } from '@/context/role-provider'
import { analyzeKnowledge, exportReport, getKnowledgeGraph, getPrecomputedGraph, type KnowledgeGraphResponse, type PrecomputedGraphResponse } from '@/lib/api'
import { StudentApps } from '@/features/student/apps'
import { TransformWrapper, TransformComponent, useControls, type ReactZoomPanPinchRef } from 'react-zoom-pan-pinch'
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts'
import { computeMindMapLayout, computeEdges, computeLayoutBounds, getModuleColor, type MindMapNode, type MindMapEdge, type BackendNode as LayoutBackendNode } from './mind-map-layout'

// ===== 类型定义 =====

interface WeakPointDisplay {
  name: string
  weakness: number
  errorCount: number
  lastError: string
  knowledgeId?: string
  errorCauseDistribution?: Record<string, number>
  suggestion?: string
}

interface BackendWeakPoint {
  knowledge_id: string
  knowledge_name: string
  weakness_score: number
  error_count: number
  recent_errors: Array<{ question: string; date: string }>
  suggestion: string
  error_cause_distribution: Record<string, number>
}

interface KnowledgeAnalysisResponse {
  weak_points: BackendWeakPoint[]
  radar?: Record<string, number>
}

// ===== 常量 =====

// 默认薄弱点示例数据（后端不可用时的 fallback）
const defaultWeakPoints: WeakPointDisplay[] = [
  { name: '相似三角形', weakness: 78, errorCount: 12, lastError: '2025-07-14' },
  { name: '二次函数', weakness: 65, errorCount: 9, lastError: '2025-07-13' },
  { name: '几何证明', weakness: 58, errorCount: 7, lastError: '2025-07-12' },
  { name: '一元一次不等式', weakness: 45, errorCount: 5, lastError: '2025-07-11' },
  { name: '数据收集', weakness: 32, errorCount: 3, lastError: '2025-07-10' },
]

// ===== 工具函数 =====

function getWeaknessColor(weakness: number) {
  if (weakness >= 70) return 'text-red-600'
  if (weakness >= 50) return 'text-orange-500'
  return 'text-yellow-500'
}

function getWeaknessBadgeVariant(weakness: number): 'destructive' | 'secondary' | 'outline' {
  if (weakness >= 70) return 'destructive'
  if (weakness >= 50) return 'secondary'
  return 'outline'
}

function mapBackendWeakPoint(wp: BackendWeakPoint): WeakPointDisplay {
  return {
    name: wp.knowledge_name,
    weakness: Math.round(wp.weakness_score * 100),
    errorCount: wp.error_count,
    lastError: wp.recent_errors?.[0]?.date || '—',
    knowledgeId: wp.knowledge_id,
    errorCauseDistribution: wp.error_cause_distribution,
    suggestion: wp.suggestion,
  }
}

// ===== 缩放工具栏组件 =====

function ZoomToolbar() {
  const { zoomIn, zoomOut, resetTransform } = useControls<ReactZoomPanPinchRef>()
  return (
    <div className='absolute right-3 top-3 z-10 flex flex-col gap-1'>
      <Button size='icon' variant='outline' className='h-8 w-8' onClick={() => zoomIn()}>
        <ZoomIn className='h-4 w-4' />
      </Button>
      <Button size='icon' variant='outline' className='h-8 w-8' onClick={() => zoomOut()}>
        <ZoomOut className='h-4 w-4' />
      </Button>
      <Button size='icon' variant='outline' className='h-8 w-8' onClick={() => resetTransform()}>
        <RotateCcw className='h-4 w-4' />
      </Button>
    </div>
  )
}

// ===== 主组件 =====

export function Apps() {
  const { role } = useRole()

  // ---- 知识图谱数据 ----
  const [mindMapNodes, setMindMapNodes] = useState<MindMapNode[]>([])
  const [edges, setEdges] = useState<MindMapEdge[]>([])
  const [precomputedData, setPrecomputedData] = useState<PrecomputedGraphResponse | null>(null)
  const [graphLoading, setGraphLoading] = useState(true)
  const [graphError, setGraphError] = useState<string | null>(null)
  const [backendNodeArray, setBackendNodeArray] = useState<LayoutBackendNode[]>([])

  // ---- 薄弱点数据 ----
  const [weakPointsData, setWeakPointsData] = useState<WeakPointDisplay[]>(defaultWeakPoints)
  const [weakKnowledgeIds, setWeakKnowledgeIds] = useState<Set<string>>(new Set())
  const [radarData, setRadarData] = useState<Array<{ module: string; score: number; fullMark: number }>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // ---- 交互状态 ----
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [collapsedModules, setCollapsedModules] = useState<Set<string>>(new Set())
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)
  const [exportMsg, setExportMsg] = useState<string | null>(null)

  // ---- 折叠模块 ----
  const toggleModule = (moduleId: string) => {
    setCollapsedModules((prev) => {
      const next = new Set(prev)
      if (next.has(moduleId)) next.delete(moduleId)
      else next.add(moduleId)
      return next
    })
  }

  // ---- 加载知识图谱数据 ----
  const loadGraphData = async () => {
    setGraphLoading(true)
    setGraphError(null)
    try {
      const [graphRes, precomputed] = await Promise.all([
        getKnowledgeGraph(),
        getPrecomputedGraph(),
      ])

      const nodeArray = Object.values(graphRes.nodes)
      setBackendNodeArray(nodeArray)
      const layout = computeMindMapLayout(nodeArray, collapsedModules)
      const visibleNodeMap = new Map(layout.map((n) => [n.id, n]))
      const computedEdges = computeEdges(layout, visibleNodeMap)

      setMindMapNodes(layout)
      setEdges(computedEdges)
      setPrecomputedData(precomputed)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误'
      setGraphError(`知识图谱加载失败：${msg}`)
    } finally {
      setGraphLoading(false)
    }
  }

  // ---- 加载薄弱点数据 ----
  const loadWeakPoints = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = (await analyzeKnowledge('stu_demo_001')) as KnowledgeAnalysisResponse
      const backendWeakPoints = data?.weak_points ?? []
      if (backendWeakPoints.length > 0) {
        const mapped = backendWeakPoints.map(mapBackendWeakPoint)
        setWeakPointsData(mapped)
        setWeakKnowledgeIds(new Set(backendWeakPoints.map((wp) => wp.knowledge_id)))
      } else {
        setError('后端返回空数据，已展示示例数据供参考')
      }

      // 雷达图数据
      const idToName: Record<string, string> = {
        num_algebra: '数与代数',
        geometry: '图形与几何',
        stats_prob: '统计与概率',
        comprehensive: '综合与实践',
      }
      if (data?.radar && Object.keys(data.radar).length > 0) {
        const radarArr = Object.entries(data.radar).map(([k, v]) => ({
          module: idToName[k] || k,
          score: Math.round(v * 100),
          fullMark: 100,
        }))
        setRadarData(radarArr)
      } else {
        // 无真实雷达数据时使用示例数据
        setRadarData([
          { module: '数与代数', score: 45, fullMark: 100 },
          { module: '图形与几何', score: 68, fullMark: 100 },
          { module: '统计与概率', score: 30, fullMark: 100 },
          { module: '综合与实践', score: 25, fullMark: 100 },
        ])
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误'
      setError(`无法连接后端：${msg}。当前展示示例数据`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadGraphData()
    loadWeakPoints()
  }, [])

  // ---- collapsedModules 变化时重新计算布局 ----
  useEffect(() => {
    if (backendNodeArray.length > 0) {
      const layout = computeMindMapLayout(backendNodeArray, collapsedModules)
      setMindMapNodes(layout)
    }
  }, [collapsedModules])

  // ---- 选中节点的归因路径 ----
  const attributionPath = useMemo(() => {
    if (!selectedNodeId || !precomputedData) return []
    const ancestors = precomputedData.ancestors[selectedNodeId] || []
    const path: Array<{ id: string; name: string; propagationType: string }> = []
    const selectedNode = mindMapNodes.find((n) => n.id === selectedNodeId)
    if (selectedNode) {
      path.push({ id: selectedNodeId, name: selectedNode.name, propagationType: '直接薄弱' })
    }
    for (const ancestorId of ancestors) {
      const ancestor = mindMapNodes.find((n) => n.id === ancestorId)
      if (ancestor) {
        path.push({ id: ancestorId, name: ancestor.name, propagationType: '传播薄弱' })
      }
    }
    return path
  }, [selectedNodeId, precomputedData, mindMapNodes])

  // 归因路径上需要高亮的边
  const highlightedEdgeKeys = useMemo(() => {
    if (!selectedNodeId || attributionPath.length <= 1) return new Set<string>()
    const keys = new Set<string>()
    for (let i = 0; i < attributionPath.length - 1; i++) {
      keys.add(`${attributionPath[i].id}-${attributionPath[i + 1].id}`)
      keys.add(`${attributionPath[i + 1].id}-${attributionPath[i].id}`)
    }
    return keys
  }, [selectedNodeId, attributionPath])

  // 归因路径上的节点ID集合
  const highlightedNodeIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>()
    return new Set(attributionPath.map((p) => p.id))
  }, [selectedNodeId, attributionPath])

  // ---- 可见节点与边 ----
  // 折叠过滤已在布局算法中完成，直接使用 mindMapNodes
  const visibleNodes = mindMapNodes
  const visibleNodeMap = useMemo(() => {
    return new Map(visibleNodes.map((n) => [n.id, n]))
  }, [visibleNodes])

  const visibleEdges = useMemo(() => {
    const visibleIds = new Set(visibleNodes.map((n) => n.id))
    return edges.filter((e) => visibleIds.has(e.from) && visibleIds.has(e.to))
  }, [edges, visibleNodes])

  // 布局边界
  const bounds = useMemo(() => computeLayoutBounds(visibleNodes), [visibleNodes])

  // ---- 选中节点详情 ----
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null
    return mindMapNodes.find((n) => n.id === selectedNodeId) || null
  }, [selectedNodeId, mindMapNodes])

  const selectedWeakPoint = useMemo(() => {
    if (!selectedNodeId) return null
    return weakPointsData.find((wp) => wp.knowledgeId === selectedNodeId) || null
  }, [selectedNodeId, weakPointsData])

  // ---- 导出报告 ----
  const handleExport = async (format: 'json' | 'csv' | 'word' | 'pdf') => {
    setExporting(format)
    setExportMsg(null)
    try {
      const blob = await exportReport('stu_demo_001', format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report_stu_demo_001.${format === 'word' ? 'docx' : format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setExportMsg(`✓ ${format.toUpperCase()} 报告已下载`)
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : '导出失败，请检查后端是否启动或有足够错题数据'
      setExportMsg(`✗ ${msg}`)
    } finally {
      setExporting(null)
      setTimeout(() => setExportMsg(null), 5000)
    }
  }

  // 学生端渲染
  if (role === 'student') {
    return (
      <>
        <Header>
          <Search className='me-auto' />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </Header>
        <Main>
          <StudentApps />
        </Main>
      </>
    )
  }

  return (
    <>
      <Header>
        <Search className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main className='space-y-6'>
        <div className='mb-2'>
          <h1 className='text-2xl font-bold tracking-tight'>知识归因分析</h1>
          <p className='text-muted-foreground'>基于DecayPropagate算法的知识薄弱点溯源</p>
        </div>

        <Tabs defaultValue='graph' className='space-y-4'>
          <TabsList>
            <TabsTrigger value='graph'>知识图谱</TabsTrigger>
            <TabsTrigger value='weakness'>薄弱点分析</TabsTrigger>
            <TabsTrigger value='report'>归因报告</TabsTrigger>
          </TabsList>

          {/* ===== 知识图谱 Tab ===== */}
          <TabsContent value='graph' className='space-y-4'>
            <Card>
              <CardHeader>
                <div className='flex items-center justify-between'>
                  <div>
                    <CardTitle>初中数学知识图谱（{mindMapNodes.length}节点）</CardTitle>
                    <CardDescription>
                      Xmind风格思维导图 · 鼠标滚轮缩放 · 拖拽平移 · 点击模块节点展开/收起
                    </CardDescription>
                  </div>
                  <Button variant='outline' size='sm' onClick={loadGraphData} disabled={graphLoading}>
                    {graphLoading ? <Loader2 className='mr-1 h-3 w-3 animate-spin' /> : null}
                    刷新图谱
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {graphLoading ? (
                  <div className='flex h-96 items-center justify-center'>
                    <Loader2 className='h-8 w-8 animate-spin text-muted-foreground' />
                    <span className='ml-2 text-muted-foreground'>加载知识图谱...</span>
                  </div>
                ) : graphError ? (
                  <div className='flex h-48 flex-col items-center justify-center gap-3 rounded-lg border border-dashed text-muted-foreground'>
                    <span className='text-red-500'>{graphError}</span>
                    <Button variant='outline' size='sm' onClick={loadGraphData}>重试</Button>
                  </div>
                ) : (
                  <div className='relative overflow-hidden rounded-lg border bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900/50 dark:to-slate-800/50' style={{ height: 600 }}>
                    <TransformWrapper
                      initialScale={0.7}
                      minScale={0.2}
                      maxScale={3}
                      centerOnInit
                      wheel={{ step: 0.1 }}
                      doubleClick={{ disabled: true }}
                    >
                      <TransformComponent
                        wrapperStyle={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}
                        contentStyle={{ width: bounds.width, height: bounds.height, position: 'relative' }}
                      >
                        {/* SVG curves layer */}
                        <svg
                          style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible', pointerEvents: 'none' }}
                          width={bounds.width}
                          height={bounds.height}
                        >
                          {visibleEdges.map((edge, i) => {
                            const isHighlighted = highlightedEdgeKeys.has(`${edge.from}-${edge.to}`)
                            const isWeakEdge = weakKnowledgeIds.has(edge.from) || weakKnowledgeIds.has(edge.to)
                            const fromNode = visibleNodeMap.get(edge.from)
                            const moduleColor = fromNode ? getModuleColor(fromNode.group) : null

                            return (
                              <path
                                key={`edge-${i}`}
                                d={edge.path}
                                fill='none'
                                stroke={isHighlighted ? '#3b82f6' : isWeakEdge ? '#ef4444' : moduleColor?.light || '#94a3b8'}
                                strokeWidth={isHighlighted ? 3 : isWeakEdge ? 2 : 1.5}
                                strokeOpacity={isHighlighted ? 0.9 : isWeakEdge ? 0.6 : 0.4}
                                strokeDasharray={edge.isPrereq ? '6 3' : 'none'}
                              />
                            )
                          })}
                        </svg>

                        {/* HTML nodes layer */}
                        {visibleNodes.map((node) => {
                          const isWeak = weakKnowledgeIds.has(node.id)
                          const isSelected = selectedNodeId === node.id
                          const isInPath = highlightedNodeIds.has(node.id)
                          const isModuleNode = node.level === 1
                          const isCollapsed = collapsedModules.has(node.id)
                          const color = getModuleColor(node.group)

                          return (
                            <div
                              key={node.id}
                              style={{
                                position: 'absolute',
                                left: node.x,
                                top: node.y,
                                minWidth: node.width,
                                height: node.height,
                                borderLeftWidth: node.level >= 1 ? 3 : 0,
                                borderLeftColor: node.level >= 1 ? color.stroke : undefined,
                              }}
                              className={`
                                flex items-center justify-center gap-1 px-3 cursor-pointer select-none
                                transition-all duration-150 hover:brightness-110
                                ${node.level === 0 ? 'rounded-xl text-[15px] font-bold' :
                                  node.level === 1 ? 'rounded-lg text-[13px] font-semibold' :
                                  node.level === 2 ? 'rounded-md text-[12px] font-medium' :
                                  'rounded-md text-[11px]'}
                                ${isSelected ? 'ring-2 ring-blue-500 shadow-lg shadow-blue-200' : ''}
                                ${isInPath && !isSelected ? 'ring-2 ring-blue-300' : ''}
                                ${isWeak ? 'border-2 border-red-400 bg-red-50 dark:bg-red-950/30' :
                                  isInPath ? 'bg-blue-50 dark:bg-blue-950/30' :
                                  node.level === 0 ? 'bg-slate-700 text-white dark:bg-slate-800' :
                                  `bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700`}
                              `}
                              onClick={() => {
                                if (isModuleNode) {
                                  toggleModule(node.id)
                                } else {
                                  setSelectedNodeId(isSelected ? null : node.id)
                                }
                              }}
                              onMouseEnter={() => setHoveredNodeId(node.id)}
                              onMouseLeave={() => setHoveredNodeId(null)}
                            >
                              {/* Left color bar for module/chapter/knowledge nodes */}
                              {node.level >= 1 && (
                                <div
                                  className='absolute left-0 top-0 bottom-0 w-[3px] rounded-l-md'
                                  style={{ backgroundColor: color.stroke }}
                                />
                              )}

                              <span className='truncate px-2 text-center'>
                                {node.name}
                              </span>

                              {/* Module collapse icon */}
                              {isModuleNode && (
                                isCollapsed ? <ChevronRight className='h-3 w-3 shrink-0 opacity-50' /> : <ChevronDown className='h-3 w-3 shrink-0 opacity-50' />
                              )}

                              {/* Weak point badge */}
                              {isWeak && (
                                <Badge variant='destructive' className='ml-1 h-4 px-1 text-[9px]'>薄弱</Badge>
                              )}
                            </div>
                          )
                        })}
                      </TransformComponent>

                      {/* Zoom toolbar */}
                      <ZoomToolbar />
                    </TransformWrapper>
                  </div>
                )}

                {/* 归因路径卡片 */}
                {selectedNode && attributionPath.length > 1 && (
                  <div className='mt-4 rounded-lg border-2 border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20'>
                    <div className='mb-2 flex items-center justify-between'>
                      <div className='flex items-center gap-2'>
                        <span className='text-sm font-semibold text-blue-700 dark:text-blue-300'>
                          归因路径
                        </span>
                        <Badge variant='outline' className='text-xs'>
                          {attributionPath.length} 个节点
                        </Badge>
                      </div>
                      <Button
                        variant='ghost'
                        size='sm'
                        onClick={() => setSelectedNodeId(null)}
                      >
                        ×
                      </Button>
                    </div>
                    <div className='flex flex-wrap items-center gap-1 text-sm'>
                      {attributionPath.map((p, i) => (
                        <span key={p.id} className='flex items-center gap-1'>
                          <span
                            className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                              i === 0
                                ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                                : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                            }`}
                          >
                            {p.name}
                            <span className='ml-1 opacity-60'>
                              ({p.propagationType})
                            </span>
                          </span>
                          {i < attributionPath.length - 1 && (
                            <span className='text-muted-foreground'>←</span>
                          )}
                        </span>
                      ))}
                    </div>
                    {selectedWeakPoint?.suggestion && (
                      <div className='mt-2 text-xs text-muted-foreground'>
                        💡 {selectedWeakPoint.suggestion}
                      </div>
                    )}
                  </div>
                )}

                {/* 选中节点详情 */}
                {selectedNode && (
                  <div className='mt-4 rounded-lg border-2 border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20'>
                    <div className='flex items-center justify-between'>
                      <div className='flex items-center gap-2'>
                        <span className='text-lg font-bold'>{selectedNode.name}</span>
                        <Badge
                          variant={weakKnowledgeIds.has(selectedNode.id) ? 'destructive' : 'outline'}
                        >
                          {weakKnowledgeIds.has(selectedNode.id) ? '薄弱节点' : '正常节点'}
                        </Badge>
                      </div>
                      <Button
                        variant='ghost'
                        size='sm'
                        onClick={() => setSelectedNodeId(null)}
                      >
                        ×
                      </Button>
                    </div>
                    <div className='mt-2 space-y-1 text-sm text-muted-foreground'>
                      <div>节点ID: <span className='font-mono'>{selectedNode.id}</span></div>
                      <div>所属模块: <span className='font-medium'>{selectedNode.group}</span></div>
                      <div>层级: <span className='font-medium'>
                        {selectedNode.level === 1 ? '模块' : selectedNode.level === 2 ? '章节' : '知识点'}
                      </span></div>
                      {selectedNode.prerequisites.length > 0 && (
                        <div>前置依赖: <span className='font-mono text-xs'>{selectedNode.prerequisites.join(', ')}</span></div>
                      )}
                      {selectedWeakPoint && (
                        <>
                          <div>薄弱度: <span className={`font-medium ${getWeaknessColor(selectedWeakPoint.weakness)}`}>
                            {selectedWeakPoint.weakness}%
                          </span></div>
                          <div>错题数量: <span className='font-medium'>{selectedWeakPoint.errorCount} 道</span></div>
                          {selectedWeakPoint.errorCauseDistribution && Object.keys(selectedWeakPoint.errorCauseDistribution).length > 0 && (
                            <div>错因分布:
                              <span className='ml-1 text-xs'>
                                {Object.entries(selectedWeakPoint.errorCauseDistribution)
                                  .map(([cause, count]) => `${cause}(${count})`)
                                  .join('、')}
                              </span>
                            </div>
                          )}
                        </>
                      )}
                      <div>
                        状态:
                        {weakKnowledgeIds.has(selectedNode.id) ? (
                          <span className='ml-1 font-medium text-red-600'>
                            该知识点为学生薄弱点，建议重点复习
                          </span>
                        ) : (
                          <span className='ml-1 font-medium text-green-600'>
                            该知识点掌握情况良好
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* 操作提示 */}
                {!selectedNode && (
                  <div className='mt-4 flex items-center justify-center gap-2 text-xs text-muted-foreground'>
                    <span className='inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500' />
                    点击薄弱节点查看归因路径，点击模块节点展开/收起
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ===== 薄弱点分析 Tab ===== */}
          <TabsContent value='weakness' className='space-y-4'>
            {/* 雷达图 */}
            {radarData.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>知识模块薄弱度雷达图</CardTitle>
                  <CardDescription>
                    各学科模块的综合薄弱度（0=完全掌握，100=极度薄弱）
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className='h-[300px] w-full'>
                    <ResponsiveContainer width='100%' height='100%'>
                      <RadarChart data={radarData} cx='50%' cy='50%' outerRadius='70%'>
                        <PolarGrid strokeDasharray='3 3' />
                        <PolarAngleAxis
                          dataKey='module'
                          tick={{ fontSize: 12, fill: 'currentColor' }}
                        />
                        <PolarRadiusAxis
                          angle={90}
                          domain={[0, 100]}
                          tick={{ fontSize: 10 }}
                        />
                        <Radar
                          name='薄弱度'
                          dataKey='score'
                          stroke='#ef4444'
                          fill='#ef4444'
                          fillOpacity={0.2}
                          strokeWidth={2}
                        />
                        <RechartsTooltip
                          formatter={(value: number) => [`${value}%`, '薄弱度']}
                          contentStyle={{
                            borderRadius: '8px',
                            fontSize: '12px',
                          }}
                        />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 错误提示条 */}
            {error && !loading && (
              <div className='flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-900/20'>
                <div className='flex items-center gap-2 text-amber-700 dark:text-amber-300'>
                  <span>⚠</span>
                  <span>{error}</span>
                </div>
                <Button variant='outline' size='sm' onClick={loadWeakPoints}>
                  重试
                </Button>
              </div>
            )}

            {loading ? (
              // 骨架屏
              <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Card key={i}>
                    <CardHeader>
                      <div className='flex items-center justify-between'>
                        <div className='h-4 w-24 animate-pulse rounded bg-muted' />
                        <div className='h-5 w-16 animate-pulse rounded-full bg-muted' />
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className='space-y-3'>
                        <div>
                          <div className='mb-1 flex items-center justify-between'>
                            <div className='h-3 w-20 animate-pulse rounded bg-muted' />
                            <div className='h-3 w-8 animate-pulse rounded bg-muted' />
                          </div>
                          <div className='h-2 w-full animate-pulse rounded-full bg-muted' />
                        </div>
                        <div className='flex items-center justify-between'>
                          <div className='h-3 w-16 animate-pulse rounded bg-muted' />
                          <div className='h-3 w-10 animate-pulse rounded bg-muted' />
                        </div>
                        <div className='flex items-center justify-between'>
                          <div className='h-3 w-16 animate-pulse rounded bg-muted' />
                          <div className='h-3 w-20 animate-pulse rounded bg-muted' />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : weakPointsData.length === 0 ? (
              // 空状态
              <div className='flex h-48 flex-col items-center justify-center gap-3 rounded-lg border border-dashed text-muted-foreground'>
                <FileText className='h-12 w-12 opacity-40' />
                <div className='text-center'>
                  <p className='font-medium'>暂无薄弱点数据</p>
                  <p className='mt-1 text-xs'>
                    学生完成作业后，薄弱点将自动归因显示
                  </p>
                </div>
                <Button variant='outline' size='sm' onClick={loadWeakPoints}>
                  重新加载
                </Button>
              </div>
            ) : (
              <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
                {weakPointsData.map((point) => (
                  <Card
                    key={point.name}
                    className={`transition-shadow hover:shadow-md cursor-pointer ${
                      selectedNodeId === point.knowledgeId ? 'ring-2 ring-blue-400' : ''
                    }`}
                    onClick={() => {
                      if (point.knowledgeId) setSelectedNodeId(point.knowledgeId)
                    }}
                  >
                    <CardHeader>
                      <div className='flex items-center justify-between'>
                        <CardTitle className='text-base'>{point.name}</CardTitle>
                        <Badge variant={getWeaknessBadgeVariant(point.weakness)}>
                          薄弱度 {point.weakness}%
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className='space-y-3'>
                        {/* 薄弱度进度条 */}
                        <div>
                          <div className='mb-1 flex items-center justify-between text-sm'>
                            <span className='text-muted-foreground'>薄弱程度</span>
                            <span className={`font-medium ${getWeaknessColor(point.weakness)}`}>
                              {point.weakness}%
                            </span>
                          </div>
                          <div className='h-2 w-full rounded-full bg-muted'>
                            <div
                              className={`h-2 rounded-full transition-all duration-500 ${
                                point.weakness >= 70
                                  ? 'bg-red-500'
                                  : point.weakness >= 50
                                    ? 'bg-orange-400'
                                    : 'bg-yellow-400'
                              }`}
                              style={{ width: `${point.weakness}%` }}
                            />
                          </div>
                        </div>
                        <div className='flex items-center justify-between text-sm'>
                          <span className='text-muted-foreground'>错题数量</span>
                          <span className='font-medium'>{point.errorCount} 道</span>
                        </div>
                        <div className='flex items-center justify-between text-sm'>
                          <span className='text-muted-foreground'>最近错误</span>
                          <span className='font-medium'>{point.lastError}</span>
                        </div>
                        {point.errorCauseDistribution && Object.keys(point.errorCauseDistribution).length > 0 && (
                          <div className='text-xs text-muted-foreground'>
                            错因: {Object.entries(point.errorCauseDistribution)
                              .map(([cause, count]) => `${cause}(${count})`)
                              .join('、')}
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ===== 归因报告 Tab ===== */}
          <TabsContent value='report' className='space-y-4'>
            {/* 导出报告卡片 */}
            <Card>
              <CardHeader>
                <CardTitle className='flex items-center gap-2'>
                  <Download className='h-5 w-5' />
                  导出学情报告
                </CardTitle>
                <CardDescription>
                  支持 4 种格式导出，调用后端 /api/v1/export/{'{student_id}'}/{'{format}'} 接口
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className='flex flex-wrap gap-2'>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => handleExport('json')}
                    disabled={exporting !== null}
                  >
                    {exporting === 'json' ? (
                      <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                    ) : (
                      <FileText className='mr-1 h-3 w-3' />
                    )}
                    JSON
                  </Button>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => handleExport('csv')}
                    disabled={exporting !== null}
                  >
                    {exporting === 'csv' ? (
                      <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                    ) : (
                      <FileText className='mr-1 h-3 w-3' />
                    )}
                    CSV
                  </Button>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => handleExport('word')}
                    disabled={exporting !== null}
                  >
                    {exporting === 'word' ? (
                      <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                    ) : (
                      <FileText className='mr-1 h-3 w-3' />
                    )}
                    Word
                  </Button>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => handleExport('pdf')}
                    disabled={exporting !== null}
                  >
                    {exporting === 'pdf' ? (
                      <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                    ) : (
                      <FileText className='mr-1 h-3 w-3' />
                    )}
                    PDF
                  </Button>
                </div>
                {exportMsg && (
                  <div
                    className={`mt-3 rounded-md p-2 text-sm ${
                      exportMsg.startsWith('✓')
                        ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300'
                        : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'
                    }`}
                  >
                    {exportMsg}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>DecayPropagate 算法说明</CardTitle>
                <CardDescription>
                  基于知识图谱的知识薄弱点溯源算法
                </CardDescription>
              </CardHeader>
              <CardContent className='space-y-6'>
                <div className='space-y-2'>
                  <h3 className='font-semibold'>1. 时间衰减（Temporal Decay）</h3>
                  <p className='text-sm text-muted-foreground'>
                    对学生的每次错误记录引入指数时间衰减因子，距离当前时间越近的错误权重越大，
                    早期错误的影响逐渐衰减。衰减公式：w(t) = e<sup>-λΔt</sup>，其中 λ 为衰减系数，
                    Δt 为距今天数。这使得算法更关注近期的学习状态，避免历史错误对归因结果的过度影响。
                  </p>
                </div>
                <div className='space-y-2'>
                  <h3 className='font-semibold'>2. 后向传播（Backward Propagation）</h3>
                  <p className='text-sm text-muted-foreground'>
                    沿知识图谱的依赖边从下游节点向根节点传播薄弱信号。如果学生在一个高级知识点（如"相似三角形"）上表现薄弱，
                    算法会将薄弱度按照边的权重向上游传播至其前置知识（如"三角形"、"全等三角形"），
                    从而发现导致薄弱的深层原因。
                  </p>
                </div>
                <div className='space-y-2'>
                  <h3 className='font-semibold'>3. 前向聚合（Forward Aggregation）</h3>
                  <p className='text-sm text-muted-foreground'>
                    将各路径传播来的薄弱信号进行聚合，计算每个知识点的综合薄弱度。
                    聚合采用加权求和策略，综合考虑直接薄弱度和传播薄弱度，
                    最终输出排序后的薄弱知识点列表及归因路径。
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>归因结果示例</CardTitle>
                <CardDescription>
                  以"相似三角形"薄弱点为例的归因分析
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className='space-y-4'>
                  <div className='rounded-lg border p-4'>
                    <div className='mb-2 flex items-center gap-2'>
                      <Badge variant='destructive'>目标薄弱点</Badge>
                      <span className='font-semibold'>相似三角形</span>
                      <span className='text-sm text-muted-foreground'>(薄弱度 78%)</span>
                    </div>
                    <div className='space-y-2 text-sm'>
                      <div className='flex items-center gap-2'>
                        <span className='text-muted-foreground'>直接错误：</span>
                        <span>错题 12 道，近期错误集中</span>
                      </div>
                      <div className='flex items-center gap-2'>
                        <span className='text-muted-foreground'>归因路径1：</span>
                        <span>相似三角形 ← 全等三角形 (传播薄弱度 35%)</span>
                      </div>
                      <div className='flex items-center gap-2'>
                        <span className='text-muted-foreground'>归因路径2：</span>
                        <span>相似三角形 ← 三角形 ← 线段与角 (传播薄弱度 18%)</span>
                      </div>
                    </div>
                  </div>
                  <div className='text-sm text-muted-foreground'>
                    建议：优先复习"全等三角形"相关知识，夯实前置基础后再回归"相似三角形"的练习。
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}
