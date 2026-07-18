import { useEffect, useState } from 'react'
import { BookOpen } from 'lucide-react'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { useRole } from '@/context/role-provider'
import { StudentTasks } from '@/features/student/tasks'
import { getRecentActivity } from '@/lib/api'
import { TasksDialogs } from './components/tasks-dialogs'
import { TasksPrimaryButtons } from './components/tasks-primary-buttons'
import { TasksProvider } from './components/tasks-provider'
import { TasksTable } from './components/tasks-table'
import { tasks } from './data/tasks'
import { type Task } from './data/schema'

// 将后端最近批改动态适配为 TasksTable 所需的数据格式
function mapActivityToTask(activity: {
  task_id: string
  student_id: string
  score: number
  max_score: number
  status: string
  flagged: boolean
  confidence: number
}): Task {
  const backendStatus = (activity.status || '').toLowerCase()
  let status = 'backlog'
  if (
    backendStatus.includes('complete') ||
    backendStatus.includes('done') ||
    backendStatus.includes('graded')
  ) {
    status = 'done'
  } else if (backendStatus.includes('review')) {
    status = 'review'
  } else if (
    backendStatus.includes('verified') ||
    backendStatus.includes('approved')
  ) {
    status = 'verified'
  } else if (
    backendStatus.includes('progress') ||
    backendStatus.includes('grading')
  ) {
    status = 'in progress'
  }

  let priority = 'low'
  if (activity.flagged) {
    priority = 'high'
  } else if (activity.confidence < 0.8) {
    priority = 'medium'
  }

  return {
    id: activity.task_id,
    title: `学生 ${activity.student_id} 批改任务`,
    status,
    label: 'calculation',
    priority,
  }
}

export function Tasks() {
  const { role } = useRole()
  const [taskData, setTaskData] = useState<Task[]>(tasks)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const data = await getRecentActivity()
        if (!mounted) return
        const activities = data?.activities ?? []
        if (activities.length === 0) {
          // fallback：保留 Mock 数据
          return
        }
        setTaskData(activities.map(mapActivityToTask))
      } catch {
        // fallback：保留 Mock 数据
      } finally {
        if (mounted) setLoading(false)
      }
    })()
    return () => {
      mounted = false
    }
  }, [])

  if (role === 'student') {
    return (
      <>
        <Header fixed>
          <Search className='me-auto' />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </Header>
        <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
          <StudentTasks />
        </Main>
      </>
    )
  }

  return (
    <TasksProvider>
      <Header fixed>
        <Search className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-wrap items-end justify-between gap-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>批改任务</h2>
            <p className='text-muted-foreground'>
              查看和管理班级批改任务
            </p>
          </div>
          <TasksPrimaryButtons />
        </div>
        {loading ? (
          // 骨架表格
          <div className='overflow-hidden rounded-md border'>
            <div className='border-b bg-muted/50 px-4 py-3'>
              <div className='flex items-center gap-4'>
                <div className='h-4 w-32 animate-pulse rounded bg-muted' />
                <div className='h-4 w-24 animate-pulse rounded bg-muted' />
                <div className='h-4 w-20 animate-pulse rounded bg-muted' />
                <div className='h-4 w-16 animate-pulse rounded bg-muted' />
              </div>
            </div>
            <div>
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className='flex items-center gap-4 border-b last:border-0 px-4 py-3'
                >
                  <div className='h-4 w-4 animate-pulse rounded bg-muted' />
                  <div className='h-4 w-48 animate-pulse rounded bg-muted' />
                  <div className='h-5 w-16 animate-pulse rounded-full bg-muted' />
                  <div className='h-5 w-12 animate-pulse rounded-full bg-muted' />
                  <div className='h-5 w-10 animate-pulse rounded-full bg-muted' />
                  <div className='ml-auto h-4 w-16 animate-pulse rounded bg-muted' />
                </div>
              ))}
            </div>
          </div>
        ) : taskData.length === 0 ? (
          <div className='flex h-48 flex-col items-center justify-center gap-3 rounded-lg border border-dashed text-muted-foreground'>
            <BookOpen className='h-12 w-12 opacity-40' />
            <div className='text-center'>
              <p className='font-medium'>暂无批改任务</p>
              <p className='mt-1 text-xs'>提交作业后，批改任务将显示在这里</p>
            </div>
          </div>
        ) : (
          <TasksTable data={taskData} />
        )}
      </Main>

      <TasksDialogs />
    </TasksProvider>
  )
}
