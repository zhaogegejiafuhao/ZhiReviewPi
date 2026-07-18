import { useState, useRef, useEffect } from 'react'
import { Upload, Loader2, CheckCircle, AlertTriangle, FileText, History, Sparkles, ThumbsUp, ThumbsDown, RefreshCw, ArrowLeft, ChevronRight, Image as ImageIcon, Shapes } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ocrQuestion, gradeHomework, getRecentActivity, reviewAnswer } from '@/lib/api'
import type { AxiosError } from 'axios'

// ===== 类型定义 =====

type GradingStep = 'question_ocr' | 'student_grade'

interface GradingResult {
  task_id: string
  status: string
  review_status: string
  student_id: string
  message?: string
  ai_generated_answer?: {
    solution: string
    final_answer: string
    standard_answer: string
    rubric_suggestion: Record<string, unknown>
  }
  answer_source?: string
  ocr_result: {
    text: string
    confidence: number
    engines_used: string[]
  }
  grading: {
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
  comment: string
  rubric: Record<string, unknown>
  suggested_score: number
  confidence: number
  flagged: boolean
}

interface OcrResult {
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

// ===== 步骤指示器 =====

function StepIndicator({ step }: { step: GradingStep }) {
  const isStep1 = step === 'question_ocr'
  const isStep2 = step === 'student_grade'

  return (
    <div className='flex items-center justify-center gap-2 py-4'>
      {/* Step 1 */}
      <div className='flex items-center gap-2'>
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold transition-colors ${
            isStep2
              ? 'bg-primary text-primary-foreground'
              : 'bg-primary text-primary-foreground'
          }`}
        >
          {isStep2 ? <CheckCircle className='h-4 w-4' /> : '1'}
        </div>
        <span
          className={`text-sm font-medium ${
            isStep1 ? 'text-foreground' : isStep2 ? 'text-foreground' : 'text-muted-foreground'
          }`}
        >
          题目识别
        </span>
      </div>

      {/* 连线 */}
      <div className={`h-0.5 w-12 ${isStep2 ? 'bg-primary' : 'bg-muted-foreground/30'}`} />
      <ChevronRight className={`h-4 w-4 ${isStep2 ? 'text-primary' : 'text-muted-foreground/30'}`} />
      <div className={`h-0.5 w-12 ${isStep2 ? 'bg-primary' : 'bg-muted-foreground/30'}`} />

      {/* Step 2 */}
      <div className='flex items-center gap-2'>
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold transition-colors ${
            isStep2
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-muted-foreground'
          }`}
        >
          2
        </div>
        <span
          className={`text-sm font-medium ${
            isStep2 ? 'text-foreground' : 'text-muted-foreground'
          }`}
        >
          作业批改
        </span>
      </div>
    </div>
  )
}

// ===== 单图上传组件 =====

function SingleImageUpload({
  label,
  hint,
  required,
  preview,
  onFileChange,
  onRemove,
  fileInputRef,
}: {
  label: string
  hint?: string
  required?: boolean
  preview: string | null
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  onRemove: () => void
  fileInputRef: React.RefObject<HTMLInputElement | null>
}) {
  return (
    <div className='space-y-1.5'>
      <Label className='flex items-center gap-1'>
        {label}
        {required && <span className='text-destructive'>*</span>}
        {hint && <span className='text-xs text-muted-foreground font-normal'>({hint})</span>}
      </Label>
      <div
        className='flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/25 p-4 transition-colors hover:border-primary/50'
        onClick={() => fileInputRef.current?.click()}
      >
        {preview ? (
          <div className='group relative'>
            <img
              src={preview}
              alt='预览'
              className='h-32 rounded-md object-contain border shadow-sm'
            />
            <button
              type='button'
              className='absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white opacity-0 transition-opacity group-hover:opacity-100'
              onClick={(e) => { e.stopPropagation(); onRemove() }}
            >
              ×
            </button>
          </div>
        ) : (
          <>
            <ImageIcon className='mb-1 h-8 w-8 text-muted-foreground' />
            <p className='text-xs text-muted-foreground'>点击上传图片</p>
          </>
        )}
        <input
          ref={fileInputRef}
          type='file'
          accept='image/*'
          className='hidden'
          onChange={onFileChange}
        />
      </div>
    </div>
  )
}

// ===== 主页面组件 =====

export function GradingPage() {
  // 步骤控制
  const [step, setStep] = useState<GradingStep>('question_ocr')

  // ===== Step 1 状态 =====
  const [questionFile, setQuestionFile] = useState<File | null>(null)
  const [questionPreview, setQuestionPreview] = useState<string | null>(null)
  const [answerFile, setAnswerFile] = useState<File | null>(null)
  const [answerPreview, setAnswerPreview] = useState<string | null>(null)
  const [subject, setSubject] = useState('math')
  const [grade, setGrade] = useState('6')
  const [totalScore, setTotalScore] = useState('5')

  // OCR 相关
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrResult, setOcrResult] = useState<OcrResult | null>(null)
  const [editQuestion, setEditQuestion] = useState('')
  const [editAnswer, setEditAnswer] = useState('')
  const [ocrError, setOcrError] = useState<string | null>(null)

