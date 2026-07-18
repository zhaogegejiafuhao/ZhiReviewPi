import { GraduationCap, BookOpen } from 'lucide-react'
import { useLayout } from '@/context/layout-provider'
import { useRole } from '@/context/role-provider'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { sidebarData, studentSidebarData } from './data/sidebar-data'
import { NavGroup } from './nav-group'
import { NavUser } from './nav-user'
import { TeamSwitcher } from './team-switcher'

export function AppSidebar() {
  const { collapsible, variant } = useLayout()
  const { role, setRole } = useRole()
  const currentData = role === 'teacher' ? sidebarData : studentSidebarData

  return (
    <Sidebar collapsible={collapsible} variant={variant}>
      <SidebarHeader>
        <TeamSwitcher teams={currentData.teams} />
        {/* 角色切换 */}
        <div className='flex gap-1 px-2 py-1'>
          <Button
            variant={role === 'teacher' ? 'default' : 'outline'}
            size='sm'
            className='flex-1 text-xs'
            onClick={() => setRole('teacher')}
          >
            <GraduationCap className='mr-1 h-3 w-3' />
            教师
          </Button>
          <Button
            variant={role === 'student' ? 'default' : 'outline'}
            size='sm'
            className='flex-1 text-xs'
            onClick={() => setRole('student')}
          >
            <BookOpen className='mr-1 h-3 w-3' />
            学生
          </Button>
        </div>
      </SidebarHeader>
      <SidebarContent className='overflow-y-auto'>
        {currentData.navGroups.map((props) => (
          <NavGroup key={props.title} {...props} />
        ))}
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={currentData.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
