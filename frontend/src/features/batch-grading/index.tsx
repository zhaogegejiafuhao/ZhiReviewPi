import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Upload,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  X,
  Layers,
  RefreshCw,
  ArrowLeft,
} from 'lucide-react'
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
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  createBatchGrade,
  getBatchStatus,
  executeBatch,
  getBatchResults,
} from '@/lib/api'
import type {
  FileEntry,
  CommonParams,
  BatchStatusResponse,
  BatchResultItem,
  Phase,
} from './types'

const MAX_FILES = 50
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const POLL_INTERVAL = 2000 // 2秒

// ===== 主页面组件 =====
export function BatchGradingPage() {
  const [phase, setPhase] = useState<Phase>('upload')
  const [files, setFiles] = useState<FileEntry[]>([])
  const [commonParams, setCommonParams] = useState<CommonParams>({
    subject: 'math',
    question: '解方程：2x + 3 = 7',
    standardAnswer: 'x = 2',
    totalScore: 5,
  })
  const [batchId, setBatchId] = useState<string | null>(null)
  const [batchStatus, setBatchStatus] = useState<BatchStatusResponse | null>(null)
  const [results, setResults] = useState<BatchResultItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [selectedResult, setSelectedResult] = useState<BatchResultItem | null>(null)

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const submitTimeRef = useRef<number>(0)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 清理预览 URL
  useEffect(() => {
    return () => {
      files.forEach((f) => URL.revokeObjectURL(f.preview))
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 组件卸载时停止轮询
  useEffect(() => {
    return () => stopPolling()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ===== 文件上传处理 =====
  const handleFilesSelected = (fileList: FileList | null) => {
    if (!fileList) return
    const newFiles: FileEntry[] = []
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i]
      if (files.length + newFiles.length >= MAX_FILES) break
      if (file.size > MAX_FILE_SIZE) continue
      if (!file.type.startsWith('image/')) continue
      newFiles.push({
        id: `${Date.now()}_${i}`,
        file,
        preview: URL.createObjectURL(file),
        studentId: `stu_${files.length + newFiles.length + 1}`,
        homeworkId: `hw_batch_${Date.now().toString(36)}`,
      })
    }
    setFiles((prev) => [...prev, ...newFiles])
  }

  const removeFile = (id: string) => {
    setFiles((prev) => {
      const target = prev.find((f) => f.id === id)
      if (target) URL.revokeObjectURL(target.preview)
      return prev.filter((f) => f.id !== id)
    })
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    handleFilesSelected(e.dataTransfer.files)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }

  // ===== 提交与轮询 =====
  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }, [])

  const startPolling = useCallback((bid: string) => {
    const poll = async () => {
      try {
        const data = (await getBatchStatus(bid)) as unknown as BatchStatusResponse
        setBatchStatus(data)
        if (data.status === 'completed') {
          stopPolling()
          const resultsData = await getBatchResults(bid)
          const r = (resultsData as { results: BatchResultItem[] }).results || []
          setResults(r)
          setPhase('results')
        }
        // 检查是否10秒内仍为pending
        if (
          data.status === 'pending' &&
          Date.now() - submitTimeRef.current > 10000
        ) {
          setError('任务未开始执行，请稍后重试')
        }
      } catch {
        // 轮询失败不中断
      }
    }
    poll()
    pollingRef.current = setInterval(poll, POLL_INTERVAL)
  }, [stopPolling])

  const handleSubmit = async () => {
    if (files.length === 0) return
    setPhase('submitting')
    setError(null)
    submitTimeRef.current = Date.now()

    try {
      const formData = new FormData()
      files.forEach((f) => formData.append('files', f.file))

      const tasksJson = files.map((f) => ({
        homework_id: f.homeworkId,
        student_id: f.studentId,
        question: commonParams.question,
        standard_answer: commonParams.standardAnswer,
        total_score: commonParams.totalScore,
        subject: commonParams.subject,
      }))
      formData.append('tasks_json', JSON.stringify(tasksJson))

      const createResult = await createBatchGrade(formData)
      const bid = createResult.batch_id
      setBatchId(bid)

      // fire-and-forget：后端 execute 是同步阻塞的
      void executeBatch(bid)

      setPhase('processing')
      startPolling(bid)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '提交失败'
      setError(msg)
      setPhase('upload')
    }
  }

  const handleReset = () => {
    files.forEach((f) => URL.revokeObjectURL(f.preview))
    setFiles([])
    setPhase('upload')
    setBatchId(null)
    setBatchStatus(null)
    setResults([])
    setError(null)
    setSelectedResult(null)
    stopPolling()
  }

  // ===== 统计计算 =====
  const avgScore =
    results.length > 0
      ? (
          results
            .filter((r) => r.status === 'completed')
            .reduce((sum, r) => sum + (r.suggested_score || 0), 0) /
          results.filter((r) => r.status === 'completed').length
        ).toFixed(1)
      : '0'

  const completedCount = results.filter((r) => r.status === 'completed').length
  const failedCount = results.filter((r) => r.status === 'failed').length

  // ===== 渲染 =====
  return (
    <div className='space-y-6'>
      <div className='flex items-center justify-between'>
        <div>
          <h1 className='text-2xl font-bold tracking-tight'>批量批改</h1>
          <p className='text-muted-foreground text-sm'>
            同时上传多张作业图片，智能调度优先级，批量完成AI批改
          </p>
        </div>
      </div>

      {error && (
        <div className='rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300'>
          {error}
        </div>
      )}

      {/* ===== Phase: upload ===== */}
      {phase === 'upload' && (
        <>
          {/* 多文件上传区 */}
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <Upload className='h-5 w-5' />
                上传作业图片
              </CardTitle>
              <CardDescription>
                支持 JPG/PNG 格式，可拖拽或点击上传，最多 {MAX_FILES} 张
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              {/* 拖拽区域 */}
              <div
                className='flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/25 p-8 transition-colors hover:border-primary/50'
                onClick={() => fileInputRef.current?.click()}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
              >
                <Upload className='mb-2 h-10 w-10 text-muted-foreground' />
                <p className='text-sm text-muted-foreground'>
                  拖拽图片到此处，或点击选择文件
                </p>
                <input
                  ref={fileInputRef}
                  type='file'
                  accept='image/*'
                  multiple
                  className='hidden'
                  onChange={(e) => handleFilesSelected(e.target.files)}
                />
              </div>

              {/* 缩略图网格 */}
              {files.length > 0 && (
                <div className='space-y-2'>
                  <div className='text-sm text-muted-foreground'>
                    已选择 {files.length} 张图片
                  </div>
                  <div className='grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6'>
                    {files.map((f) => (
                      <div key={f.id} className='group relative'>
                        <img
                          src={f.preview}
                          alt={f.file.name}
                          className='aspect-square w-full rounded-md object-cover'
                        />
                        <button
                          className='absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity group-hover:opacity-100'
                          onClick={() => removeFile(f.id)}
                        >
                          <X className='h-3 w-3' />
                        </button>
                        <div className='absolute bottom-0 left-0 right-0 truncate rounded-b-md bg-black/50 px-1 py-0.5 text-center text-[10px] text-white'>
                          {f.studentId}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 通用参数表单 */}
          <Card>
            <CardHeader>
              <CardTitle>批改参数</CardTitle>
              <CardDescription>
                设置通用参数，将应用到所有上传的图片
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <div className='grid grid-cols-1 gap-3 md:grid-cols-2'>
                <div>
                  <Label>学科</Label>
                  <Select
                    value={commonParams.subject}
                    onValueChange={(v) =>
                      setCommonParams((p) => ({ ...p, subject: v }))
                    }
                  >
                    <SelectTrigger className='w-full'>
                      <SelectValue />
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
                  <Label>满分</Label>
                  <Input
                    type='number'
                    value={commonParams.totalScore}
                    onChange={(e) =>
                      setCommonParams((p) => ({
                        ...p,
                        totalScore: Number(e.target.value),
                      }))
                    }
                    placeholder='5'
                  />
                </div>
              </div>
              <div>
                <Label>题目内容</Label>
                <Textarea
                  value={commonParams.question}
                  onChange={(e) =>
                    setCommonParams((p) => ({ ...p, question: e.target.value }))
                  }
                  placeholder='如：解方程 2x+3=7'
                  rows={2}
                />
              </div>
              <div>
                <Label>
                  标准答案{' '}
                  <span className='text-muted-foreground text-xs'>
                    （可选，留空时AI自动解题）
                  </span>
                </Label>
                <Input
                  value={commonParams.standardAnswer}
                  onChange={(e) =>
                    setCommonParams((p) => ({
                      ...p,
                      standardAnswer: e.target.value,
                    }))
                  }
                  placeholder={
                    commonParams.subject === 'chinese'
                      ? '作文主题/评分要点（可选）'
                      : '如：x=2，留空则AI自动解题'
                  }
                />
              </div>
            </CardContent>
          </Card>

          {/* 操作按钮 */}
          <div className='flex justify-end gap-2'>
            <Button variant='outline' onClick={handleReset}>
              重置
            </Button>
            <Button onClick={handleSubmit} disabled={files.length === 0}>
              <Layers className='mr-2 h-4 w-4' />
              开始批量批改（{files.length}张）
            </Button>
          </div>
        </>
      )}

      {/* ===== Phase: submitting ===== */}
      {phase === 'submitting' && (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-16'>
            <Loader2 className='mb-4 h-10 w-10 animate-spin text-primary' />
            <p className='text-lg font-medium'>正在提交批量任务...</p>
          </CardContent>
        </Card>
      )}

      {/* ===== Phase: processing ===== */}
      {phase === 'processing' && batchStatus && (
        <Card>
          <CardHeader>
            <CardTitle className='flex items-center gap-2'>
              <Loader2 className='h-5 w-5 animate-spin text-primary' />
              批量批改进行中
            </CardTitle>
            <CardDescription>
              任务ID: {batchId} · 创建时间:{' '}
              {batchStatus.created_at
                ? new Date(batchStatus.created_at).toLocaleString('zh-CN')
                : '-'}
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-6'>
            {/* 进度条 */}
            <div className='space-y-2'>
              <Progress value={batchStatus.progress_pct} className='h-3' />
              <div className='text-muted-foreground flex justify-between text-sm'>
                <span>
                  已完成 {batchStatus.completed + batchStatus.failed} /{' '}
                  {batchStatus.total} ({batchStatus.progress_pct}%)
                </span>
                <span>
                  成功 {batchStatus.completed} · 失败 {batchStatus.failed} ·
                  待处理 {batchStatus.pending}
                </span>
              </div>
            </div>

            {/* 统计卡片 */}
            <div className='grid grid-cols-4 gap-4'>
              <Card>
                <CardContent className='pt-4 text-center'>
                  <div className='text-2xl font-bold text-primary'>
                    {batchStatus.completed}
                  </div>
                  <div className='text-muted-foreground text-xs'>已完成</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className='pt-4 text-center'>
                  <div className='text-2xl font-bold text-red-500'>
                    {batchStatus.failed}
                  </div>
                  <div className='text-muted-foreground text-xs'>失败</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className='pt-4 text-center'>
                  <div className='text-muted-foreground text-2xl font-bold'>
                    {batchStatus.pending}
                  </div>
                  <div className='text-muted-foreground text-xs'>待处理</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className='pt-4 text-center'>
                  <div className='text-2xl font-bold'>
                    {batchStatus.progress_pct}%
                  </div>
                  <div className='text-muted-foreground text-xs'>进度</div>
                </CardContent>
              </Card>
            </div>

            {/* 当前任务指示器 */}
            {batchStatus.current_task && (
              <div className='rounded-md bg-blue-50 p-3 text-sm dark:bg-blue-900/20'>
                <span className='text-blue-700 dark:text-blue-300'>
                  正在处理：学生 {batchStatus.current_task.student_id}（优先级:{' '}
                  {batchStatus.current_task.priority.toFixed(2)}）
                </span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ===== Phase: results ===== */}
      {phase === 'results' && (
        <>
          {/* 统计摘要卡片 */}
          <div className='grid grid-cols-4 gap-4'>
            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>总任务数</CardTitle>
                <Layers className='h-4 w-4 text-muted-foreground' />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>{results.length}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>成功</CardTitle>
                <CheckCircle className='h-4 w-4 text-green-500' />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold text-green-600'>
                  {completedCount}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>失败</CardTitle>
                <XCircle className='h-4 w-4 text-red-500' />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold text-red-600'>
                  {failedCount}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>平均得分</CardTitle>
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>{avgScore}</div>
              </CardContent>
            </Card>
          </div>

          {/* 结果表格 */}
          <Card>
            <CardHeader>
              <CardTitle>批改结果</CardTitle>
              <CardDescription>
                共 {results.length} 项 · 点击行查看详情
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className='overflow-hidden rounded-md border'>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className='w-12'>#</TableHead>
                      <TableHead>学生ID</TableHead>
                      <TableHead>得分</TableHead>
                      <TableHead>满分</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>置信度</TableHead>
                      <TableHead>标记</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {results.map((r, idx) => (
                      <TableRow
                        key={r.task_id}
                        className='cursor-pointer hover:bg-muted/50'
                        onClick={() => setSelectedResult(r)}
                      >
                        <TableCell className='text-muted-foreground'>
                          {idx + 1}
                        </TableCell>
                        <TableCell className='font-medium'>
                          {r.student_id}
                        </TableCell>
                        <TableCell>
                          {r.status === 'completed' ? (
                            <span
                              className={
                                (r.suggested_score || 0) /
                                  (r.max_score || commonParams.totalScore) >=
                                0.6
                                  ? 'text-green-600'
                                  : 'text-red-600'
                              }
                            >
                              {r.suggested_score ?? '-'}
                            </span>
                          ) : (
                            <span className='text-muted-foreground'>-</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {r.max_score ?? commonParams.totalScore}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              r.status === 'completed' ? 'default' : 'destructive'
                            }
                          >
                            {r.status === 'completed' ? '完成' : '失败'}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {r.status === 'completed' && r.confidence != null ? (
                            <Badge
                              variant={r.confidence > 0.7 ? 'default' : 'outline'}
                            >
                              {(r.confidence * 100).toFixed(0)}%
                            </Badge>
                          ) : (
                            '-'
                          )}
                        </TableCell>
                        <TableCell>
                          {r.flagged ? (
                            <AlertTriangle className='h-4 w-4 text-yellow-500' />
                          ) : (
                            <span className='text-muted-foreground'>-</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* 操作按钮 */}
          <div className='flex justify-end gap-2'>
            <Button variant='outline' onClick={handleReset}>
              <ArrowLeft className='mr-2 h-4 w-4' />
              返回批量上传
            </Button>
            <Button
              variant='outline'
              onClick={() => {
                if (batchId) {
                  void executeBatch(batchId)
                }
              }}
            >
              <RefreshCw className='mr-2 h-4 w-4' />
              重新批改失败项
            </Button>
          </div>

          {/* 详情弹窗 */}
          <Dialog
            open={selectedResult !== null}
            onOpenChange={(open) => !open && setSelectedResult(null)}
          >
            <DialogContent className='max-h-[80vh] max-w-2xl overflow-y-auto'>
              <DialogHeader>
                <DialogTitle>
                  批改详情 — {selectedResult?.student_id}
                </DialogTitle>
                <DialogDescription>
                  任务ID: {selectedResult?.task_id}
                </DialogDescription>
              </DialogHeader>
              {selectedResult && (
                <ResultDetailContent result={selectedResult} />
              )}
              <DialogFooter>
                <Button
                  variant='outline'
                  onClick={() => setSelectedResult(null)}
                >
                  关闭
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </>
      )}
    </div>
  )
}

// ===== 结果详情内容组件 =====
function ResultDetailContent({ result }: { result: BatchResultItem }) {
  if (result.status === 'failed') {
    return (
      <div className='space-y-4'>
        <div className='rounded-md bg-red-50 p-4 dark:bg-red-900/20'>
          <h3 className='font-semibold text-red-700 dark:text-red-300'>
            批改失败
          </h3>
          <p className='mt-1 text-sm text-red-600 dark:text-red-400'>
            {result.error || '未知错误'}
          </p>
        </div>
        <div className='text-muted-foreground text-sm'>
          学生: {result.student_id} · 作业: {result.homework_id}
        </div>
      </div>
    )
  }

  const score = result.suggested_score ?? 0
  const maxScore = result.max_score ?? 0
  const pct = maxScore > 0 ? Math.round((score / maxScore) * 100) : 0

  return (
    <div className='space-y-4'>
      {/* 评分总览 */}
      <div className='flex items-center gap-6'>
        <div className='text-center'>
          <div
            className={`text-4xl font-bold ${pct >= 60 ? 'text-green-600' : 'text-red-600'}`}
          >
            {score}
          </div>
          <div className='text-muted-foreground text-sm'>/ {maxScore} 分</div>
        </div>
        <div className='flex-1'>
          <Progress value={pct} className='h-3' />
          <div className='text-muted-foreground mt-1 text-sm'>
            得分率 {pct}%
          </div>
        </div>
        {result.flagged && (
          <Badge variant='destructive' className='flex items-center gap-1'>
            <AlertTriangle className='h-3 w-3' />
            需关注
          </Badge>
        )}
      </div>

      {/* OCR 识别文本 */}
      {result.ocr_result && (
        <div>
          <h4 className='mb-1 text-sm font-medium'>OCR识别文本</h4>
          <div className='rounded-md bg-muted p-3 text-sm'>
            {result.ocr_result.text}
          </div>
          <div className='text-muted-foreground mt-1 text-xs'>
            置信度: {(result.ocr_result.confidence * 100).toFixed(0)}% · 引擎:{' '}
            {result.ocr_result.engines_used.join(', ')}
          </div>
        </div>
      )}

      {/* 知识点 */}
      {result.grading?.knowledge_points &&
        result.grading.knowledge_points.length > 0 && (
          <div>
            <h4 className='mb-1 text-sm font-medium'>知识点</h4>
            <div className='flex flex-wrap gap-1'>
              {result.grading.knowledge_points.map((kp, i) => (
                <Badge key={i} variant='outline'>
                  {kp}
                </Badge>
              ))}
            </div>
          </div>
        )}

      {/* AI 评语 */}
      {result.comment && (
        <div>
          <h4 className='mb-1 text-sm font-medium'>AI评语</h4>
          <p className='text-sm'>{result.comment}</p>
        </div>
      )}

      {/* 步骤评分 */}
      {result.grading?.steps && result.grading.steps.length > 0 && (
        <div>
          <h4 className='mb-1 text-sm font-medium'>步骤评分</h4>
          <div className='space-y-2'>
            {result.grading.steps.map((step) => (
              <div
                key={step.step_id}
                className={`rounded-md border p-2 text-sm ${
                  step.correct
                    ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20'
                    : 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20'
                }`}
              >
                <div className='flex items-center justify-between'>
                  <span>
                    {step.correct ? (
                      <CheckCircle className='mr-1 inline h-3 w-3 text-green-500' />
                    ) : (
                      <XCircle className='mr-1 inline h-3 w-3 text-red-500' />
                    )}
                    {step.content}
                  </span>
                  <span className='font-medium'>
                    {step.score}分
                  </span>
                </div>
                {step.error_reason && (
                  <div className='text-muted-foreground mt-1 text-xs'>
                    原因: {step.error_reason}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 错误类型 */}
      {result.grading?.error_type && (
        <div>
          <h4 className='mb-1 text-sm font-medium'>错误类型</h4>
          <Badge variant='destructive'>{result.grading.error_type}</Badge>
        </div>
      )}
    </div>
  )
}
