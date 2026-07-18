import { GraduationCap } from 'lucide-react'
import { type UserStatus } from './schema'

export const callTypes = new Map<UserStatus, string>([
  ['活跃', 'bg-teal-100/30 text-teal-900 dark:text-teal-200 border-teal-200'],
  ['休眠', 'bg-neutral-300/40 border-neutral-300'],
])

export const roles = [
  {
    label: '学生',
    value: '学生',
    icon: GraduationCap,
  },
] as const
