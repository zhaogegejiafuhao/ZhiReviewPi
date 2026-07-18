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
import { Progress } from '@/components/ui/progress'
import { getPersonalizedCorrection } from '@/lib/api'

type CorrectionStatus = '待订正' | '订正中' | '已订正' | '订正错误'

interface CorrectionTask {
  id: number
  originalQuestion: string
  originalError: string
  errorType: string
  knowledgePoints: string[]
  status: CorrectionStatus
  assignedDate: string
  deadline: string
  attempts: number
  maxAttempts: number
  correctAnswer: string
  hint: string
}

// 后端返回类型
interface CorrectionStrategy {
  mode: string
  description: string
  exercise_count: number
  exercise_type: string
  support: string
}

interface PersonalizedTask {
  knowledge_id: string
  knowledge_name: string
  tier: string
  weakness_score: number
  strategy: CorrectionStrategy
  error_cause_distribution: Record<string, number>
  suggestion: string
  recent_errors: Array<{ date: string; question: string; error_cause: string }>
}

// weakness_score → CorrectionStatus 映射
function weaknessToStatus(weaknessScore: number): CorrectionStatus {
  // 高薄弱度（学困生）→ 待订正；中等 → 订正中；低薄弱度（优等生）→ 已订正
  if (weaknessScore >= 0.6) return '待订正'
  if (weaknessScore >= 0.3) return '订正中'
  return '已订正'
}

// 从错因分布中找出主要错因
function getMainCause(dist: Record<string, number> | undefined): string {
  if (!dist || Object.keys(dist).length === 0) return '未分类'
  let mainCause = ''
  let maxCount = 0
  for (const [cause, count] of Object.entries(dist)) {
    if (count > maxCount) {
      maxCount = count
      mainCause = cause
    }
  }
  return mainCause || '未分类'
}

