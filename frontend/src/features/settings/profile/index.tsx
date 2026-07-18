import { ContentSection } from '../components/content-section'
import { ProfileForm } from './profile-form'

export function SettingsProfile() {
  return (
    <ContentSection
      title='个人信息'
      desc='这是其他人在网站上看到您的信息。'
    >
      <ProfileForm />
    </ContentSection>
  )
}
