import { Component, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className='flex min-h-[200px] flex-col items-center justify-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-6'>
          <AlertTriangle className='h-8 w-8 text-destructive' />
          <div className='text-center'>
            <h3 className='text-lg font-semibold'>页面加载出错</h3>
            <p className='mt-1 text-sm text-muted-foreground'>
              {this.state.error?.message || '发生了未知错误'}
            </p>
          </div>
          <Button variant='outline' size='sm' onClick={this.handleReset}>
            <RefreshCw className='mr-1 h-3 w-3' />
            重新加载
          </Button>
        </div>
      )
    }

    return this.props.children
  }
}
