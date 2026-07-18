import { useState, useEffect, useCallback, Fragment } from 'react'
import {
  Database,
  Search,
  Trash2,
  Edit3,
  CheckCircle,
  XCircle,
  RefreshCw,
  Loader2,
  BookOpen,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  getQuestionBankStats,
  getQuestionBankList,
  deleteQuestionBankEntry,
  correctQuestionBankAnswer,
} from '@/lib/api'

// 来源显示映射
const SOURCE_LABELS: Record<string, string> = {
  user_provided: '用户提供',
  ai_generated: 'AI解题',
  ai_expanded: 'AI补充',
  user_corrected: '用户修正',
  ai_corrected: 'AI修正',
}

const SOURCE_VARIANTS: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  user_provided: 'default',
  ai_generated: 'outline',
  ai_expanded: 'secondary',
  user_corrected: 'default',
  ai_corrected: 'outline',
}

const SUBJECT_LABELS: Record<string, string> = {
  math: '数学',
  chinese: '语文',
  english: '英语',
  physics: '物理',
}

interface QuestionBankEntry {
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
}

export function QuestionBankPage() {
  // 统计数据
  const [stats, setStats] = useState<{
    total: number
    valid: number
    invalid: number
    by_source: Record<string, number>
  } | null>(null)
  const [statsLoading, setStatsLoading] = useState(true)

  // 列表数据
  const [entries, setEntries] = useState<QuestionBankEntry[]>([])
  const [entriesLoading, setEntriesLoading] = useState(true)

  // 过滤参数
  const [statusFilter, setStatusFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [searchText, setSearchText] = useState('')

  // 纠错状态
  const [correctingHash, setCorrectingHash] = useState<string | null>(null)
  const [correctedAnswer, setCorrectedAnswer] = useState('')
  const [correctingLoading, setCorrectingLoading] = useState(false)

  // 删除状态
  const [deletingHash, setDeletingHash] = useState<string | null>(null)

  const loadStats = useCallback(async () => {
    setStatsLoading(true)
    try {
      const data = await getQuestionBankStats()
      setStats(data)
    } catch {
      setStats({ total: 0, valid: 0, invalid: 0, by_source: {} })
    } finally {
      setStatsLoading(false)
    }
  }, [])

  const loadEntries = useCallback(async () => {
    setEntriesLoading(true)
    try {
      const data = await getQuestionBankList({
        status_filter: statusFilter,
        source_filter: sourceFilter,
        search: searchText,
      })
      setEntries(data.entries || [])
    } catch {
      setEntries([])
    } finally {
      setEntriesLoading(false)
    }
  }, [statusFilter, sourceFilter, searchText])

  useEffect(() => {
    loadStats()
    loadEntries()
  }, [loadStats, loadEntries])

  const handleDelete = async (hash: string) => {
    if (!window.confirm('确认删除此题库条目？此操作不可恢复。')) return
    setDeletingHash(hash)
    try {
      await deleteQuestionBankEntry(hash)
      await loadEntries()
      await loadStats()
    } catch {
      alert('删除失败')
    } finally {
      setDeletingHash(null)
    }
  }

  const handleCorrect = async (hash: string) => {
    if (!correctedAnswer.trim()) return
    setCorrectingLoading(true)
    try {
      await correctQuestionBankAnswer(hash, { new_answer: correctedAnswer })
      setCorrectingHash(null)
      setCorrectedAnswer('')
      await loadEntries()
      await loadStats()
    } catch {
      alert('纠错失败')
    } finally {
      setCorrectingLoading(false)
    }
  }

  const handleRequestNewSolve = async (hash: string) => {
    setCorrectingLoading(true)
    try {
      await correctQuestionBankAnswer(hash, { request_new_solve: true })
      setCorrectingHash(null)
      setCorrectedAnswer('')
      await loadEntries()
      await loadStats()
    } catch {
      alert('请求AI重新解题失败')
    } finally {
      setCorrectingLoading(false)
    }
  }

  // 来源分布文本
  const sourceDistributionText = stats?.by_source
    ? Object.entries(stats.by_source)
        .map(([k, v]) => `${SOURCE_LABELS[k] || k}: ${v}`)
        .join('、')
    : '-'

  return (
    <div className='space-y-6'>
      <div className='flex items-center justify-between'>
        <h1 className='text-2xl font-bold tracking-tight'>题库管理</h1>
      </div>

      {/* ===== 统计卡片 ===== */}
      <div className='grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4'>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
            <CardTitle className='text-sm font-medium'>总条目</CardTitle>
            <Database className='h-4 w-4 text-muted-foreground' />
          </CardHeader>
          <CardContent>
            <div className='text-2xl font-bold'>
              {statsLoading ? (
                <div className='h-7 w-12 animate-pulse rounded bg-muted' />
              ) : (
                stats?.total ?? 0
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
            <CardTitle className='text-sm font-medium'>有效条目</CardTitle>
            <CheckCircle className='h-4 w-4 text-green-500' />
          </CardHeader>
          <CardContent>
            <div className='text-2xl font-bold text-green-600'>
              {statsLoading ? (
                <div className='h-7 w-12 animate-pulse rounded bg-muted' />
              ) : (
                stats?.valid ?? 0
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
            <CardTitle className='text-sm font-medium'>无效条目</CardTitle>
            <XCircle className='h-4 w-4 text-red-500' />
          </CardHeader>
          <CardContent>
            <div className='text-2xl font-bold text-red-600'>
              {statsLoading ? (
                <div className='h-7 w-12 animate-pulse rounded bg-muted' />
              ) : (
                stats?.invalid ?? 0
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
            <CardTitle className='text-sm font-medium'>来源分布</CardTitle>
            <BookOpen className='h-4 w-4 text-muted-foreground' />
          </CardHeader>
          <CardContent>
            <div className='text-sm'>
              {statsLoading ? (
                <div className='h-7 w-40 animate-pulse rounded bg-muted' />
              ) : (
                sourceDistributionText
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ===== 搜索 + 过滤 ===== */}
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-2'>
            <Search className='h-5 w-5' />
            搜索与过滤
          </CardTitle>
          <CardDescription>按题目内容搜索，或按状态/来源过滤</CardDescription>
        </CardHeader>
        <CardContent>
          <div className='flex flex-wrap items-end gap-3'>
            <div className='flex-1 min-w-[200px]'>
              <Label>搜索题目</Label>
              <Input
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder='输入关键词搜索...'
              />
            </div>
            <div className='w-40'>
              <Label>状态</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='all'>全部</SelectItem>
                  <SelectItem value='valid'>有效</SelectItem>
                  <SelectItem value='invalid'>无效</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='w-40'>
              <Label>来源</Label>
              <Select value={sourceFilter} onValueChange={setSourceFilter}>
                <SelectTrigger className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='all'>全部</SelectItem>
                  <SelectItem value='user_provided'>用户提供</SelectItem>
                  <SelectItem value='ai_generated'>AI解题</SelectItem>
                  <SelectItem value='ai_expanded'>AI补充</SelectItem>
                  <SelectItem value='user_corrected'>用户修正</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ===== 题库条目列表 ===== */}
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-2'>
            <BookOpen className='h-5 w-5' />
            题库条目
          </CardTitle>
          <CardDescription>
            共 {entries.length} 条记录
          </CardDescription>
        </CardHeader>
        <CardContent>
          {entriesLoading ? (
            <div className='space-y-3'>
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className='h-16 animate-pulse rounded-md bg-muted' />
              ))}
            </div>
          ) : entries.length === 0 ? (
            <div className='flex h-32 flex-col items-center justify-center gap-2 text-muted-foreground'>
              <Database className='h-8 w-8 opacity-40' />
              <p className='font-medium'>暂无题库数据</p>
              <p className='text-xs'>批改作业时，题目和答案会自动存入题库</p>
            </div>
          ) : (
            <div className='overflow-hidden rounded-md border'>
              <table className='w-full text-sm'>
                <thead className='border-b bg-muted/50'>
                  <tr>
                    <th className='px-3 py-2 text-start font-medium'>题目</th>
                    <th className='px-3 py-2 text-start font-medium'>答案摘要</th>
                    <th className='px-3 py-2 text-start font-medium'>来源</th>
                    <th className='px-3 py-2 text-start font-medium'>状态</th>
                    <th className='px-3 py-2 text-start font-medium'>学科</th>
                    <th className='px-3 py-2 text-start font-medium'>满分</th>
                    <th className='px-3 py-2 text-start font-medium'>更新时间</th>
                    <th className='px-3 py-2 text-start font-medium'>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <Fragment key={entry.question_hash}>
                      <tr className='border-b last:border-0 hover:bg-muted/30'>
                        <td className='max-w-[200px] truncate px-3 py-2' title={entry.question}>
                          {entry.question}
                        </td>
                        <td className='max-w-[150px] truncate px-3 py-2' title={entry.standard_answer}>
                          {entry.standard_answer}
                        </td>
                        <td className='px-3 py-2'>
                          <Badge variant={SOURCE_VARIANTS[entry.source] || 'outline'}>
                            {SOURCE_LABELS[entry.source] || entry.source}
                          </Badge>
                        </td>
                        <td className='px-3 py-2'>
                          <Badge variant={entry.status === 'valid' ? 'default' : 'destructive'}>
                            {entry.status === 'valid' ? '有效' : '无效'}
                          </Badge>
                        </td>
                        <td className='px-3 py-2'>
                          {SUBJECT_LABELS[entry.subject] || entry.subject}
                        </td>
                        <td className='px-3 py-2'>{entry.total_score}</td>
                        <td className='px-3 py-2 text-xs text-muted-foreground'>
                          {entry.updated_at ? new Date(entry.updated_at).toLocaleString('zh-CN') : '-'}
                        </td>
                        <td className='px-3 py-2'>
                          <div className='flex gap-1'>
                            <Button
                              variant='ghost'
                              size='sm'
                              onClick={() => {
                                setCorrectingHash(
                                  correctingHash === entry.question_hash ? null : entry.question_hash
                                )
                                setCorrectedAnswer('')
                              }}
                              title='纠错'
                            >
                              <Edit3 className='h-4 w-4' />
                            </Button>
                            <Button
                              variant='ghost'
                              size='sm'
                              onClick={() => handleDelete(entry.question_hash)}
                              disabled={deletingHash === entry.question_hash}
                              title='删除'
                            >
                              {deletingHash === entry.question_hash ? (
                                <Loader2 className='h-4 w-4 animate-spin' />
                              ) : (
                                <Trash2 className='h-4 w-4 text-red-500' />
                              )}
                            </Button>
                          </div>
                        </td>
                      </tr>
                      {/* 纠错操作面板 */}
                      {correctingHash === entry.question_hash && (
                        <tr key={`${entry.question_hash}-correct`} className='border-b bg-muted/20'>
                          <td colSpan={8} className='px-3 py-3'>
                            <div className='space-y-2'>
                              <Label className='text-xs'>修正答案</Label>
                              <div className='flex gap-2'>
                                <Input
                                  value={correctedAnswer}
                                  onChange={(e) => setCorrectedAnswer(e.target.value)}
                                  placeholder='输入正确的答案...'
                                  className='flex-1'
                                />
                                <Button
                                  size='sm'
                                  onClick={() => handleCorrect(entry.question_hash)}
                                  disabled={correctingLoading || !correctedAnswer.trim()}
                                >
                                  {correctingLoading ? (
                                    <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                                  ) : (
                                    <CheckCircle className='mr-1 h-3 w-3' />
                                  )}
                                  提交修正
                                </Button>
                                <Button
                                  variant='outline'
                                  size='sm'
                                  onClick={() => handleRequestNewSolve(entry.question_hash)}
                                  disabled={correctingLoading}
                                >
                                  {correctingLoading ? (
                                    <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                                  ) : (
                                    <RefreshCw className='mr-1 h-3 w-3' />
                                  )}
                                  AI重新解题
                                </Button>
                                <Button
                                  variant='ghost'
                                  size='sm'
                                  onClick={() => {
                                    setCorrectingHash(null)
                                    setCorrectedAnswer('')
                                  }}
                                >
                                  取消
                                </Button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
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
