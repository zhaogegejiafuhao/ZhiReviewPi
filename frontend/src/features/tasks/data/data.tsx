import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Circle,
  CheckCircle,
  AlertCircle,
  Timer,
  HelpCircle,
  CircleOff,
} from 'lucide-react'

export const labels = [
  {
    value: 'calculation',
    label: '计算题',
  },
  {
    value: 'geometry',
    label: '几何证明',
  },
  {
    value: 'composition',
    label: '作文',
  },
]

export const statuses = [
  {
    label: '待批改',
    value: 'backlog' as const,
    icon: CircleOff,
  },
  {
    label: '批改中',
    value: 'in progress' as const,
    icon: Timer,
  },
  {
    label: '已批改',
    value: 'done' as const,
    icon: CheckCircle,
  },
  {
    label: '待审核',
    value: 'review' as const,
    icon: AlertCircle,
  },
  {
    label: '已审核',
    value: 'verified' as const,
    icon: CheckCircle,
  },
]

export const priorities = [
  {
    label: '高优先级',
    value: 'high' as const,
    icon: ArrowUp,
  },
  {
    label: '中优先级',
    value: 'medium' as const,
    icon: ArrowRight,
  },
  {
    label: '低优先级',
    value: 'low' as const,
    icon: ArrowDown,
  },
]
