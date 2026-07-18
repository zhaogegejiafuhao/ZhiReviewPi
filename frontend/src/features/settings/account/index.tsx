import { ContentSection } from '../components/content-section'
import { AccountForm } from './account-form'

export function SettingsAccount() {
  return (
    <ContentSection
      title='账号信息'
      desc='更新您的账号设置，设置首选语言和时区。'
    >
      <AccountForm />
    </ContentSection>
  )
}
