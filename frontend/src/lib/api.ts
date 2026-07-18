import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 120000,
})

// ===== 批改接口 =====
export async function ocrQuestion(formData: FormData) {
  const res = await api.post('/grade/ocr-question', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data as {
    ocr_task_id: string
    question_ocr: {
      text: string
      confidence: number
      engines_used: string[]
      formulas: string[]
    }
    answer_ocr: {
      text: string
      confidence: number
      engines_used: string[]
      formulas: string[]
    } | null
    is_geometry_detected: boolean
    geometry_detection_source: string
    image_geometry_hints: string[]
  }
}

export async function gradeHomework(formData: FormData) {
  const res = await api.post('/grade', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function getGradingResult(taskId: string) {
  const res = await api.get(`/grade/${taskId}`)
  return res.data
}

export async function reviewGrading(taskId: string, data: {
  teacher_id: string
  review_actions: Array<{
    question_id: string
    action: string
    modifications?: Record<string, unknown>
  }>
  trigger_correction?: boolean
}) {
  const res = await api.put(`/grade/${taskId}/review`, data)
  return res.data
}

// ===== OCR 接口 =====
export async function ocrRecognize(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post('/ocr/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

// ===== 知识归因接口 =====
export async function analyzeKnowledge(studentId: string) {
  const res = await api.post('/analyze', {
    student_id: studentId,
    subject: 'math',
  })
  return res.data
}

// ===== 知识图谱接口 =====
export interface KnowledgeGraphResponse {
  nodes: Record<string, {
    id: string
    name: string
    parent_id: string | null
    level: number
    keywords: string[]
    prerequisites: string[]
  }>
  radar_dimensions: Array<{ id: string; name: string }>
}

export interface PrecomputedGraphResponse {
  ancestors: Record<string, string[]>
  descendants: Record<string, string[]>
  depth: Record<string, number>
  adjacency: Record<string, string[]>
  nodes_count: number
  precomputed: boolean
}

export async function getKnowledgeGraph(): Promise<KnowledgeGraphResponse> {
  const res = await api.get('/knowledge-graph')
  return res.data
}

// ===== 订正接口 =====
export async function submitCorrection(data: {
  original_task_id: string
  student_id: string
  corrections: Array<{ question_id: string; type: string; url?: string }>
}) {
  const res = await api.post('/correction', data)
  return res.data
}

// ===== 柔性Rubric =====
export async function generateRubric(data: {
  question: string
  standard_answer: string
  total_score: number
  subject?: string
  grade?: number
}) {
  const res = await api.post('/rubric/generate', data)
  return res.data
}

// ===== 仪表盘统计接口 =====
export async function getDashboardStats() {
  const res = await api.get('/dashboard/stats')
  return res.data as {
    total_graded: number
    pending_review: number
    correction_rate: number
    weak_points: number
  }
}

export async function getRecentActivity() {
  const res = await api.get('/dashboard/recent-activity')
  return res.data as {
    activities: Array<{
      task_id: string
      student_id: string
      score: number
      max_score: number
      status: string
      flagged: boolean
      confidence: number
    }>
  }
}

// ===== 学情预警接口 =====
export async function getStudentAlerts(studentId: string) {
  const res = await api.get(`/alert/student/${studentId}`)
  return res.data as {
    student_id: string
    alerts: Array<{
      alert_type: string
      knowledge_id?: string
      knowledge_name?: string
      consecutive_errors?: number
      message: string
    }>
    message?: string
  }
}

export async function getClassAlerts(classId: string, studentIds: string[]) {
  const res = await api.post('/alert/class', {
    class_id: classId,
    student_ids: studentIds,
  })
  return res.data as {
    class_id: string
    alerts: Array<{
      alert_type: string
      module_id?: string
      module_name?: string
      weak_ratio?: number
      weak_students?: string[]
      message: string
    }>
    message?: string
  }
}

// ===== 小组协同分析接口 =====
export async function analyzeGroups(groups: Array<{
  group_id: string
  group_name: string
  student_ids: string[]
}>) {
  const res = await api.post('/analyze/group', { groups })
  return res.data
}

// ===== 模型路由统计接口 =====
export async function getModelRouterStats() {
  const res = await api.get('/model-router/stats')
  return res.data
}

export async function submitModelFeedback(data: {
  model_id: string
  question_type: string
  was_corrected: boolean
}) {
  const res = await api.post('/model-router/feedback', data)
  return res.data
}

// ===== 作文归因接口 =====
export async function analyzeWriting(studentId: string, writingErrors: Array<{
  error_cause: string
  error_weight: number
  essay_title?: string
  date?: string
}>) {
  const res = await api.post('/analyze/writing', {
    student_id: studentId,
    writing_errors: writingErrors,
  })
  return res.data
}

export async function getWritingGraph() {
  const res = await api.get('/writing-graph')
  return res.data
}

// ===== 跨学科接口 =====
export async function getSubjects() {
  const res = await api.get('/subjects')
  return res.data
}

export async function getSubjectGraph(subject: string) {
  const res = await api.get(`/subjects/${subject}/graph`)
  return res.data
}

// ===== 批量批改接口 =====
export async function createBatchGrade(formData: FormData) {
  const res = await api.post('/batch/grade', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function getBatchStatus(batchId: string) {
  const res = await api.get(`/batch/${batchId}/status`)
  return res.data
}

export async function executeBatch(batchId: string) {
  const res = await api.post(`/batch/${batchId}/execute`)
  return res.data
}

export async function getBatchResults(batchId: string) {
  const res = await api.get(`/batch/${batchId}/results`)
  return res.data
}

// ===== 分层订正接口 =====
export async function getPersonalizedCorrection(studentId: string) {
  const res = await api.post('/correction/personalized', {
    student_id: studentId,
  })
  return res.data
}

// ===== 导出接口 =====
export async function exportReport(studentId: string, format: 'json' | 'csv' | 'word' | 'pdf') {
  const res = await api.get(`/export/${studentId}/${format}`, {
    responseType: 'blob',
  })
  return res.data
}

// ===== Rubric缓存管理 =====
export async function clearRubricCache() {
  const res = await api.delete('/rubric/cache')
  return res.data
}

// ===== 答案审查接口 =====
export async function reviewAnswer(taskId: string, data: {
  approved: boolean
  corrected_answer?: string
  request_new_solve?: boolean
}) {
  const res = await api.put(`/grade/${taskId}/answer_review`, data)
  return res.data
}

// ===== 题库管理接口 =====
export async function getQuestionBankStats() {
  const res = await api.get('/question_bank/stats')
  return res.data as {
    total: number
    valid: number
    invalid: number
    by_source: Record<string, number>
  }
}

export async function getQuestionBankList(params?: {
  status_filter?: string
  source_filter?: string
  search?: string
}) {
  const res = await api.get('/question_bank/list', { params })
  return res.data as {
    total: number
    entries: Array<{
      question_hash: string
      question: string
      standard_answer: string
      source: string
      status: string
      subject: string
      grade: number
      total_score: number
      created_at: string
      updated_at: string
    }>
  }
}

export async function deleteQuestionBankEntry(questionHash: string) {
  const res = await api.delete(`/question_bank/${questionHash}`)
  return res.data
}

export async function correctQuestionBankAnswer(questionHash: string, data: {
  new_answer?: string
  request_new_solve?: boolean
}) {
  const res = await api.put(`/question_bank/${questionHash}/correct`, data)
  return res.data
}

// ===== 知识图谱预计算 =====
export async function getPrecomputedGraph(): Promise<PrecomputedGraphResponse> {
  const res = await api.get('/knowledge-graph/precomputed')
  return res.data
}

// ===== 错题本接口 =====
export interface ErrorBookStats {
  total_errors: number
  pending_count: number
  corrected_count: number
  correction_rate: number
  error_type_distribution: Record<string, number>
}

export async function getErrorBookList(params: { page: number; page_size: number }) {
  const res = await api.get('/error-book/list', { params })
  return res.data as {
    total: number
    items: Array<{
      task_id: string
      student_id: string
      question: string
      student_answer_ocr: string
      standard_answer: string
      suggested_score: number
      max_score: number
      error_type: string
      knowledge_points: string[]
      correction_status: 'pending' | 'corrected' | 'failed'
      date: string
      comment: string
    }>
  }
}

export async function getErrorBookStats() {
  const res = await api.get('/error-book/stats')
  return res.data as ErrorBookStats
}

export async function getSimilarQuestions(taskId: string) {
  const res = await api.get(`/error-book/${taskId}/similar`)
  return res.data as {
    questions: Array<{
      id: string
      question: string
      standard_answer: string
      difficulty: string
    }>
  }
}

export async function submitPractice(data: {
  task_id: string
  student_id: string
  practice_answer: string
}) {
  const res = await api.post('/error-book/practice', data)
  return res.data as {
    correct: boolean
    score: number
    feedback: string
  }
}

// ===== 健康检查 =====
export async function healthCheck() {
  const res = await api.get('/health')
  return res.data
}

export default api
