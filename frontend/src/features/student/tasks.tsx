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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { getRecentActivity } from '@/lib/api'

type HomeworkStatus = '未提交' | '批改中' | '已批改' | '需订正'

interface Homework {
  id: number
  subject: string
  title: string
  deadline: string
  assignedDate: string
  status: HomeworkStatus
  score?: number
  teacherComment?: string
  errorCount?: number
}

// 后端返回类型
interface RecentActivity {
  task_id: string
  student_id: string
  score: number
  max_score: number
  status: string
  flagged: boolean
  confidence: number
}

// ===== 硬编码 fallback 数据 =====
const fallbackHomeworkList: Homework[] = [
  {
    id: 1, subject: '数学', title: '二次函数练习册 P42-45',
    deadline: '2026-07-17', assignedDate: '2026-07-15', status: '未提交',
  },
  {
    id: 2, subject: '数学', title: '相似三角形证明题',
    deadline: '2026-07-18', assignedDate: '2026-07-16', status: '未提交',
  },
  {
    id: 3, subject: '数学', title: '一元二次方程综合练习',
    deadline: '2026-07-19', assignedDate: '2026-07-16', status: '未提交',
  },
  {
    id: 4, subject: '数学', title: '三角函数应用题',
    deadline: '2026-07-15', assignedDate: '2026-07-13', status: '已批改',
    score: 85, errorCount: 2,
    teacherComment: '三角函数计算正确，但第3题辅助角公式运用有误，需注意公式适用条件。',
  },
  {
    id: 5, subject: '数学', title: '几何证明专题',
    deadline: '2026-07-14', assignedDate: '2026-07-12', status: '需订正',
    score: 72, errorCount: 4,
    teacherComment: '相似三角形的判定定理混淆，建议复习SSS/SAS/AA三种判定方法。',
  },
  {
    id: 6, subject: '数学', title: '一次函数与反比例函数',
    deadline: '2026-07-12', assignedDate: '2026-07-10', status: '已批改',
    score: 92, errorCount: 1,
    teacherComment: '整体掌握良好，注意反比例函数图像的渐近线性质。',
  },
  {
    id: 7, subject: '数学', title: '不等式与不等式组',
    deadline: '2026-07-10', assignedDate: '2026-07-08', status: '已批改',
    score: 78, errorCount: 3,
    teacherComment: '不等式组解集的交集计算有误，注意画数轴辅助判断。',
  },
]

