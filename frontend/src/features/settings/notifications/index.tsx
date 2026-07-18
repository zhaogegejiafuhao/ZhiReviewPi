import { ContentSection } from '../components/content-section'
import { NotificationsForm } from './notifications-form'

export function SettingsNotifications() {
  return (
    <ContentSection
      title='消息通知'
      desc='配置您接收通知的方式。'
    >
      <NotificationsForm />
    </ContentSection>
  )
}
