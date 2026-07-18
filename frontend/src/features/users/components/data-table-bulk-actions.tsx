import { useState } from 'react'
import { type Table } from '@tanstack/react-table'
import { Trash2, UserX, UserCheck, Mail } from 'lucide-react'
import { toast } from 'sonner'
import { sleep } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { DataTableBulkActions as BulkActionsToolbar } from '@/components/data-table'
import { type User } from '../data/schema'
import { UsersMultiDeleteDialog } from './users-multi-delete-dialog'

type DataTableBulkActionsProps<TData> = {
  table: Table<TData>
}

export function DataTableBulkActions<TData>({
  table,
}: DataTableBulkActionsProps<TData>) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const selectedRows = table.getFilteredSelectedRowModel().rows

  const handleBulkStatusChange = (status: '活跃' | '休眠') => {
    const selectedUsers = selectedRows.map((row) => row.original as User)
    toast.promise(sleep(2000), {
      loading: `${status === '活跃' ? '正在激活' : '正在休眠'}学生...`,
      success: () => {
        table.resetRowSelection()
        return `${status === '活跃' ? '已激活' : '已休眠'} ${selectedUsers.length} 名学生`
      },
      error: `${status === '活跃' ? '激活' : '休眠'}学生时出错`,
    })
    table.resetRowSelection()
  }

  const handleBulkInvite = () => {
    const selectedUsers = selectedRows.map((row) => row.original as User)
    toast.promise(sleep(2000), {
      loading: '正在邀请学生...',
      success: () => {
        table.resetRowSelection()
        return `已邀请 ${selectedUsers.length} 名学生`
      },
      error: '邀请学生时出错',
    })
    table.resetRowSelection()
  }

  return (
    <>
      <BulkActionsToolbar table={table} entityName='学生'>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant='outline'
              size='icon'
              onClick={handleBulkInvite}
              className='size-8'
              aria-label='邀请所选学生'
              title='邀请所选学生'
            >
              <Mail />
              <span className='sr-only'>邀请所选学生</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>邀请所选学生</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant='outline'
              size='icon'
              onClick={() => handleBulkStatusChange('活跃')}
              className='size-8'
              aria-label='激活所选学生'
              title='激活所选学生'
            >
              <UserCheck />
              <span className='sr-only'>激活所选学生</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>激活所选学生</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant='outline'
              size='icon'
              onClick={() => handleBulkStatusChange('休眠')}
              className='size-8'
              aria-label='休眠所选学生'
              title='休眠所选学生'
            >
              <UserX />
              <span className='sr-only'>休眠所选学生</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>休眠所选学生</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant='destructive'
              size='icon'
              onClick={() => setShowDeleteConfirm(true)}
              className='size-8'
              aria-label='删除所选学生'
              title='删除所选学生'
            >
              <Trash2 />
              <span className='sr-only'>删除所选学生</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>删除所选学生</p>
          </TooltipContent>
        </Tooltip>
      </BulkActionsToolbar>

      <UsersMultiDeleteDialog
        table={table}
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
      />
    </>
  )
}
