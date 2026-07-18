import { createFileRoute } from '@tanstack/react-router'
import { GradingPage } from '@/features/grading'

export const Route = createFileRoute('/_authenticated/grading/')({
  component: GradingPage,
})
