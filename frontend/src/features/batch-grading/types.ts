/** 批量批改相关 TypeScript 类型定义 */

/** 单个上传文件条目（前端状态） */
export interface FileEntry {
  id: string
  file: File
  preview: string // URL.createObjectURL 生成的预览 URL
  studentId: string
  homeworkId: string
}

/** 通用参数 */
export interface CommonParams {
  subject: string
  question: string
  standardAnswer: string
  totalScore: number
}

/** 后端批量状态响应 */
export interface BatchStatusResponse {
  batch_id: string
  total: number
  completed: number
  failed: number
  pending: number
  progress_pct: number
  status: 'pending' | 'processing' | 'completed'
  current_task: {
    task_id: string
    student_id: string
    homework_id: string
    priority: number
    ocr_confidence: number
  } | null
  created_at: string
}

/** 后端单个批改结果 */
export interface BatchResultItem {
  task_id: string
  homework_id: string
  student_id: string
  status: 'completed' | 'failed'
  error?: string
  review_status?: string
  question?: string
  standard_answer?: string
  answer_source?: string
  ocr_result?: {
    text: string
    confidence: number
    engines_used: string[]
  }
  rubric?: Record<string, unknown>
  grading?: {
    total_score: number
    max_score: number
    error_type: string
    knowledge_points: string[]
    steps: Array<{
      step_id: string
      content: string
      correct: boolean
      score: number
      error_reason?: string
    }>
  }
  comment?: string
  suggested_score?: number
  max_score?: number
  confidence?: number
  flagged?: boolean
  model_key?: string
}

/** 批量结果响应 */
export interface BatchResultsResponse {
  batch_id: string
  count: number
  results: BatchResultItem[]
}

/** 页面阶段 */
export type Phase =