import { useEffect, useState } from 'react'
import { Icon } from '@iconify-icon/react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { TopNav } from '@/components/layout/top-nav'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { Analytics } from './components/analytics'
import { Overview } from './components/overview'
import { RecentActivity } from './components/recent-activity'
import { getDashboardStats } from '@/lib/api'
import { useRole } from '@/context/role-provider'
import { StudentDashboard } from '@/features/student/dashboard'

interface DashboardStats {
  total_graded: number
  pending_review: number
  correction_rate: number
  weak_points: number
}

export function Dashboard() {
  const { role } = useRole()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDashboardStats()
      .then((data) => setStats(data))
      .catch(() => {
        // 后端未启动时使用默认数据
        setStats({ total_graded: 128, pending_review: 23, correction_rate: 87.3, weak_points: 3 })
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <>
      {/* ===== 顶部导航 ===== */}
      <Header>
        <TopNav links={topNav} className='me-auto' />
        <Search />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      {/* ===== 主内容区 ===== */}
      <Main>
        {role === 'student' ? (
          <StudentDashboard />
        ) : (
        <>
        <div className='mb-2 flex items-center justify-between space-y-2'>
          <h1 className='text-2xl font-bold tracking-tight'>学情总览</h1>
          <div className='flex items-center space-x-2'>
            <Button>导出报告</Button>
          </div>
        </div>
        <Tabs
          orientation='vertical'
          defaultValue='overview'
          className='space-y-4'
        >
          <div className='w-full overflow-x-auto pb-2'>
            <TabsList>
              <TabsTrigger value='overview'>总览</TabsTrigger>
              <TabsTrigger value='analytics'>学情分析</TabsTrigger>
              <TabsTrigger value='reports'>
                知识归因
              </TabsTrigger>
              <TabsTrigger value='notifications' disabled>
                预警通知
              </TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value='overview' className='space-y-4'>
            {/* ===== 四大核心指标卡片 ===== */}
            <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
              {loading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <Card key={i}>
                    <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                      <div className='h-4 w-20 animate-pulse rounded bg-muted' />
                      <div className='h-4 w-4 animate-pulse rounded bg-muted' />
                    </CardHeader>
                    <CardContent>
                      <div className='h-8 w-24 animate-pulse rounded bg-muted' />
                      <div className='mt-2 h-3 w-32 animate-pulse rounded bg-muted' />
                    </CardContent>
                  </Card>
                ))
              ) : (
                <>
              <Card>
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-sm font-medium'>
                    今日批改
                  </CardTitle>
                  <Icon icon='lucide:clipboard-check' className='h-4 w-4 text-muted-foreground' />
                </CardHeader>
                <CardContent>
                  <div className='text-2xl font-bold'>{stats?.total_graded ?? '—'} 份</div>
                  <p className='text-xs text-muted-foreground'>
                    较昨日 +12.5%
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-sm font-medium'>
                    待审核
                  </CardTitle>
                  <Icon icon='lucide:clock' className='h-4 w-4 text-muted-foreground' />
                </CardHeader>
                <CardContent>
                  <div className='text-2xl font-bold'>{stats?.pending_review ?? '—'} 份</div>
                  <p className='text-xs text-muted-foreground'>
                    低置信度 5 份需人工复核
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-sm font-medium'>
                    订正完成率
                  </CardTitle>
                  <Icon icon='lucide:check-circle' className='h-4 w-4 text-muted-foreground' />
                </CardHeader>
                <CardContent>
                  <div className='text-2xl font-bold'>{stats?.correction_rate ?? '—'}%</div>
                  <p className='text-xs text-muted-foreground'>
                    较上周提升 3.2%
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-sm font-medium'>
                    班级薄弱点
                  </CardTitle>
                  <Icon icon='lucide:alert-triangle' className='h-4 w-4 text-muted-foreground' />
                </CardHeader>
                <CardContent>
                  <div className='text-2xl font-bold'>{stats?.weak_points ?? '—'} 个</div>
                  <p className='text-xs text-muted-foreground'>
                    相似三角形 / 二次函数 / 证明题
                  </p>
                </CardContent>
              </Card>
                </>
              )}
            </div>

            {/* ===== 图表区域 ===== */}
            <div className='grid grid-cols-1 gap-4 lg:grid-cols-7'>
              <Card className='col-span-1 lg:col-span-4'>
                <CardHeader>
                  <CardTitle>批改量趋势</CardTitle>
                  <CardDescription>近12个月批改作业数量</CardDescription>
                </CardHeader>
                <CardContent className='ps-2'>
                  <Overview />
                </CardContent>
              </Card>
              <Card className='col-span-1 lg:col-span-3'>
                <CardHeader>
                  <CardTitle>最近批改动态</CardTitle>
                  <CardDescription>
                    今日已完成 {stats?.total_graded ?? 128} 份批改
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <RecentActivity />
                </CardContent>
              </Card>
            </div>
          </TabsContent>
          <TabsContent value='analytics' className='space-y-4'>
            <Analytics />
          </TabsContent>
        </Tabs>
        </>
        )}
      </Main>
    </>
  )
}

const topNav = [
  {
    title: '总览',
    href: 'dashboard/overview',
    isActive: true,
    disabled: false,
  },
  {
    title: '学生列表',
    href: 'dashboard/students',
    isActive: false,
    disabled: true,
  },
  {
    title: '错题统计',
    href: 'dashboard/errors',
    isActive: false,
    disabled: true,
  },
  {
    title: '设置',
    href: 'dashboard/settings',
    isActive: false,
    disabled: true,
  },
]
