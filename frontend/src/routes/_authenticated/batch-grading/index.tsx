import { createFileRoute } from '@tanstack/react-router'
import { BatchGradingPage } from '@/features/batch-grading'

export const Route = createFileRoute('/_authenticated/batch-grading/')({
  component: BatchGradingPage,
})
