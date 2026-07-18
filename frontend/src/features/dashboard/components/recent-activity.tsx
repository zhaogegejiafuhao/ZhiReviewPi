import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'

const activities = [
  {
    student: '李明',
    subject: '数学',
    score: '85/100',
    status: '已批改',
    type: '计算题',
  },
  {
    student: '王芳',
    subject: '数学',
    score: '62/100',
    status: '待审核',
    type: '几何证明',
  },
  {
    student: '张伟',
    subject: '作文',
    score: '78/100',
    status: '已批改',
    type: '议论文',
  },
  {
    student: '赵静',
    subject: '数学',
    score: '45/100',
    status: '低置信',
    type: '二次函数',
  },
  {
    student: '陈浩',
    subject: '数学',
    score: '92/100',
    status: '已批改',
    type: '一元一次方程',
  },
]

const statusColor: Record<string, string> = {
  '已批改': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  '待审核': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  '低置信': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
}

export function RecentActivity() {
  return (
    <div className='space-y-6'>
      {activities.map((activity, index) => (
        <div key={index} className='flex items-center gap-4'>
          <Avatar className='h-9 w-9'>
            <AvatarFallback>{activity.student.slice(0, 1)}</AvatarFallback>
          </Avatar>
          <div className='flex flex-1 flex-wrap items-center justify-between'>
            <div className='space-y-1'>
              <p className='text-sm leading-none font-medium'>
                {activity.student}
              </p>
              <p className='text-sm text-muted-foreground'>
                {activity.subject} · {activity.type}
              </p>
            </div>
            <div className='flex items-center gap-2'>
              <span className='text-sm font-medium'>{activity.score}</span>
              <Badge variant='outline' className={statusColor[activity.status]}>
                {activity.status}
              </Badge>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
