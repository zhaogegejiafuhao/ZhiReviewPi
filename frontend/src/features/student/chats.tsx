import { useEffect, useState } from 'react'
import { Icon } from '@iconify-icon/react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Progress } from '@/components/ui/progress'
import { analyzeKnowledge } from '@/lib/api'

type ErrorType = '计算粗心' | '概念混淆' | '审题不清' | '逻辑跳步' | '辅助线缺失' | '知识缺失'
type CorrectionStatus = '待订正' | '已订正' | '订正错误'

interface MyError {
  id: string
  questionContent: string
  myAnswer: string
  correctAnswer: string
  errorType: ErrorType
  knowledgePoints: string[]
  status: CorrectionStatus
  date: string
  aiSuggestion: string
  subject: string
  // 扩展字段：用于展示薄弱度
  weaknessScore?: number
  errorCount?: number
  errorCauseDistribution?: Record<string, number>
  recentErrors?: Array<{ date: string; question: string; error_cause: string }>
}

// 后端返回类型
interface WeakPoint {
  knowledge_id: string
  knowledge_name: string
  weakness_score: number
  error_count: number
  recent_errors: Array<{ date: string; question: string; error_cause: string }>
  suggestion: string
  error_cause_distribution: Record<string, number>
}

// 错因 → ErrorType 映射（未知错因归入"概念混淆"）
function toErrorType(cause: string): ErrorType {
  const known: ErrorType[] = ['计算粗心', '概念混淆', '审题不清', '逻辑跳步', '辅助线缺失', '知识缺失']
  return (known.includes(cause as ErrorType) ? cause : '概念混淆') as ErrorType
}

// 从错因分布中找出主要错因
function getMainCause(dist: Record<string, number> | undefined): ErrorType {
  if (!dist || Object.keys(dist).length === 0) return '计算粗心'
  let mainCause = ''
  let maxCount = 0
  for (const [cause, count] of Object.entries(dist)) {
    if (count > maxCount) {
      maxCount = count
      mainCause = cause
    }
  }
  return toErrorType(mainCause || '计算粗心')
}

// 将后端薄弱知识点适配为错题列表项
function adaptWeakPoint(wp: WeakPoint, analysisDate: string): MyError {
  const mainCause = getMainCause(wp.error_cause_distribution)
  const weaknessPct = Math.round(wp.weakness_score * 100)
  // 错因分布格式化为文本
  const distText = wp.error_cause_distribution && Object.keys(wp.error_cause_distribution).length > 0
    ? Object.entries(wp.error_cause_distribution)
        .map(([cause, count]) => `${cause}(${count})`)
        .join('，')
    : '暂无错因统计'

  return {
    id: wp.knowledge_id,
    subject: '数学',
    questionContent: wp.knowledge_name,
    myAnswer: `薄弱度 ${weaknessPct}%，近期错题 ${wp.error_count} 道`,
    correctAnswer: distText,
    errorType: mainCause,
    knowledgePoints: [wp.knowledge_name],
    status: '待订正',
    date: analysisDate,
    aiSuggestion: wp.suggestion || `建议重点复习${wp.knowledge_name}相关知识，多做针对性练习`,
    weaknessScore: wp.weakness_score,
    errorCount: wp.error_count,
    errorCauseDistribution: wp.error_cause_distribution,
    recentErrors: wp.recent_errors,
  }
}