const statusConfig: Record<HomeworkStatus, { color: string; icon: string }> = {
  '未提交': { color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400', icon: 'lucide:clock' },
  '批改中': { color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', icon: 'lucide:loader-2' },
  '已批改': { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', icon: 'lucide:check-circle' },
  '需订正': { color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', icon: 'lucide:alert-circle' },
}

function getUrgency(deadline: string): '紧急' | '一般' | '充裕' {
  const daysLeft = Math.ceil((new Date(deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
  if (daysLeft <= 1) return '紧急'
  if (daysLeft <= 3) return '一般'
  return '充裕'
}

const urgencyColor = {
  '紧急': 'text-red-600',
  '一般': 'text-orange-500',
  '充裕': 'text-green-600',
}

// 将后端活动数据适配为作业列表格式
function adaptActivity(activity: RecentActivity, index: number): Homework {
  // 状态映射：待审核 → 未提交/需订正；已批改 → 已批改；低置信 → 批改中
  let status: HomeworkStatus
  if (activity.status === '已批改') {
    status = '已批改'
  } else if (activity.status === '低置信' || activity.flagged) {
    status = activity.flagged ? '需订正' : '批改中'
  } else {
    // 待审核 且未标记 → 未提交
    status = '未提交'
  }

  const today = new Date().toISOString().slice(0, 10)
  const studentName = activity.student_id || `学生${index + 1}`
  const shortId = activity.task_id?.slice(-6) || String(index + 1)

  return {
    id: index + 1,
    subject: '数学',
    title: `作业任务 #${shortId}（${studentName}）`,
    deadline: today,
    assignedDate: today,
    status,
    score: status === '已批改' ? activity.score : undefined,
    errorCount: status === '已批改' && activity.score < (activity.max_score || 100)
      ? Math.max(1, Math.round((activity.max_score - activity.score) / 10))
      : undefined,
    teacherComment: status === '已批改'
      ? `置信度：${Math.round(activity.confidence * 100)}%，满分 ${activity.max_score} 分。`
      : undefined,
  }
}

export function StudentTasks() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [homeworkList, setHomeworkList] = useState<Homework[]>(fallbackHomeworkList)

  useEffect(() => {
    let mounted = true
    async function loadData() {
      setLoading(true)
      try {
        const res = await getRecentActivity()
        if (!mounted) return
        const acts: RecentActivity[] = res?.activities ?? []
        if (acts.length > 0) {
          setHomeworkList(acts.map((a, i) => adaptActivity(a, i)))
        }
      } catch (e) {
        console.warn('作业列表加载失败，使用示例数据', e)
      } finally {
        if (mounted) setLoading(false)
      }
    }
    loadData()
    return () => {
      mounted = false
    }
  }, [])

  const selected = homeworkList.find((h) => h.id === selectedId)

  const pending = homeworkList.filter((h) => h.status === '未提交')
  const inProgress = homeworkList.filter((h) => h.status === '批改中' || h.status === '需订正')
  const completed = homeworkList.filter((h) => h.status === '已批改')

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
        <h1 className='text-2xl font-bold tracking-tight'>待做作业</h1>
        <p className='text-muted-foreground'>查看和管理你的作业任务</p>
      </div>

      <Tabs defaultValue='pending' className='space-y-4'>
        <TabsList>
          <TabsTrigger value='pending'>
            未提交 <Badge variant='secondary' className='ml-1'>{pending.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value='progress'>
            进行中 <Badge variant='secondary' className='ml-1'>{inProgress.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value='completed'>
            已完成 <Badge variant='secondary' className='ml-1'>{completed.length}</Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value='pending'>
          <HomeworkList items={pending} onSelect={setSelectedId} selectedId={selectedId} />
        </TabsContent>
        <TabsContent value='progress'>
          <HomeworkList items={inProgress} onSelect={setSelectedId} selectedId={selectedId} />
        </TabsContent>
        <TabsContent value='completed'>
          <HomeworkList items={completed} onSelect={setSelectedId} selectedId={selectedId} />
        </TabsContent>
      </Tabs>

      {/* 作业详情 */}
      {selected && (
        <Card>
          <CardHeader>
            <div className='flex items-center justify-between'>
              <CardTitle className='text-lg'>{selected.title}</CardTitle>
              <Badge className={statusConfig[selected.status].color} variant='outline'>
                {selected.status}
              </Badge>
            </div>
            <CardDescription>{selected.subject} · 布置于 {selected.assignedDate}</CardDescription>
          </CardHeader>
          <CardContent className='space-y-4'>
            <div className='grid grid-cols-2 gap-4 text-sm'>
              <div>
                <span className='text-muted-foreground'>截止日期：</span>
                <span className={`ml-1 font-medium ${urgencyColor[getUrgency(selected.deadline)]}`}>
                  {selected.deadline}
                </span>
              </div>
              {selected.score !== undefined && (
                <div>
                  <span className='text-muted-foreground'>得分：</span>
                  <span className={`ml-1 font-bold text-lg ${selected.score >= 80 ? 'text-green-600' : selected.score >= 60 ? 'text-orange-500' : 'text-red-600'}`}>
                    {selected.score} 分
                  </span>
                </div>
              )}
              {selected.errorCount !== undefined && (
                <div>
                  <span className='text-muted-foreground'>错题数：</span>
                  <span className='ml-1 font-medium'>{selected.errorCount} 道</span>
                </div>
              )}
            </div>
            {selected.teacherComment && (
              <div className='rounded-lg bg-muted p-3'>
                <p className='mb-1 text-xs font-medium text-muted-foreground'>教师评语</p>
                <p className='text-sm'>{selected.teacherComment}</p>
              </div>
            )}
            <div className='flex gap-2'>
              {selected.status === '未提交' && (
                <Button>提交作业</Button>
              )}
              {selected.status === '需订正' && (
                <Button variant='destructive'>去订正</Button>
              )}
              <Button variant='outline'>查看详情</Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function HomeworkList({ items, onSelect, selectedId }: {
  items: Homework[]
  onSelect: (id: number) => void
  selectedId: number | null
}) {
  if (items.length === 0) {
    return (
      <Card>
        <CardContent className='flex flex-col items-center justify-center py-12'>
          <Icon icon='lucide:inbox' className='mb-2 h-12 w-12 text-muted-foreground' />
          <p className='text-muted-foreground'>暂无作业</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className='space-y-3'>
      {items.map((hw) => {
        const urgency = hw.status === '未提交' ? getUrgency(hw.deadline) : null
        return (
          <Card
            key={hw.id}
            className={`cursor-pointer transition-colors hover:bg-accent/50 ${selectedId === hw.id ? 'ring-2 ring-primary' : ''}`}
            onClick={() => onSelect(hw.id)}
          >
            <CardContent className='flex items-center justify-between p-4'>
              <div className='flex-1'>
                <div className='flex items-center gap-2'>
                  <Badge variant='outline' className='text-xs'>{hw.subject}</Badge>
                  <span className='font-medium'>{hw.title}</span>
                </div>
                <div className='mt-1 flex items-center gap-4 text-xs text-muted-foreground'>
                  <span>截止：{hw.deadline}</span>
                  {urgency && (
                    <span className={`font-medium ${urgencyColor[urgency]}`}>
                      {urgency === '紧急' ? '⚠ 紧急' : urgency === '一般' ? '较近' : '充裕'}
                    </span>
                  )}
                  {hw.score !== undefined && (
                    <span className={`font-bold ${hw.score >= 80 ? 'text-green-600' : hw.score >= 60 ? 'text-orange-500' : 'text-red-600'}`}>
                      {hw.score} 分
                    </span>
                  )}
                </div>
              </div>
              <Badge className={statusConfig[hw.status].color} variant='outline'>
                {hw.status}
              </Badge>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
