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
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import {
  getDashboardStats,
  getRecentActivity,
  analyzeKnowledge,
} from '@/lib/api'

// 后端返回类型
interface DashboardStats {
  total_graded: number
  pending_review: number
  correction_rate: number
  weak_points: number
}

interface RecentActivity {
  task_id: string
  student_id: string
  score: number
  max_score: number
  status: string
  flagged: boolean
  confidence: number
}

interface WeakPoint {
  knowledge_id: string
  knowledge_name: string
  weakness_score: number
  error_count: number
  recent_errors: Array<{ date: string; question: string; error_cause: string }>
  suggestion: string
  error_cause_distribution: Record<string, number>
}

// ===== 硬编码 fallback 数据 =====
const fallbackStats = {
  pendingHomework: 3,
  totalErrors: 12,
  correctionRate: 75,
  totalGraded: 5,
}

const fallbackHomework: HomeworkItem[] = [
  { id: '1', subject: '数学', title: '二次函数练习册 P42-45', deadline: '2026-07-17', status: '未提交' },
  { id: '2', subject: '数学', title: '相似三角形证明题', deadline: '2026-07-18', status: '未提交' },
  { id: '3', subject: '数学', title: '一元二次方程综合练习', deadline: '2026-07-19', status: '未提交' },
  { id: '4', subject: '数学', title: '三角函数应用题', deadline: '2026-07-15', status: '已批改', score: 85 },
  { id: '5', subject: '数学', title: '几何证明专题', deadline: '2026-07-14', status: '已批改', score: 72 },
]

const fallbackWeakKnowledge = [
  { name: '相似三角形', mastery: 35 },
  { name: '二次函数', mastery: 48 },
  { name: '几何证明', mastery: 55 },
]

const achievements = [
  { icon: '🏆', title: '连续7天完成作业', desc: '坚持就是胜利' },
  { icon: '📚', title: '订正达人', desc: '订正完成率超过80%' },
]

type HomeworkStatus = '未提交' | '已批改'

interface HomeworkItem {
  id: string
  subject: string
  title: string
  deadline: string
  status: HomeworkStatus
  score?: number
}

const statusColorMap: Record<HomeworkStatus, string> = {
  '未提交': 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  '已批改': 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
}

// 将后端活动数据适配为作业列表格式
function adaptActivity(activity: RecentActivity, index: number): HomeworkItem {
  let status: HomeworkStatus
  if (activity.status === '已批改') {
    status = '已批改'
  } else {
    // 待审核 / 低置信 → 未提交
    status = '未提交'
  }
  const today = new Date().toISOString().slice(0, 10)
  return {
    id: activity.task_id || String(index + 1),
    subject: '数学',
    title: activity.student_id
      ? `作业 #${activity.task_id?.slice(-4) || index + 1}（${activity.student_id}）`
      : `作业 #${index + 1}`,
    deadline: today,
    status,
    score: status === '已批改' ? activity.score : undefined,
  }
}