// ===== 硬编码 fallback 数据 =====
const fallbackErrors: MyError[] = [
  {
    id: '1',
    subject: '数学',
    questionContent: '导数与极值',
    myAnswer: '薄弱度 65%，近期错题 2 道',
    correctAnswer: '计算粗心(1)，概念混淆(1)',
    errorType: '计算粗心',
    knowledgePoints: ['导数', '极值', '因式分解'],
    status: '待订正',
    date: '2026-07-15',
    aiSuggestion: '因式分解出错：3x² - 6x = 3x(x - 2)，不是 3x(x - 6)。注意提取公因式后的系数。',
    weaknessScore: 0.65,
    errorCount: 2,
    errorCauseDistribution: { '计算粗心': 1, '概念混淆': 1 },
  },
  {
    id: '2',
    subject: '数学',
    questionContent: '余弦定理',
    myAnswer: '薄弱度 72%，近期错题 1 道',
    correctAnswer: '概念混淆(1)',
    errorType: '概念混淆',
    knowledgePoints: ['余弦定理', '特殊角三角函数'],
    status: '已订正',
    date: '2026-07-14',
    aiSuggestion: 'cos60° = 0.5，所以 2ab·cosC = 35，不是 70。加强特殊角三角函数值的记忆。',
    weaknessScore: 0.72,
    errorCount: 1,
    errorCauseDistribution: { '概念混淆': 1 },
  },
  {
    id: '3',
    subject: '数学',
    questionContent: '等差数列',
    myAnswer: '薄弱度 58%，近期错题 1 道',
    correctAnswer: '审题不清(1)',
    errorType: '审题不清',
    knowledgePoints: ['等差数列', '通项公式', '前n项和'],
    status: '订正错误',
    date: '2026-07-13',
    aiSuggestion: 'a₁ = a₃ - 2d = 7 - 4 = 3，不是 5。注意 a₃ = a₁ + 2d 中 2d 的系数。',
    weaknessScore: 0.58,
    errorCount: 1,
    errorCauseDistribution: { '审题不清': 1 },
  },
  {
    id: '4',
    subject: '数学',
    questionContent: '对数不等式',
    myAnswer: '薄弱度 80%，近期错题 1 道',
    correctAnswer: '审题不清(1)',
    errorType: '审题不清',
    knowledgePoints: ['对数不等式', '定义域', '二次不等式'],
    status: '待订正',
    date: '2026-07-12',
    aiSuggestion: '忽略定义域限制：需 x-1 > 0 且 5-x > 0，即 1 < x < 5。必须先求定义域再解不等式。',
    weaknessScore: 0.8,
    errorCount: 1,
    errorCauseDistribution: { '审题不清': 1 },
  },
  {
    id: '5',
    subject: '数学',
    questionContent: '椭圆与点差法',
    myAnswer: '薄弱度 50%，近期错题 1 道',
    correctAnswer: '计算粗心(1)',
    errorType: '计算粗心',
    knowledgePoints: ['椭圆', '点差法', '直线方程'],
    status: '已订正',
    date: '2026-07-11',
    aiSuggestion: '点差法计算出错，需重新检查化简过程，注意 y₁+y₂ = 3 的正确使用。',
    weaknessScore: 0.5,
    errorCount: 1,
    errorCauseDistribution: { '计算粗心': 1 },
  },
]

const errorTypeColorMap: Record<ErrorType, string> = {
  计算粗心: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  概念混淆: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  审题不清: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  逻辑跳步: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  辅助线缺失: 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400',
  知识缺失: 'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400',
}

const statusColorMap: Record<CorrectionStatus, string> = {
  '待订正': 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  '已订正': 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  '订正错误': 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
}

// 从错题列表统计错因分布
function computeErrorStats(errors: MyError[]) {
  const counts: Record<ErrorType, number> = {
    计算粗心: 0,
    概念混淆: 0,
    审题不清: 0,
    逻辑跳步: 0,
    辅助线缺失: 0,
    知识缺失: 0,
  }
  for (const e of errors) {
    // 优先用 errorCauseDistribution 累加，否则用 errorType +1
    if (e.errorCauseDistribution) {
      for (const [cause, count] of Object.entries(e.errorCauseDistribution)) {
        counts[toErrorType(cause)] += count
      }
    } else {
      counts[e.errorType] += 1
    }
  }
  const colors: Record<ErrorType, string> = {
    计算粗心: 'bg-red-500',
    概念混淆: 'bg-purple-500',
    审题不清: 'bg-orange-500',
    逻辑跳步: 'bg-blue-500',
    辅助线缺失: 'bg-teal-500',
    知识缺失: 'bg-pink-500',
  }
  return (Object.keys(counts) as ErrorType[])
    .filter((t) => counts[t] > 0)
    .map((t) => ({ type: t, count: counts[t], color: colors[t] }))
}

