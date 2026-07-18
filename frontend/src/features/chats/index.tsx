import { useEffect, useState } from 'react'
import {
  BookOpen,
  Search as SearchIcon,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Lightbulb,
  Loader2,
  Play,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { useRole } from '@/context/role-provider'
import {
  getErrorBookList,
  getErrorBookStats,
  getSimilarQuestions,
  submitPractice,
  type ErrorBookStats,
} from '@/lib/api'
import { StudentChats } from '@/features/student/chats'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

// ==================== 错题数据类型 ====================
interface WrongQuestion {
  task_id: string
  student_id: string
  question: string
  student_answer_ocr: string
  standard_answer: string
  suggested_score: number
  max_score: number
  error_type: string
  knowledge_points: string[]
  correction_status: 'pending' | 'corrected' | 'failed'
  date: string
  comment: string
}

// ==================== 错因标签颜色映射（灵活 key，支持 API 动态返回） ====================
const FALLBACK_ERROR_TYPE_COLOR =
  'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400'

const errorTypeColorMap: Record<string, string> = {
  计算粗心: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  概念混淆: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  审题不清: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  逻辑跳步: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  辅助线缺失: 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400',
}

function getErrorTypeColor(errorType: string): string {
  return errorTypeColorMap[errorType] ?? FALLBACK_ERROR_TYPE_COLOR
}

// ==================== 订正状态映射 ====================
const statusConfig: Record<string, { label: string; color: string; icon: typeof AlertTriangle }> = {
  pending: {
    label: '待订正',
    color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    icon: AlertTriangle,
  },
  corrected: {
    label: '已订正',
    color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    icon: CheckCircle2,
  },
  failed: {
    label: '订正失败',
    color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    icon: XCircle,
  },
}

function getStatusInfo(status: string) {
  return (
    statusConfig[status] ?? {
      label: status,
      color: FALLBACK_ERROR_TYPE_COLOR,
      icon: AlertTriangle,
    }
  )
}

// ==================== 统计 KPI 卡片 ====================
function StatsCards({ stats }: { stats: ErrorBookStats | null }) {
  const cards = [
    { label: '总错题', value: stats?.total_errors ?? '-', icon: BookOpen },
    { label: '待订正', value: stats?.pending_count ?? '-', icon: AlertTriangle },
    { label: '已订正', value: stats?.corrected_count ?? '-', icon: CheckCircle2 },
    {
      label: '订正率',
      value:
        stats && typeof stats.correction_rate === 'number'
          ? `${(stats.correction_rate * 100).toFixed(1)}%`
          : '-',
      icon: CheckCircle2,
    },
  ]

  return (
    <div className='grid grid-cols-2 gap-3 lg:grid-cols-4'>
      {cards.map((card) => (
        <Card key={card.label} className='py-3'>
          <CardContent className='flex items-center gap-3'>
            <card.icon size={20} className='text-primary' />
            <div>
              <p className='text-xs text-muted-foreground'>{card.label}</p>
              <p className='text-lg font-semibold'>{card.value}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ==================== 错因分布横向柱状图 ====================
function ErrorTypeChart({ stats }: { stats: ErrorBookStats | null }) {
  if (!stats?.error_type_distribution) return null

  const data = Object.entries(stats.error_type_distribution).map(
    ([name, count]) => ({ name, count })
  )

  if (data.length === 0) return null

  return (
    <Card className='py-3'>
      <CardHeader className='pb-0'>
        <CardTitle className='text-base'>错因分布</CardTitle>
      </CardHeader>
      <CardContent>
        <div className='h-48'>
          <ResponsiveContainer width='100%' height='100%'>
            <BarChart data={data} layout='vertical' margin={{ left: 20, right: 20 }}>
              <CartesianGrid strokeDasharray='3 3' />
              <XAxis type='number' allowDecimals={false} />
              <YAxis type='category' dataKey='name' width={80} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey='count' fill='hsl(var(--primary))' radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

export function Chats() {
  const { role } = useRole()
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [mobileSelectedId, setMobileSelectedId] = useState<string | null>(null)
  const [questions, setQuestions] = useState<WrongQuestion[]>([])
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<ErrorBookStats | null>(null)
  const [similarLoading, setSimilarLoading] = useState(false)
  const [similarQuestions, setSimilarQuestions] = useState<
    Array<{ id: string; question: string; standard_answer: string; difficulty: string }>
  >([])
  const [practiceAnswers, setPracticeAnswers] = useState<Record<string, string>>({})
  const [practiceResults, setPracticeResults] = useState<
    Record<string, { correct: boolean; score: number; feedback: string }>
  >({})

  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const [listData, statsData] = await Promise.all([
          getErrorBookList({ page: 1, page_size: 20 }),
          getErrorBookStats(),
        ])
        if (!mounted) return
        setQuestions(listData?.items ?? [])
        setStats(statsData)
      } catch {
        // API 失败时展示空状态，不使用硬编码数据
      } finally {
        if (mounted) setLoading(false)
      }
    })()
    return () => {
      mounted = false
    }
  }, [])

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
        <Main fixed>
          <StudentChats />
        </Main>
      </>
    )
  }

  // 加载中
  if (loading) {
    return (
      <>
        <Header>
          <Search className='me-auto' />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </Header>
        <Main fixed>
          <section className='flex h-full gap-6'>
            {/* 左侧骨架列表 */}
            <div className='flex w-full flex-col gap-2 sm:w-56 lg:w-72 2xl:w-80'>
              <div className='py-2'>
                <div className='h-7 w-24 animate-pulse rounded bg-muted' />
                <div className='mt-1 h-4 w-40 animate-pulse rounded bg-muted' />
              </div>
              <div className='h-10 w-full animate-pulse rounded-md border' />
              <div className='mt-2 space-y-2'>
                {Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className='flex items-start gap-3 rounded-lg border p-3'
                  >
                    <div className='h-9 w-9 shrink-0 animate-pulse rounded-full bg-muted' />
                    <div className='flex-1 space-y-2'>
                      <div className='h-4 w-20 animate-pulse rounded bg-muted' />
                      <div className='h-3 w-full animate-pulse rounded bg-muted' />
                      <div className='h-3 w-2/3 animate-pulse rounded bg-muted' />
                      <div className='flex gap-2'>
                        <div className='h-5 w-16 animate-pulse rounded-full bg-muted' />
                        <div className='h-5 w-12 animate-pulse rounded-full bg-muted' />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {/* 右侧骨架详情 */}
            <div className='hidden flex-1 flex-col gap-4 sm:flex'>
              <div className='h-8 w-32 animate-pulse rounded bg-muted' />
              <div className='space-y-3'>
                <div className='h-20 w-full animate-pulse rounded-lg bg-muted' />
                <div className='h-32 w-full animate-pulse rounded-lg bg-muted' />
                <div className='h-16 w-full animate-pulse rounded-lg bg-muted' />
              </div>
            </div>
          </section>
        </Main>
      </>
    )
  }

  // 搜索过滤
  const filteredList = questions.filter(
    ({ question, error_type, student_id }) =>
      question.includes(search.trim()) ||
      error_type.includes(search.trim()) ||
      student_id.includes(search.trim())
  )

  const selectedQuestion = questions.find(
    (q) => q.task_id === (mobileSelectedId || selectedId)
  ) ?? null

  // 获取相似题推荐
  const handleFetchSimilar = async () => {
    if (!selectedQuestion) return
    setSimilarLoading(true)
    try {
      const data = await getSimilarQuestions(selectedQuestion.task_id)
      setSimilarQuestions(data?.questions ?? [])
    } catch {
      setSimilarQuestions([])
    } finally {
      setSimilarLoading(false)
    }
  }

  // 提交练习答案
  const handleSubmitPractice = async (similarId: string) => {
    if (!selectedQuestion) return
    const answer = practiceAnswers[similarId]
    if (!answer?.trim()) return
    try {
      const result = await submitPractice({
        task_id: selectedQuestion.task_id,
        student_id: selectedQuestion.student_id,
        practice_answer: answer,
      })
      setPracticeResults((prev) => ({ ...prev, [similarId]: result }))
    } catch {
      // 提交失败静默处理
    }
  }

  return (
    <>
      {/* ===== 顶部标题栏 ===== */}
      <Header>
        <Search className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main fixed>
        {/* ===== 统计区域 ===== */}
        <div className='mb-4 space-y-4'>
          <StatsCards stats={stats} />
          <ErrorTypeChart stats={stats} />
        </div>

        <section className='flex h-full gap-6'>
          {/* ===== 左侧：错题列表 ===== */}
          <div className='flex w-full flex-col gap-2 sm:w-56 lg:w-72 2xl:w-80'>
            <div className='sticky top-0 z-10 -mx-4 bg-background px-4 pb-3 shadow-md sm:static sm:z-auto sm:mx-0 sm:p-0 sm:shadow-none'>
              <div className='py-2'>
                <h1 className='text-2xl font-bold'>错题本</h1>
                <p className='text-sm text-muted-foreground'>班级错题记录与归因分析</p>
              </div>

              <label
                className={cn(
                  'focus-within:ring-1 focus-within:ring-ring focus-within:outline-hidden',
                  'flex h-10 w-full items-center space-x-0 rounded-md border border-border ps-2'
                )}
              >
                <SearchIcon size={15} className='me-2 stroke-slate-500' />
                <span className='sr-only'>搜索</span>
                <input
                  type='text'
                  className='w-full flex-1 bg-inherit text-sm focus-visible:outline-hidden'
                  placeholder='搜索学生、题目或错因...'
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
            </div>

            <ScrollArea className='-mx-3 h-full overflow-scroll p-3'>
              {filteredList.length === 0 ? (
                <div className='py-8 text-center text-sm text-muted-foreground'>
                  暂无错题数据
                </div>
              ) : (
                filteredList.map((q) => (
                  <div key={q.task_id}>
                    <button
                      type='button'
                      className={cn(
                        'group hover:bg-accent hover:text-accent-foreground',
                        'flex w-full flex-col gap-1 rounded-md px-3 py-2.5 text-start text-sm',
                        selectedId === q.task_id && 'sm:bg-muted'
                      )}
                      onClick={() => {
                        setSelectedId(q.task_id)
                        setMobileSelectedId(q.task_id)
                        // 切换错题时重置相似题数据
                        setSimilarQuestions([])
                        setPracticeAnswers({})
                        setPracticeResults({})
                      }}
                    >
                      <div className='flex items-center justify-between'>
                        <span className='font-medium'>{q.student_id}</span>
                        <Badge
                          className={cn('text-[10px] px-1.5 py-0', getErrorTypeColor(q.error_type))}
                          variant='outline'
                        >
                          {q.error_type}
                        </Badge>
                      </div>
                      <span className='line-clamp-2 text-ellipsis text-muted-foreground group-hover:text-accent-foreground/90'>
                        {q.question}
                      </span>
                      <div className='flex items-center justify-between'>
                        <span className='text-xs text-muted-foreground/70'>{q.date}</span>
                        <span className='text-xs text-muted-foreground/70'>
                          {q.suggested_score}/{q.max_score}
                        </span>
                      </div>
                    </button>
                    <Separator className='my-1' />
                  </div>
                ))
              )}
            </ScrollArea>
          </div>

          {/* ===== 右侧：错题详情 ===== */}
          {selectedQuestion ? (
            <div
              className={cn(
                'absolute inset-0 start-full z-50 hidden w-full flex-1 flex-col border bg-background shadow-xs sm:static sm:z-auto sm:flex sm:rounded-md',
                mobileSelectedId && 'inset-s-0 flex'
              )}
            >
              {/* 顶部：学生信息与返回按钮 */}
              <div className='mb-1 flex flex-none items-center gap-3 bg-card p-4 shadow-lg sm:rounded-t-md'>
                <Button
                  size='icon'
                  variant='ghost'
                  className='-ms-2 h-full sm:hidden'
                  onClick={() => setMobileSelectedId(null)}
                >
                  ← 返回
                </Button>
                <div className='flex items-center gap-2'>
                  <BookOpen size={20} className='text-primary' />
                  <div>
                    <span className='font-medium'>{selectedQuestion.student_id}</span>
                    <span className='ml-2 text-xs text-muted-foreground'>
                      {selectedQuestion.date}
                    </span>
                  </div>
                </div>
                <Badge
                  className={cn('ml-auto', getStatusInfo(selectedQuestion.correction_status).color)}
                  variant='outline'
                >
                  {(() => {
                    const info = getStatusInfo(selectedQuestion.correction_status)
                    const Icon = info.icon
                    return <Icon size={12} className='mr-1' />
                  })()}
                  {getStatusInfo(selectedQuestion.correction_status).label}
                </Badge>
              </div>

              {/* 详情内容 - Tabs 切换 */}
              <ScrollArea className='flex-1 p-4'>
                <Tabs defaultValue='detail' className='w-full'>
                  <TabsList>
                    <TabsTrigger value='detail'>错题详情</TabsTrigger>
                    <TabsTrigger value='practice'>练习模式</TabsTrigger>
                  </TabsList>

                  {/* ===== Tab 1: 错题详情 ===== */}
                  <TabsContent value='detail'>
                    <div className='space-y-4'>
                      {/* 原题内容 */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='text-base'>原题内容</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className='text-sm leading-relaxed'>
                            {selectedQuestion.question}
                          </p>
                        </CardContent>
                      </Card>

                      {/* 学生作答（OCR识别） */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='text-base'>学生作答（OCR识别）</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className='rounded-md bg-muted p-3 text-sm leading-relaxed'>
                            {selectedQuestion.student_answer_ocr || '暂无 OCR 识别结果'}
                          </p>
                        </CardContent>
                      </Card>

                      {/* 标准答案 */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='text-base'>标准答案</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className='rounded-md bg-muted p-3 text-sm leading-relaxed'>
                            {selectedQuestion.standard_answer || '暂无标准答案'}
                          </p>
                        </CardContent>
                      </Card>

                      {/* 评分 */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='text-base'>评分</CardTitle>
                          <CardDescription>AI 建议得分 / 满分</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <span className='text-2xl font-bold text-primary'>
                            {selectedQuestion.suggested_score}
                          </span>
                          <span className='text-lg text-muted-foreground'>
                            {' / '}{selectedQuestion.max_score}
                          </span>
                        </CardContent>
                      </Card>

                      {/* 错因分析 */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='text-base'>错因分析</CardTitle>
                          <CardDescription>归因分类</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <Badge
                            className={cn('text-sm', getErrorTypeColor(selectedQuestion.error_type))}
                            variant='outline'
                          >
                            {selectedQuestion.error_type}
                          </Badge>
                        </CardContent>
                      </Card>

                      {/* 涉及知识点 */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='text-base'>涉及知识点</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className='flex flex-wrap gap-2'>
                            {selectedQuestion.knowledge_points.map((point) => (
                              <Badge key={point} variant='secondary'>
                                {point}
                              </Badge>
                            ))}
                          </div>
                        </CardContent>
                      </Card>

                      {/* 订正状态 */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='text-base'>订正状态</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <Badge
                            className={cn(getStatusInfo(selectedQuestion.correction_status).color)}
                            variant='outline'
                          >
                            {(() => {
                              const info = getStatusInfo(selectedQuestion.correction_status)
                              const Icon = info.icon
                              return <Icon size={12} className='mr-1' />
                            })()}
                            {getStatusInfo(selectedQuestion.correction_status).label}
                          </Badge>
                        </CardContent>
                      </Card>

                      {/* AI建议 */}
                      <Card className='border-primary/20 bg-primary/5'>
                        <CardHeader>
                          <CardTitle className='flex items-center gap-2 text-base'>
                            <Lightbulb size={16} className='text-primary' />
                            AI建议
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className='text-sm leading-relaxed'>
                            {selectedQuestion.comment || '暂无 AI 建议'}
                          </p>
                        </CardContent>
                      </Card>

                      {/* 相似题推荐 */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='flex items-center gap-2 text-base'>
                            <Play size={16} className='text-primary' />
                            相似题推荐
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          {similarQuestions.length === 0 ? (
                            <Button
                              variant='outline'
                              onClick={handleFetchSimilar}
                              disabled={similarLoading}
                            >
                              {similarLoading ? (
                                <>
                                  <Loader2 size={14} className='mr-2 animate-spin' />
                                  加载中...
                                </>
                              ) : (
                                '推荐相似题'
                              )}
                            </Button>
                          ) : (
                            <div className='space-y-3'>
                              {similarQuestions.map((sq) => (
                                <div
                                  key={sq.id}
                                  className='rounded-md border p-3'
                                >
                                  <p className='text-sm leading-relaxed'>{sq.question}</p>
                                  <div className='mt-2 flex items-center gap-2'>
                                    <Badge variant='secondary' className='text-xs'>
                                      {sq.difficulty}
                                    </Badge>
                                  </div>
                                  <details className='mt-2'>
                                    <summary className='cursor-pointer text-xs text-muted-foreground'>
                                      查看标准答案
                                    </summary>
                                    <p className='mt-1 rounded-md bg-muted p-2 text-sm leading-relaxed'>
                                      {sq.standard_answer}
                                    </p>
                                  </details>
                                </div>
                              ))}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>

                  {/* ===== Tab 2: 练习模式 ===== */}
                  <TabsContent value='practice'>
                    <div className='space-y-4'>
                      {similarQuestions.length === 0 ? (
                        <Card>
                          <CardContent className='py-8 text-center'>
                            <p className='text-sm text-muted-foreground'>
                              请先在"错题详情"标签页中点击"推荐相似题"获取练习题目
                            </p>
                            <Button
                              variant='outline'
                              className='mt-4'
                              onClick={handleFetchSimilar}
                              disabled={similarLoading}
                            >
                              {similarLoading ? (
                                <>
                                  <Loader2 size={14} className='mr-2 animate-spin' />
                                  加载中...
                                </>
                              ) : (
                                '获取相似题'
                              )}
                            </Button>
                          </CardContent>
                        </Card>
                      ) : (
                        similarQuestions.map((sq, idx) => (
                          <Card key={sq.id}>
                            <CardHeader>
                              <CardTitle className='text-base'>
                                练习题 {idx + 1}
                              </CardTitle>
                              <CardDescription>{sq.difficulty}</CardDescription>
                            </CardHeader>
                            <CardContent>
                              <p className='mb-3 text-sm leading-relaxed'>
                                {sq.question}
                              </p>
                              <textarea
                                className='w-full rounded-md border border-border bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'
                                rows={4}
                                placeholder='请输入你的解答...'
                                value={practiceAnswers[sq.id] ?? ''}
                                onChange={(e) =>
                                  setPracticeAnswers((prev) => ({
                                    ...prev,
                                    [sq.id]: e.target.value,
                                  }))
                                }
                              />
                              <div className='mt-3 flex items-center gap-3'>
                                <Button
                                  size='sm'
                                  onClick={() => handleSubmitPractice(sq.id)}
                                  disabled={!practiceAnswers[sq.id]?.trim()}
                                >
                                  提交答案
                                </Button>
                                {practiceResults[sq.id] && (
                                  <div
                                    className={cn(
                                      'text-sm font-medium',
                                      practiceResults[sq.id].correct
                                        ? 'text-green-600'
                                        : 'text-red-600'
                                    )}
                                  >
                                    {practiceResults[sq.id].correct ? '回答正确' : '回答有误'} -
                                    得分: {practiceResults[sq.id].score}
                                    {practiceResults[sq.id].feedback && (
                                      <span className='ml-2 font-normal text-muted-foreground'>
                                        {practiceResults[sq.id].feedback}
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </CardContent>
                          </Card>
                        ))
                      )}
                    </div>
                  </TabsContent>
                </Tabs>
              </ScrollArea>
            </div>
          ) : (
            <div
              className='absolute inset-0 start-full z-50 hidden w-full flex-1 flex-col justify-center rounded-md border bg-card shadow-xs sm:static sm:z-auto sm:flex'
            >
              <div className='flex flex-col items-center space-y-6'>
                <div className='flex size-16 items-center justify-center rounded-full border-2 border-border'>
                  <BookOpen className='size-8' />
                </div>
                <div className='space-y-2 text-center'>
                  <h1 className='text-xl font-semibold'>选择一道错题</h1>
                  <p className='text-sm text-muted-foreground'>
                    从左侧列表中选择错题，查看详细分析
                  </p>
                </div>
              </div>
            </div>
          )}
        </section>
      </Main>
    </>
  )
}