export function StudentDashboard() {
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<typeof fallbackStats>(fallbackStats)
  const [homework, setHomework] = useState(fallbackHomework)
  const [weakKnowledge, setWeakKnowledge] = useState(fallbackWeakKnowledge)

  useEffect(() => {
    let mounted = true
    async function loadAll() {
      setLoading(true)
      try {
        const [statsRes, activityRes, knowledgeRes] = await Promise.allSettled([
          getDashboardStats(),
          getRecentActivity(),
          analyzeKnowledge('stu_demo'),
        ])

        if (!mounted) return

        // KPI 卡片
        if (statsRes.status === 'fulfilled') {
          const s: DashboardStats = statsRes.value
          if (s && typeof s.pending_review === 'number') {
            setStats({
              pendingHomework: s.pending_review,
              totalErrors: s.weak_points,
              correctionRate: Math.round(s.correction_rate),
              totalGraded: s.total_graded,
            })
          }
        }

        // 最近作业
        if (activityRes.status === 'fulfilled') {
          const acts = activityRes.value?.activities ?? []
          if (acts.length > 0) {
            setHomework(acts.map((a, i) => adaptActivity(a, i)))
          }
        }

        // 薄弱知识点
        if (knowledgeRes.status === 'fulfilled') {
          const wps: WeakPoint[] = knowledgeRes.value?.weak_points ?? []
          if (wps.length > 0) {
            setWeakKnowledge(
              wps.map((wp) => ({
                name: wp.knowledge_name,
                // weakness_score 越高掌握度越低
                mastery: Math.max(0, Math.round((1 - wp.weakness_score) * 100)),
              }))
            )
          }
        }
      } catch (e) {
        // 全部失败时保持 fallback 数据
        console.warn('Dashboard 数据加载失败，使用示例数据', e)
      } finally {
        if (mounted) setLoading(false)
      }
    }
    loadAll()
    return () => {
      mounted = false
    }
  }, [])

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
      {/* 欢迎语 */}
      <div>
        <h1 className='text-2xl font-bold tracking-tight'>学习主页</h1>
        <p className='text-muted-foreground'>欢迎回来，李明！今天也要加油哦 💪</p>
      </div>

      {/* KPI 卡片 */}
      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
            <CardTitle className='text-sm font-medium'>待做作业</CardTitle>
            <Icon icon='lucide:clipboard-list' className='h-4 w-4 text-muted-foreground' />
          </CardHeader>
          <CardContent>
            <div className='text-2xl font-bold'>{stats.pendingHomework} 份</div>
            <p className='text-xs text-muted-foreground'>
              最近截止：明天
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
            <CardTitle className='text-sm font-medium'>我的错题</CardTitle>
            <Icon icon='lucide:book-open' className='h-4 w-4 text-muted-foreground' />
          </CardHeader>
          <CardContent>
            <div className='text-2xl font-bold'>{stats.totalErrors} 道</div>
            <p className='text-xs text-muted-foreground'>
              本周新增 4 道
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
            <CardTitle className='text-sm font-medium'>订正完成率</CardTitle>
            <Icon icon='lucide:check-circle' className='h-4 w-4 text-muted-foreground' />
          </CardHeader>
          <CardContent>
            <div className='text-2xl font-bold'>{stats.correctionRate}%</div>
            <p className='text-xs text-muted-foreground'>
              较上周提升 8%
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
            <CardTitle className='text-sm font-medium'>已批改作业</CardTitle>
            <Icon icon='lucide:trophy' className='h-4 w-4 text-muted-foreground' />
          </CardHeader>
          <CardContent>
            <div className='text-2xl font-bold'>
              {stats.totalGraded} 份
            </div>
            <p className='text-xs text-muted-foreground'>
              累计批改记录
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 下方双栏 */}
      <div className='grid grid-cols-1 gap-4 lg:grid-cols-7'>
        {/* 最近作业 */}
        <Card className='col-span-1 lg:col-span-4'>
          <CardHeader>
            <CardTitle>最近作业</CardTitle>
            <CardDescription>待完成和已批改的作业</CardDescription>
          </CardHeader>
          <CardContent>
            <div className='space-y-3'>
              {homework.map((hw) => (
                <div
                  key={hw.id}
                  className='flex items-center justify-between rounded-lg border p-3'
                >
                  <div className='flex-1'>
                    <div className='flex items-center gap-2'>
                      <Badge variant='outline' className='text-xs'>{hw.subject}</Badge>
                      <span className='text-sm font-medium'>{hw.title}</span>
                    </div>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      截止日期：{hw.deadline}
                    </p>
                  </div>
                  <div className='flex items-center gap-3'>
                    {hw.status === '已批改' && hw.score !== undefined && (
                      <span className={`text-sm font-bold ${hw.score >= 80 ? 'text-green-600' : hw.score >= 60 ? 'text-orange-500' : 'text-red-600'}`}>
                        {hw.score} 分
                      </span>
                    )}
                    <Badge className={statusColorMap[hw.status]} variant='outline'>
                      {hw.status}
                    </Badge>
                    {hw.status === '未提交' && (
                      <Button size='sm' variant='outline'>去提交</Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* 右侧：薄弱知识点 + 学习成就 */}
        <div className='col-span-1 space-y-4 lg:col-span-3'>
          <Card>
            <CardHeader>
              <CardTitle>薄弱知识点</CardTitle>
              <CardDescription>需要加强的知识领域</CardDescription>
            </CardHeader>
            <CardContent>
              <div className='space-y-4'>
                {weakKnowledge.map((point) => (
                  <div key={point.name}>
                    <div className='mb-1 flex items-center justify-between text-sm'>
                      <span>{point.name}</span>
                      <span className='text-muted-foreground'>掌握度 {point.mastery}%</span>
                    </div>
                    <Progress value={point.mastery} className='h-2' />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>学习成就</CardTitle>
            </CardHeader>
            <CardContent>
              <div className='space-y-3'>
                {achievements.map((a) => (
                  <div key={a.title} className='flex items-center gap-3'>
                    <span className='text-2xl'>{a.icon}</span>
                    <div>
                      <p className='text-sm font-medium'>{a.title}</p>
                      <p className='text-xs text-muted-foreground'>{a.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