export function StudentChats() {
  const [loading, setLoading] = useState(true)
  const [myErrors, setMyErrors] = useState<MyError[]>(fallbackErrors)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filter, setFilter] = useState<ErrorType | 'all'>('all')

  useEffect(() => {
    let mounted = true
    async function loadData() {
      setLoading(true)
      try {
        const res = await analyzeKnowledge('stu_demo')
        if (!mounted) return
        const wps: WeakPoint[] = res?.weak_points ?? []
        if (wps.length > 0) {
          const analysisDate = res?.analysis_date || new Date().toISOString().slice(0, 10)
          setMyErrors(wps.map((wp) => adaptWeakPoint(wp, analysisDate)))
        }
      } catch (e) {
        console.warn('错题归因数据加载失败，使用示例数据', e)
      } finally {
        if (mounted) setLoading(false)
      }
    }
    loadData()
    return () => {
      mounted = false
    }
  }, [])

  const errorStats = computeErrorStats(myErrors)
  const filtered = filter === 'all' ? myErrors : myErrors.filter((e) => e.errorType === filter)
  const selected = myErrors.find((e) => e.id === selectedId)
  const pendingCount = myErrors.filter((e) => e.status === '待订正').length

  if (loading) {
    return (
      <div className='flex items-center justify-center py-20'>
        <Icon icon='lucide:loader-2' className='mr-2 h-5 w-5 animate-spin text-muted-foreground' />
        <span className='text-muted-foreground'>加载中...</span>
      </div>
    )
  }

  return (
    <div className='space-y-6'>
      <div>
        <h1 className='text-2xl font-bold tracking-tight'>我的错题本</h1>
        <p className='text-muted-foreground'>
          共 {myErrors.length} 道错题，{pendingCount} 道待订正
        </p>
      </div>

      {/* 错因统计条 */}
      <Card>
        <CardContent className='p-4'>
          <div className='flex items-center gap-4'>
            {errorStats.map((s) => (
              <button
                key={s.type}
                type='button'
                onClick={() => setFilter(filter === s.type ? 'all' : s.type)}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  filter === s.type ? 'ring-2 ring-primary' : ''
                } ${errorTypeColorMap[s.type]}`}
              >
                {s.type} ({s.count})
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 错题列表 */}
      <div className='grid grid-cols-1 gap-4 lg:grid-cols-5'>
        {/* 左侧列表 */}
        <div className='lg:col-span-2'>
          <ScrollArea className='h-[500px]'>
            <div className='space-y-2'>
              {filtered.map((err) => (
                <Card
                  key={err.id}
                  className={`cursor-pointer transition-colors hover:bg-accent/50 ${selectedId === err.id ? 'ring-2 ring-primary' : ''}`}
                  onClick={() => setSelectedId(err.id)}
                >
                  <CardContent className='p-3'>
                    <div className='flex items-center justify-between'>
                      <Badge className={errorTypeColorMap[err.errorType]} variant='outline' style={{ fontSize: 10 }}>
                        {err.errorType}
                      </Badge>
                      <Badge className={statusColorMap[err.status]} variant='outline' style={{ fontSize: 10 }}>
                        {err.status}
                      </Badge>
                    </div>
                    <p className='mt-2 line-clamp-2 text-sm font-medium'>{err.questionContent}</p>
                    {err.weaknessScore !== undefined && (
                      <div className='mt-2'>
                        <div className='mb-1 flex items-center justify-between text-xs text-muted-foreground'>
                          <span>薄弱度</span>
                          <span>{Math.round(err.weaknessScore * 100)}%</span>
                        </div>
                        <Progress value={err.weaknessScore * 100} className='h-1.5' />
                      </div>
                    )}
                    <p className='mt-1 text-xs text-muted-foreground'>{err.date}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* 右侧详情 */}
        <div className='lg:col-span-3'>
          {selected ? (
            <div className='space-y-4'>
              <Card>
                <CardHeader>
                  <div className='flex items-center justify-between'>
                    <CardTitle className='text-base'>知识点详情</CardTitle>
                    <Badge className={errorTypeColorMap[selected.errorType]} variant='outline'>
                      {selected.errorType}
                    </Badge>
                  </div>
                  <CardDescription>{selected.subject} · {selected.date}</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className='text-sm leading-relaxed font-medium'>{selected.questionContent}</p>
                  {selected.errorCount !== undefined && (
                    <p className='mt-1 text-xs text-muted-foreground'>近期错题 {selected.errorCount} 道</p>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className='text-base'>薄弱度分析</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className='rounded-md bg-red-50 p-3 text-sm leading-relaxed dark:bg-red-900/20'>
                    {selected.myAnswer}
                  </p>
                  {selected.weaknessScore !== undefined && (
                    <div className='mt-3'>
                      <Progress value={selected.weaknessScore * 100} className='h-2' />
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className='text-base'>错因分布</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className='rounded-md bg-green-50 p-3 text-sm leading-relaxed dark:bg-green-900/20'>
                    {selected.correctAnswer}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className='text-base'>AI 诊断建议</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className='rounded-md bg-blue-50 p-3 text-sm leading-relaxed dark:bg-blue-900/20'>
                    {selected.aiSuggestion}
                  </p>
                  <div className='mt-3 flex flex-wrap gap-2'>
                    {selected.knowledgePoints.map((kp) => (
                      <Badge key={kp} variant='secondary'>{kp}</Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <div className='flex gap-2'>
                {selected.status === '待订正' && (
                  <Button>开始订正</Button>
                )}
                {selected.status === '订正错误' && (
                  <Button variant='destructive'>重新订正</Button>
                )}
                <Button variant='outline'>查看类似题</Button>
              </div>
            </div>
          ) : (
            <Card>
              <CardContent className='flex flex-col items-center justify-center py-16'>
                <Icon icon='lucide:mouse-pointer-click' className='mb-2 h-10 w-10 text-muted-foreground' />
                <p className='text-muted-foreground'>点击左侧错题查看详情</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
