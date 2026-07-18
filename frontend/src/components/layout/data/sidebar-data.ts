import {
  LayoutDashboard,
  ClipboardCheck,
  Brain,
  GraduationCap,
  BookOpen,
  BarChart3,
  Settings,
  Bell,
  FileText,
  Target,
  AlertTriangle,
  Command,
  PenTool,
  Calculator,
  Home,
  CheckSquare,
  Trophy,
  TrendingUp,
  Database,
  Layers,
} from 'lucide-react'
import { type SidebarData } from '../types'

export const sidebarData: SidebarData = {
  user: {
    name: '张老师',
    email: 'zhanglaoshi@school.edu.cn',
    avatar: '/avatars/shadcn.jpg',
  },
  teams: [
    {
      name: '希沃智教π',
      logo: Command,
      plan: '智能作业批改系统',
    },
    {
      name: '七年级2班',
      logo: GraduationCap,
      plan: '2026春季学期',
    },
    {
      name: '八年级1班',
      logo: Calculator,
      plan: '2026春季学期',
    },
  ],
  navGroups: [
    {
      title: '核心功能',
      items: [
        {
          title: '学情总览',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          title: '智能批改',
          url: '/grading',
          icon: PenTool,
        },
        {
          title: '批量批改',
          url: '/batch-grading',
          icon: Layers,
        },
        {
          title: '批改任务',
          url: '/tasks',
          icon: ClipboardCheck,
        },
        {
          title: '知识归因',
          url: '/apps',
          icon: Brain,
        },
        {
          title: '题库管理',
          url: '/question-bank',
          icon: Database,
        },
        {
          title: '学生管理',
          url: '/users',
          icon: GraduationCap,
        },
        {
          title: '错题本',
          url: '/chats',
          badge: '12',
          icon: BookOpen,
        },
      ],
    },
    {
      title: '数据分析',
      items: [
        {
          title: '学情报告',
          url: '/apps',
          icon: BarChart3,
          items: [
            {
              title: '雷达图分析',
              url: '/apps',
              icon: Target,
            },
            {
              title: '薄弱项追踪',
              url: '/apps',
              icon: AlertTriangle,
            },
            {
              title: '衰减传播分析',
              url: '/apps',
              icon: Brain,
            },
            {
              title: '报告导出',
              url: '/apps',
              icon: FileText,
            },
          ],
        },
        {
          title: '学科分析',
          icon: PenTool,
          items: [
            {
              title: '数学学情',
              url: '/apps',
              icon: Calculator,
            },
            {
              title: '作文批改',
              url: '/grading',
              icon: PenTool,
            },
          ],
        },
      ],
    },
    {
      title: '系统',
      items: [
        {
          title: '系统设置',
          icon: Settings,
          items: [
            {
              title: '个人信息',
              url: '/settings',
              icon: GraduationCap,
            },
            {
              title: '消息通知',
              url: '/settings/notifications',
              icon: Bell,
            },
          ],
        },
      ],
    },
  ],
}

// ===== 学生端导航数据 =====
export const studentSidebarData: SidebarData = {
  user: {
    name: '李明',
    email: 'liming@student.edu.cn',
    avatar: '/avatars/shadcn.jpg',
  },
  teams: [
    {
      name: '希沃智教π',
      logo: Command,
      plan: '学生端',
    },
  ],
  navGroups: [
    {
      title: '学习中心',
      items: [
        {
          title: '学习主页',
          url: '/',
          icon: Home,
        },
        {
          title: '待做作业',
          url: '/tasks',
          badge: '3',
          icon: CheckSquare,
        },
        {
          title: '我的错题本',
          url: '/chats',
          icon: BookOpen,
        },
        {
          title: '订正任务',
          url: '/apps',
          badge: '5',
          icon: ClipboardCheck,
        },
      ],
    },
    {
      title: '学情分析',
      items: [
        {
          title: '我的学情报告',
          url: '/users',
          icon: BarChart3,
        },
        {
          title: '薄弱知识点',
          url: '/settings',
          icon: Target,
        },
        {
          title: '进步追踪',
          url: '/settings/account',
          icon: TrendingUp,
        },
        {
          title: '知识雷达图',
          url: '/settings/appearance',
          icon: Brain,
        },
      ],
    },
    {
      title: '成就',
      items: [
        {
          title: '学习成就',
          url: '/sign-in',
          icon: Trophy,
        },
        {
          title: '消息通知',
          url: '/settings/notifications',
          icon: Bell,
        },
      ],
    },
  ],
}