  // Step 1 传递到 Step 2 的确认数据
  const [ocrTaskId, setOcrTaskId] = useState('')
  const [confirmedQuestion, setConfirmedQuestion] = useState('')
  const [confirmedAnswer, setConfirmedAnswer] = useState('')
  const [isGeometryDetected, setIsGeometryDetected] = useState(false)

  // Step 1 文件引用
  const questionInputRef = useRef<HTMLInputElement>(null)
  const answerInputRef = useRef<HTMLInputElement>(null)

  // ===== Step 2 状态 =====
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<GradingResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const studentFileInputRef = useRef<HTMLInputElement>(null)
  const [showResult, setShowResult] = useState(false)
  const [animatedScore, setAnimatedScore] = useState(0)
  const [animatedProgress, setAnimatedProgress] = useState(0)

  // 答案审查状态
  const [answerReviewLoading, setAnswerReviewLoading] = useState(false)
  const [correctedAnswer, setCorrectedAnswer] = useState('')

  // 历史批改记录
  const [history, setHistory] = useState<
    Array<{
      task_id: string
      student_id: string
      score: number
      max_score: number
      status: string
      flagged: boolean
      confidence: number
    }>
  >([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState<string | null>(null)

  const loadHistory = async () => {
    setHistoryLoading(true)
    setHistoryError(null)
    try {
      const data = await getRecentActivity()
      setHistory(data.activities || [])
    } catch (err) {
      setHistory([])
      const msg = err instanceof Error ? err.message : '未知错误'
      setHistoryError(`加载历史记录失败：${msg}`)
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    loadHistory()
  }, [])

  // ===== Step 1 处理函数 =====

  const handleQuestionFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setQuestionFile(file)
    const reader = new FileReader()
    reader.onloadend = () => setQuestionPreview(reader.result as string)
    reader.readAsDataURL(file)
    if (questionInputRef.current) questionInputRef.current.value = ''
  }

  const handleAnswerFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAnswerFile(file)
    const reader = new FileReader()
    reader.onloadend = () => setAnswerPreview(reader.result as string)
    reader.readAsDataURL(file)
    if (answerInputRef.current) answerInputRef.current.value = ''
  }

  const handleOcr = async () => {
    if (!questionFile) return
    setOcrLoading(true)
    setOcrError(null)
    setOcrResult(null)

    try {
      const formData = new FormData()
      formData.append('question_image', questionFile)
      if (answerFile) {
        formData.append('answer_image', answerFile)
      }
      formData.append('subject', subject)
      formData.append('grade', grade)
      formData.append('total_score', totalScore)

      const data = await ocrQuestion(formData)
      setOcrResult(data)
      setEditQuestion(data.question_ocr.text)
      setEditAnswer(data.answer_ocr?.text || '')
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      setOcrError(axiosErr.response?.data?.detail || 'OCR识别失败，请检查后端是否启动')
    } finally {
      setOcrLoading(false)
    }
  }

  const handleConfirmAndContinue = () => {
    if (!ocrResult) return
    setOcrTaskId(ocrResult.ocr_task_id)
    setConfirmedQuestion(editQuestion)
    setConfirmedAnswer(editAnswer)
    setIsGeometryDetected(ocrResult.is_geometry_detected)
    setStep('student_grade')
    // 重置 Step 2 的状态
    setFiles([])
    setPreviews([])
    setResult(null)
    setError(null)
    setShowResult(false)
    setAnimatedScore(0)
    setAnimatedProgress(0)
  }

  // ===== Step 2 处理函数 =====

  const handleStudentFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files
    if (!selectedFiles || selectedFiles.length === 0) return