// 将后端分层订正任务适配为 CorrectionTask 格式
function adaptTask(task: PersonalizedTask, index: number): CorrectionTask {
  const today = new Date()
  const todayStr = today.toISOString().slice(0, 10)
  // 截止日期 = 今天 + 3天
  const deadline = new Date(today.getTime() + 3 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  const status = weaknessToStatus(task.weakness_score)

  // 优先使用 recent_errors 中的题目内容，否则使用知识点名称
  const recentQuestion = task.recent_errors && task.recent_errors.length > 0
    ? task.recent_errors[0].question
    : task.knowledge_name

  return {
    id: index + 1,
    originalQuestion: `${recentQuestion}（${task.tier}）`,
    originalError: task.strategy?.description || `薄弱度 ${Math.round(task.weakness_score * 100)}%，${getMainCause(task.error_cause_distribution)}为主`,
    errorType: getMainCause(task.error_cause_distribution),
    knowledgePoints: [task.knowledge_name],
    status,
    assignedDate: todayStr,
    deadline,
    attempts: status === '已订正' ? 2 : status === '订正中' ? 1 : 0,
    maxAttempts: 3,
    correctAnswer: '',
    hint: task.suggestion || task.strategy?.support || `建议重点复习${task.knowledge_name}相关知识`,
  }
}

// ===== 硬编码 fallback 数据 =====
const fallbackTasks: CorrectionTask[] = [
  {
    id: 1,
    originalQuestion: '求函数 f(x) = x³ - 3x² + 2 的极值点及对应的极值。（学困生）',
    originalError: '因式分解错误：3x(x-6) 应为 3x(x-2)',
    errorType: '计算粗心',
    knowledgePoints: ['导数', '极值', '因式分解'],
    status: '待订正',
    assignedDate: '2026-07-15',
    deadline: '2026-07-18',
    attempts: 0,
    maxAttempts: 3,
    correctAnswer: 'f导(x) = 3x(x-2) = 0，x = 0（极大值2）或 x = 2（极小值-2）',
    hint: '先对 f(x) 求导，然后正确因式分解',
  },
  {
    id: 2,
    originalQuestion: '在△ABC中，已知 a = 5，b = 7，C = 60°，求 c 的长度。（中等生）',
    originalError: 'cos60° 计算错误：2ab·cosC = 35，不是 70',
    errorType: '概念混淆',
    knowledgePoints: ['余弦定理', '特殊角三角函数'],
    status: '订正中',
    assignedDate: '2026-07-14',
    deadline: '2026-07-17',
    attempts: 1,
    maxAttempts: 3,
    correctAnswer: '',
    hint: '回忆特殊角的三角函数值：cos60° = 1/2',
  },
  {
    id: 3,
    originalQuestion: '解不等式：log₂(x - 1) + log₂(5 - x) ≤ 1。（学困生）',
    originalError: '忽略了对数函数的定义域限制',
    errorType: '审题不清',
    knowledgePoints: ['对数不等式', '定义域'],
    status: '待订正',
    assignedDate: '2026-07-12',
    deadline: '2026-07-16',
    attempts: 0,
    maxAttempts: 3,
    correctAnswer: '先求定义域 1 < x < 5，再解不等式，取交集',
    hint: '对数不等式必须先确定定义域条件',
  },
  {
    id: 4,
    originalQuestion: '求等差数列 {an} 中，已知 a₃ = 7，a₇ = 15，求 S₁₀。（优等生）',
    originalError: 'a₁ 计算错误：a₁ = a₃ - 2d = 3，不是 5',
    errorType: '审题不清',
    knowledgePoints: ['等差数列', '通项公式'],
    status: '已订正',
    assignedDate: '2026-07-11',
    deadline: '2026-07-14',
    attempts: 2,
    maxAttempts: 3,
    correctAnswer: '',
    hint: '',
  },
  {
    id: 5,
    originalQuestion: '已知椭圆 C: x²/4 + y²/3 = 1，直线 l 过点 (1, 0)，求直线方程。（中等生）',
    originalError: '点差法化简过程出错',
    errorType: '计算粗心',
    knowledgePoints: ['椭圆', '点差法'],
    status: '订正错误',
    assignedDate: '2026-07-13',
    deadline: '2026-07-17',
    attempts: 3,
    maxAttempts: 3,
    correctAnswer: '',
    hint: '重新检查点差法的每一步代数运算',
  },
]

const statusConfig: Record<CorrectionStatus, { color: string; label: string }> = {
  待订正: { color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400', label: '待订正' },
  订正中: { color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', label: '订正中' },
  已订正: { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: '已订正' },
  订正错误: { color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', label: '订正错误' },
}

export function StudentApps() {
  const [loading, setLoading] = useState(true)
  const [correctionTasks, setCorrectionTasks] = useState<CorrectionTask[]>(fallbackTasks)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  useEffect(() => {
    let mounted = true
    async function loadData() {
      setLoading(true)
      try {
        const res = await getPersonalizedCorrection('stu_demo')
        if (!mounted) return
        const tasks: PersonalizedTask[] = res?.tasks ?? []
        if (tasks.length > 0) {
          setCorrectionTasks(tasks.map((t, i) => adaptTask(t, i)))
        }
      } catch (e) {
        console.warn('订正任务加载失败，使用示例数据', e)
      } finally {
        if (mounted) setLoading(false)
      }
    }
    loadData()
    return () => {
      mounted = false
    }
  }, [])

  const selected = correctionTasks.find((t) => t.id === selectedId)

  const pending = correctionTasks.filter((t) => t.status === '待订正')
  const inProgress = correctionTasks.filter((t) => t.status === '订正中' || t.status === '订正错误')
  const completed = correctionTasks.filter((t) => t.status === '已订正')
  const completionRate = correctionTasks.length > 0
    ? Math.round((completed.length / correctionTasks.length) * 100)
    : 0

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Icon icon="lucide:loader-2" className="mr-2 h-5 w-5 animate-spin text-muted-foreground" />
        <span className="text-muted-foreground">加载中...</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">订正任务</h1>
          <p className="text-muted-foreground">完成错题订正，巩固薄弱知识点</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-muted-foreground">完成率</p>
          <p className="text-2xl font-bold text-green-600">{completionRate}%</p>
        </div>
      </div>

      {/* 进度条 */}
      <Card>
        <CardContent className="p-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              已完成 {completed.length} / {correctionTasks.length} 项
            </span>
            <div className="flex gap-3 text-xs">
              <span className="text-orange-500">待订正 {pending.length}</span>
              <span className="text-blue-500">进行中 {inProgress.length}</span>
              <span className="text-green-500">已完成 {completed.length}</span>
            </div>
          </div>
          <Progress value={completionRate} className="h-3" />
        </CardContent>
      </Card>

      {/* 订正任务列表 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {correctionTasks.map((task) => (
          <Card
            key={task.id}
            className={`cursor-pointer transition-colors hover:bg-accent/50 ${selectedId === task.id ? 'ring-2 ring-primary' : ''}`}
            onClick={() => setSelectedId(task.id)}
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <Badge className={statusConfig[task.status].color} variant="outline">
                  {task.status}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  尝试 {task.attempts}/{task.maxAttempts} 次
                </span>
              </div>
              <CardTitle className="mt-2 line-clamp-2 text-sm">
                {task.originalQuestion}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-2 text-xs text-red-600 dark:text-red-400">
                错误：{task.originalError}
              </p>
              <div className="flex items-center justify-between">
                <div className="flex flex-wrap gap-1">
                  {task.knowledgePoints.map((kp) => (
                    <Badge key={kp} variant="secondary" className="text-[10px]">
                      {kp}
                    </Badge>
                  ))}
                </div>
                <span className="text-xs text-muted-foreground">截止 {task.deadline}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 选中任务的详情 */}
      {selected && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>订正详情</CardTitle>
              <Badge className={statusConfig[selected.status].color} variant="outline">
                {selected.status}
              </Badge>
            </div>
            <CardDescription>
              布置于 {selected.assignedDate} · 截止 {selected.deadline}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">原题</p>
              <p className="text-sm">{selected.originalQuestion}</p>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-red-600">错误原因</p>
              <p className="text-sm">{selected.originalError}</p>
            </div>
            {selected.correctAnswer && (
              <div>
                <p className="mb-1 text-xs font-medium text-green-600">参考答案</p>
                <p className="text-sm">{selected.correctAnswer}</p>
              </div>
            )}
            {selected.hint && (
              <div className="rounded-lg bg-yellow-50 p-3 dark:bg-yellow-900/20">
                <p className="mb-1 text-xs font-medium text-yellow-700 dark:text-yellow-400">提示</p>
                <p className="text-sm">{selected.hint}</p>
              </div>
            )}
            <div className="flex gap-2">
              {selected.status === "待订正" && (
                <Button>开始订正</Button>
              )}
              {selected.status === "订正中" && (
                <Button>继续订正</Button>
              )}
              {selected.status === "订正错误" && selected.attempts < selected.maxAttempts && (
                <Button variant="destructive">重新订正 ({selected.maxAttempts - selected.attempts} 次机会)</Button>
              )}
              {selected.status === "订正错误" && selected.attempts >= selected.maxAttempts && (
                <Button variant="outline" disabled>已达最大尝试次数，请联系老师</Button>
              )}
              {selected.status === "已订正" && (
                <Button variant="outline">查看订正记录</Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
