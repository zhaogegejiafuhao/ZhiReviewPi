import { createFileRoute } from '@tanstack/react-router'
import { QuestionBankPage } from '@/features/question-bank'

export const Route = createFileRoute('/_authenticated/question-bank/')({
  component: QuestionBankPage,
})