    const newFiles = Array.from(selectedFiles)
    const newPreviews: string[] = []

    let loaded = 0
    for (const f of newFiles) {
      const reader = new FileReader()
      reader.onloadend = () => {
        newPreviews.push(reader.result as string)
        loaded++
        if (loaded === newFiles.length) {
          setFiles((prev) => [...prev, ...newFiles])
          setPreviews((prev) => [...prev, ...newPreviews])
        }
      }
      reader.readAsDataURL(f)
    }
    if (studentFileInputRef.current) studentFileInputRef.current.value = ''
  }

  const removeStudentFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
    setPreviews((prev) => prev.filter((_, i) => i !== index))
  }

  const handleGrade = async () => {
    if (files.length === 0) return
    setLoading(true)
    setError(null)
    setResult(null)
    setShowResult(false)
    setAnimatedScore(0)
    setAnimatedProgress(0)

    try {
      const formData = new FormData()
      for (const f of files) {
        formData.append('files', f, f.name)
      }
      formData.append('homework_id', 'hw_001')
      formData.append('student_id', 'stu_001')
      formData.append('subject', subject)
      formData.append('total_score', totalScore)
      formData.append('ocr_task_id', ocrTaskId)
      formData.append('question', confirmedQuestion)
      formData.append('standard_answer', confirmedAnswer)

      const data = await gradeHomework(formData)
      setResult(data)
      setShowResult(true)
      loadHistory()

      // 得分数字动画
      const targetScore = data.suggested_score
      const maxScore = data.grading?.max_score || Number(totalScore)
      const targetProgress = Math.round((targetScore / maxScore) * 100)
      const duration = 800
      const steps = 30
      const stepTime = duration / steps
      let currentStep = 0
      const timer = setInterval(() => {
        currentStep++
        const progress = currentStep / steps
        const eased = 1 - Math.pow(1 - progress, 3)
        setAnimatedScore(Number((eased * targetScore).toFixed(1)))
        setAnimatedProgress(Math.round(eased * targetProgress))
        if (currentStep >= steps) {
          setAnimatedScore(targetScore)
          setAnimatedProgress(targetProgress)
          clearInterval(timer)
        }
      }, stepTime)
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      setError(axiosErr.response?.data?.detail || '批改请求失败，请检查后端是否启动')
    } finally {
      setLoading(false)
    }
  }

  // 答案审查
  const handleAnswerReview = async (approved: boolean, correctedAnswerValue?: string) => {
    if (!result) return
    setAnswerReviewLoading(true)
    try {
      const data = await reviewAnswer(result.task_id, {
        approved,
        corrected_answer: correctedAnswerValue || undefined,
      })
      setResult(data)
      setShowResult(true)
      if (data.status === 'completed') {
        const targetScore = data.suggested_score
        const maxScore = data.grading?.max_score || Number(totalScore)
        const targetProgress = Math.round((targetScore / maxScore) * 100)
        setAnimatedScore(targetScore)
        setAnimatedProgress(targetProgress)
      }
      loadHistory()
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      setError(axiosErr.response?.data?.detail || '答案审查请求失败')
    } finally {
      setAnswerReviewLoading(false)
    }
  }

  // ===== 渲染 =====

  return (
    <div className='space-y-6'>
      <div className='flex items-center justify-between'>
        <h1 className='text-2xl font-bold tracking-tight'>智能批改</h1>
      </div>

      {/* 步骤指示器 */}
      <StepIndicator step={step} />

      {/* ===== Step 1: 题目识别 ===== */}
      {step === 'question_ocr' && (
        <div className='grid grid-cols-1 gap-6 lg:grid-cols-2'>
          {/* 左侧：上传 & 参数 */}
          <Card>
            <CardHeader>
              <CardTitle>题目识别</CardTitle>
              <CardDescription>上传题目和答案图片，AI自动进行OCR识别</CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              {/* 图片上传区 */}
              <div className='grid grid-cols-2 gap-4'>
                <SingleImageUpload
                  label='题目图片'
                  required
                  preview={questionPreview}
                  onFileChange={handleQuestionFileChange}
                  onRemove={() => { setQuestionFile(null); setQuestionPreview(null) }}
                  fileInputRef={questionInputRef}
                />
                <SingleImageUpload
                  label='答案图片'
                  hint='留空则AI自动解题'
                  preview={answerPreview}
                  onFileChange={handleAnswerFileChange}
                  onRemove={() => { setAnswerFile(null); setAnswerPreview(null) }}
                  fileInputRef={answerInputRef}
                />
              </div>

              {/* 参数 */}
              <div className='space-y-3'>
                <div className='grid grid-cols-3 gap-3'>
                  <div>
                    <Label>学科</Label>
                    <Select value={subject} onValueChange={setSubject}>
                      <SelectTrigger className='w-full'>
                        <SelectValue placeholder='选择学科' />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='math'>数学</SelectItem>
                        <SelectItem value='chinese'>语文</SelectItem>
                        <SelectItem value='english'>英语</SelectItem>
                        <SelectItem value='physics'>物理</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>年级</Label>
                    <Select value={grade} onValueChange={setGrade}>
                      <SelectTrigger className='w-full'>
                        <SelectValue placeholder='选择年级' />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='1'>一年级</SelectItem>
                        <SelectItem value='2'>二年级</SelectItem>
                        <SelectItem value='3'>三年级</SelectItem>
                        <SelectItem value='4'>四年级</SelectItem>
                        <SelectItem value='5'>五年级</SelectItem>
                        <SelectItem value='6'>六年级</SelectItem>
                        <SelectItem value='7'>初一</SelectItem>
                        <SelectItem value='8'>初二</SelectItem>
                        <SelectItem value='9'>初三</SelectItem>
                        <SelectItem value='10'>高一</SelectItem>
                        <SelectItem value='11'>高二</SelectItem>
                        <SelectItem value='12'>高三</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>满分</Label>
                    <Input
                      type='number'
                      value={totalScore}
                      onChange={(e) => setTotalScore(e.target.value)}
                      placeholder='5'
                    />
                  </div>
                </div>

                <Button
                  className='w-full'
                  onClick={handleOcr}
                  disabled={!questionFile || ocrLoading}
                >
                  {ocrLoading ? (
                    <>
                      <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                      识别中...
                    </>
                  ) : (
                    <>
                      <FileText className='mr-2 h-4 w-4' />
                      识别题目
                    </>
                  )}
                </Button>
              </div>

              {ocrError && (
                <div className='rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300'>
                  {ocrError}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 右侧：OCR 识别结果 */}
          <Card>
            <CardHeader>
              <CardTitle>识别结果</CardTitle>
              <CardDescription>
                {ocrResult
                  ? '请检查并编辑识别内容，确认无误后继续'
                  : '上传题目图片并点击"识别题目"查看结果'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {ocrResult ? (
                <div className='space-y-4'>
                  {/* 几何检测徽章 */}
                  {ocrResult.is_geometry_detected && (
                    <div className='flex items-center gap-2 rounded-lg bg-amber-50 p-3 dark:bg-amber-900/20'>
                      <Shapes className='h-4 w-4 text-amber-600 dark:text-amber-400' />
                      <span className='text-sm font-medium text-amber-700 dark:text-amber-300'>
                        检测到几何图形
                      </span>
                      {ocrResult.geometry_detection_source && (
                        <Badge variant='outline' className='text-xs'>
                          {ocrResult.geometry_detection_source}
                        </Badge>
                      )}
                    </div>
                  )}

                  {/* OCR 置信度 */}
                  <div className='flex items-center gap-2'>
                    <span className='text-sm text-muted-foreground'>OCR置信度：</span>
                    <Badge
                      variant={
                        ocrResult.question_ocr.confidence > 0.8
                          ? 'default'
                          : ocrResult.question_ocr.confidence > 0.5
                            ? 'secondary'
                            : 'destructive'
                      }
                    >
                      {(ocrResult.question_ocr.confidence * 100).toFixed(1)}%
                    </Badge>
                    {ocrResult.question_ocr.engines_used.length > 0 && (
                      <span className='text-xs text-muted-foreground'>
                        引擎: {ocrResult.question_ocr.engines_used.join(', ')}
                      </span>
                    )}
                  </div>

                  {/* 题目文本编辑 */}
                  <div className='space-y-1.5'>
                    <Label className='flex items-center gap-1'>
                      <FileText className='h-3.5 w-3.5' />
                      题目文本
                    </Label>
                    <Textarea
                      value={editQuestion}
                      onChange={(e) => setEditQuestion(e.target.value)}
                      rows={4}
                      className='text-sm'
                      placeholder='OCR识别的题目内容（可编辑）'
                    />
                  </div>

                  {/* 答案文本编辑 */}
                  <div className='space-y-1.5'>
                    <Label className='flex items-center gap-1'>
                      <CheckCircle className='h-3.5 w-3.5' />
                      标准答案
                      <span className='text-xs text-muted-foreground font-normal'>
                        {editAnswer ? '' : '（未提供，AI将自动解题）'}
                      </span>
                    </Label>
                    <Textarea
                      value={editAnswer}
                      onChange={(e) => setEditAnswer(e.target.value)}
                      rows={3}
                      className='text-sm'
                      placeholder='OCR识别的答案内容（可编辑，留空则AI自动解题）'
                    />
                  </div>

                  {/* 识别的公式 */}
                  {ocrResult.question_ocr.formulas.length > 0 && (
                    <div className='space-y-1'>
                      <span className='text-xs text-muted-foreground'>识别到的公式：</span>
                      <div className='flex flex-wrap gap-1'>
                        {ocrResult.question_ocr.formulas.map((f, i) => (
                          <Badge key={i} variant='secondary' className='font-mono text-xs'>
                            {f}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 确认并继续 */}
                  <Button
                    className='w-full'
                    onClick={handleConfirmAndContinue}
                    disabled={!editQuestion.trim()}
                  >
                    确认并继续
                    <ChevronRight className='ml-2 h-4 w-4' />
                  </Button>
                </div>
              ) : (
                <div className='flex flex-col items-center justify-center py-12 text-muted-foreground'>
                  <FileText className='mb-2 h-12 w-12' />
                  <p>等待识别结果</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ===== Step 2: 作业批改 ===== */}
      {step === 'student_grade' && (
        <div className='grid grid-cols-1 gap-6 lg:grid-cols-2'>
          {/* 左侧：上传学生作业 */}
          <Card>
            <CardHeader>
              <CardTitle>上传学生作业</CardTitle>
              <CardDescription>上传学生作业图片，AI将根据已识别的题目进行批改</CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              {/* 已确认题目信息摘要（只读） */}
              <div className='rounded-lg border bg-muted/30 p-3 space-y-2'>
                <h4 className='text-xs font-semibold text-muted-foreground uppercase tracking-wider'>已确认题目信息</h4>
                <div className='text-sm'>
                  <span className='text-muted-foreground'>题目：</span>
                  <span className='font-medium'>
                    {confirmedQuestion.length > 80
                      ? confirmedQuestion.slice(0, 80) + '...'
                      : confirmedQuestion}
                  </span>
                </div>
                {confirmedAnswer && (
                  <div className='text-sm'>
                    <span className='text-muted-foreground'>标准答案：</span>
                    <span className='font-medium'>
                      {confirmedAnswer.length > 60
                        ? confirmedAnswer.slice(0, 60) + '...'
                        : confirmedAnswer}
                    </span>
                  </div>
                )}
                <div className='flex items-center gap-2 text-xs text-muted-foreground'>
                  <span>学科: {subject === 'math' ? '数学' : subject === 'chinese' ? '语文' : subject === 'english' ? '英语' : '物理'}</span>
                  <span>|</span>
                  <span>满分: {totalScore}</span>
                  {isGeometryDetected && (
                    <>
                      <span>|</span>
                      <Badge variant='outline' className='text-xs py-0'>
                        <Shapes className='mr-1 h-3 w-3' />
                        几何题
                      </Badge>
                    </>
                  )}
                </div>
              </div>

              {/* 学生作业图片上传区 */}
              <div
                className='flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/25 p-6 transition-colors hover:border-primary/50'
                onClick={() => studentFileInputRef.current?.click()}
              >
                {previews.length > 0 ? (
                  <div className='flex flex-wrap items-center justify-center gap-2'>
                    {previews.map((p, i) => (
                      <div key={i} className='group relative'>
                        <img
                          src={p}
                          alt={`预览 ${i + 1}`}
                          className='h-28 rounded-md object-contain border shadow-sm'
                        />
                        <button
                          type='button'
                          className='absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white opacity-0 transition-opacity group-hover:opacity-100'
                          onClick={(e) => { e.stopPropagation(); removeStudentFile(i) }}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                    <div className='flex h-28 w-28 items-center justify-center rounded-md border-2 border-dashed border-muted-foreground/25 text-muted-foreground hover:border-primary/50'>
                      <span className='text-2xl'>+</span>
                    </div>
                  </div>
                ) : (
                  <>
                    <Upload className='mb-2 h-10 w-10 text-muted-foreground' />
                    <p className='text-sm text-muted-foreground'>
                      点击上传学生作业图片（支持多张）
                    </p>
                  </>
                )}
                <input
                  ref={studentFileInputRef}
                  type='file'
                  accept='image/*'
                  multiple
                  className='hidden'
                  onChange={handleStudentFileChange}
                />
              </div>

              {/* 操作按钮 */}
              <div className='flex gap-2'>
                <Button
                  variant='outline'
                  className='flex-1'
                  onClick={() => setStep('question_ocr')}
                >
                  <ArrowLeft className='mr-2 h-4 w-4' />
                  返回Step 1
                </Button>
                <Button
                  className='flex-[2]'
                  onClick={handleGrade}
                  disabled={files.length === 0 || loading}
                >
                  {loading ? (
                    <>
                      <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                      批改中...
                    </>
                  ) : (
                    '开始批改'
                  )}
                </Button>
              </div>

              {error && (
                <div className='rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300'>
                  {error}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 右侧：批改结果 */}
          <Card className={showResult ? 'animate-in fade-in slide-in-from-bottom-4 duration-500' : ''}>
            <CardHeader>
              <CardTitle>批改结果</CardTitle>
              <CardDescription>
                {result
                  ? `任务ID: ${result.task_id}`
                  : '上传学生作业并点击"开始批改"查看结果'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {result ? (
                result.status === 'needs_answer_review' ? (
                  /* ===== 答案审查状态 ===== */
                  <div className='space-y-4'>
                    <div className='flex items-center gap-2 rounded-lg bg-blue-50 p-3 dark:bg-blue-900/20'>
                      <Sparkles className='h-5 w-5 text-blue-500' />
                      <p className='text-sm text-blue-700 dark:text-blue-300'>
                        {result.message || 'AI已自动解题，请审查答案后继续批改'}
                      </p>
                    </div>

                    {result.ai_generated_answer && (
                      <div className='space-y-3'>
                        <h3 className='font-semibold'>AI生成的解题过程</h3>
                        <div className='rounded-lg border p-3 space-y-2'>
                          <div>
                            <span className='text-muted-foreground text-xs'>解题过程：</span>
                            <p className='text-sm whitespace-pre-wrap'>{result.ai_generated_answer.solution}</p>
                          </div>
                          <div>
                            <span className='text-muted-foreground text-xs'>最终答案：</span>
                            <p className='text-sm font-medium'>{result.ai_generated_answer.final_answer}</p>
                          </div>
                        </div>

                        <div className='space-y-2'>
                          <div className='flex gap-2'>
                            <Button
                              className='flex-1'
                              onClick={() => handleAnswerReview(true)}
                              disabled={answerReviewLoading}
                            >
                              {answerReviewLoading ? <Loader2 className='mr-2 h-4 w-4 animate-spin' /> : <ThumbsUp className='mr-2 h-4 w-4' />}
                              确认通过
                            </Button>
                            <Button
                              variant='destructive'
                              className='flex-1'
                              onClick={() => {
                                if (correctedAnswer.trim()) {
                                  handleAnswerReview(false, correctedAnswer)
                                }
                              }}
                              disabled={answerReviewLoading || !correctedAnswer.trim()}
                            >
                              {answerReviewLoading ? <Loader2 className='mr-2 h-4 w-4 animate-spin' /> : <ThumbsDown className='mr-2 h-4 w-4' />}
                              答案有误，提供修正答案
                            </Button>
                          </div>
                          <Input
                            value={correctedAnswer}
                            onChange={(e) => setCorrectedAnswer(e.target.value)}
                            placeholder='如确认答案有误，请在此输入正确答案'
                            className='text-sm'
                          />
                          <Button
                            variant='outline'
                            size='sm'
                            onClick={() => handleAnswerReview(false)}
                            disabled={answerReviewLoading}
                            className='w-full'
                          >
                            <RefreshCw className='mr-2 h-3 w-3' />
                            要求AI重新解题
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className='space-y-4'>
                    {/* 评分总览 */}
                    <div className='flex items-center gap-4 rounded-lg bg-muted/50 p-4'>
                      <div className='text-center'>
                        <div className='text-3xl font-bold text-primary'>
                          {showResult ? animatedScore : result.suggested_score}
                        </div>
                        <div className='text-sm text-muted-foreground'>
                          / {result.grading?.max_score || totalScore} 分
                        </div>
                      </div>
                      <div className='flex-1 space-y-1'>
                        <div className='h-2 w-full overflow-hidden rounded-full bg-muted'>
                          <div
                            className='h-full rounded-full bg-primary transition-all'
                            style={{ width: `${showResult ? animatedProgress : 0}%`, transition: 'width 0.8s ease-out' }}
                          />
                        </div>
                        <div className='flex items-center gap-2'>
                          <span className='text-sm'>OCR置信度：</span>
                          <Badge
                            variant={
                              result.confidence > 0.8 ? 'default' : 'destructive'
                            }
                          >
                            {(result.confidence * 100).toFixed(1)}%
                          </Badge>
                        </div>
                        <div className='flex items-center gap-2'>
                          <span className='text-sm'>审核状态：</span>
                          <Badge variant='outline'>
                            {result.review_status === 'pending_review'
                              ? '待审核'
                              : '已审核'}
                          </Badge>
                          {result.answer_source && (
                            <Badge variant={
                              result.answer_source.startsWith('cached_') ? 'default' :
                              result.answer_source === 'ai_expanded' ? 'secondary' :
                              result.answer_source === 'ai_generated' ? 'outline' :
                              'outline'
                            }>
                              {result.answer_source === 'user_provided' ? '用户提供' :
                               result.answer_source.startsWith('cached_') ? '题库命中' :
                               result.answer_source === 'ai_expanded' ? 'AI补充完整' :
                               result.answer_source === 'ai_generated' ? 'AI解题' :
                               result.answer_source === 'user_corrected' ? '用户修正' :
                               result.answer_source}
                            </Badge>
                          )}
                        </div>
                        {result.flagged && (
                          <div className='flex items-center gap-1 text-sm text-yellow-600 dark:text-yellow-400'>
                            <AlertTriangle className='h-4 w-4' />
                            低置信度，建议人工复核
                          </div>
                        )}
                      </div>
                    </div>

                    {/* OCR识别结果 */}
                    <div>
                      <h3 className='mb-2 flex items-center gap-2 text-sm font-medium'>
                        <FileText className='h-4 w-4' />
                        OCR识别文本
                      </h3>
                      <div className='rounded-md bg-muted p-3 text-sm'>
                        {result.ocr_result?.text || '无识别结果'}
                      </div>
                    </div>

                    {/* 知识点 */}
                    {result.grading?.knowledge_points?.length > 0 && (
                      <div>
                        <h3 className='mb-2 text-sm font-medium'>涉及知识点</h3>
                        <div className='flex flex-wrap gap-1'>
                          {result.grading.knowledge_points.map((kp: string) => (
                            <Badge key={kp} variant='secondary'>
                              {kp}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* AI评语 */}
                    {result.comment && (
                      <div>
                        <h3 className='mb-2 flex items-center gap-2 text-sm font-medium'>
                          <CheckCircle className='h-4 w-4' />
                          AI评语
                        </h3>
                        <div className='rounded-md border p-3 text-sm'>
                          {result.comment}
                        </div>
                      </div>
                    )}

                    {/* 步骤评分 */}
                    {result.grading?.steps?.length > 0 && (
                      <div>
                        <h3 className='mb-2 text-sm font-medium'>步骤评分</h3>
                        <div className='space-y-2'>
                          {result.grading.steps.map(
                            (step: GradingResult['grading']['steps'][0]) => (
                              <div
                                key={step.step_id}
                                className={`flex items-start gap-2 rounded-md border p-2 text-sm ${
                                  step.correct
                                    ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20'
                                    : 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20'
                                }`}
                              >
                                {step.correct ? (
                                  <CheckCircle className='mt-0.5 h-4 w-4 shrink-0 text-green-600' />
                                ) : (
                                  <AlertTriangle className='mt-0.5 h-4 w-4 shrink-0 text-red-600' />
                                )}
                                <div className='flex-1'>
                                  <div>{step.content}</div>
                                  {step.error_reason && (
                                    <div className='mt-1 text-xs text-red-600'>
                                      错误原因：{step.error_reason}
                                    </div>
                                  )}
                                </div>
                                <span className='shrink-0 font-medium'>
                                  {step.score}分
                                </span>
                              </div>
                            )
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )
              ) : (
                <div className='flex flex-col items-center justify-center py-12 text-muted-foreground'>
                  <FileText className='mb-2 h-12 w-12' />
                  <p>等待批改结果</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ===== 历史批改记录 ===== */}
      <Card>
        <CardHeader>
          <div className='flex items-center justify-between'>
            <div>
              <CardTitle className='flex items-center gap-2'>
                <History className='h-5 w-5' />
                历史批改记录
              </CardTitle>
              <CardDescription>最近批改的作业列表（来自后端 /dashboard/recent-activity）</CardDescription>
            </div>
            <Button variant='outline' size='sm' onClick={loadHistory} disabled={historyLoading}>
              {historyLoading ? '刷新中...' : '刷新'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {historyError && !historyLoading && (
            <div className='mb-3 flex items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs dark:border-amber-800 dark:bg-amber-900/20'>
              <span className='text-amber-700 dark:text-amber-300'>⚠ {historyError}</span>
              <Button variant='outline' size='sm' onClick={loadHistory}>
                重试
              </Button>
            </div>
          )}
          {historyLoading ? (
            <div className='overflow-hidden rounded-md border'>
              <table className='w-full text-sm'>
                <thead className='border-b bg-muted/50'>
                  <tr>
                    <th className='px-3 py-2 text-start font-medium'>任务ID</th>
                    <th className='px-3 py-2 text-start font-medium'>学生</th>
                    <th className='px-3 py-2 text-start font-medium'>得分</th>
                    <th className='px-3 py-2 text-start font-medium'>状态</th>
                    <th className='px-3 py-2 text-start font-medium'>置信度</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i} className='border-b last:border-0'>
                      <td className='px-3 py-2'>
                        <div className='h-3 w-20 animate-pulse rounded bg-muted' />
                      </td>
                      <td className='px-3 py-2'>
                        <div className='h-3 w-16 animate-pulse rounded bg-muted' />
                      </td>
                      <td className='px-3 py-2'>
                        <div className='h-3 w-8 animate-pulse rounded bg-muted' />
                      </td>
                      <td className='px-3 py-2'>
                        <div className='h-5 w-12 animate-pulse rounded-full bg-muted' />
                      </td>
                      <td className='px-3 py-2'>
                        <div className='h-5 w-10 animate-pulse rounded-full bg-muted' />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : history.length === 0 ? (
            <div className='flex h-32 flex-col items-center justify-center gap-2 text-muted-foreground'>
              <History className='h-8 w-8 opacity-40' />
              <div className='text-center'>
                <p className='font-medium'>暂无批改记录</p>
                <p className='mt-1 text-xs'>完成首次批改后，历史记录将显示在这里</p>
              </div>
            </div>
          ) : (
            <div className='overflow-hidden rounded-md border'>
              <table className='w-full text-sm'>
                <thead className='border-b bg-muted/50'>
                  <tr>
                    <th className='px-3 py-2 text-start font-medium'>任务ID</th>
                    <th className='px-3 py-2 text-start font-medium'>学生</th>
                    <th className='px-3 py-2 text-start font-medium'>得分</th>
                    <th className='px-3 py-2 text-start font-medium'>状态</th>
                    <th className='px-3 py-2 text-start font-medium'>置信度</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr key={item.task_id} className='border-b last:border-0 hover:bg-muted/30'>
                      <td className='px-3 py-2 font-mono text-xs text-muted-foreground'>
                        {item.task_id}
                      </td>
                      <td className='px-3 py-2 font-medium'>{item.student_id}</td>
                      <td className='px-3 py-2'>
                        <span className='font-semibold text-primary'>
                          {item.score}
                        </span>
                        <span className='text-muted-foreground'> / {item.max_score}</span>
                      </td>
                      <td className='px-3 py-2'>
                        <Badge
                          variant={
                            item.status === '已批改'
                              ? 'default'
                              : item.status === '待审核'
                                ? 'secondary'
                                : 'destructive'
                          }
                        >
                          {item.status}
                        </Badge>
                        {item.flagged && (
                          <AlertTriangle className='ml-1 inline h-3 w-3 text-yellow-600 dark:text-yellow-400' />
                        )}
                      </td>
                      <td className='px-3 py-2'>
                        <Badge
                          variant={item.confidence > 0.8 ? 'default' : 'destructive'}
                        >
                          {(item.confidence * 100).toFixed(0)}%
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default GradingPage
