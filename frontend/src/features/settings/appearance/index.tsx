import { ContentSection } from '../components/content-section'
import { AppearanceForm } from './appearance-form'

export function SettingsAppearance() {
  return (
    <ContentSection
      title='外观设置'
      desc='自定义应用外观，自动切换日间和夜间主题。'
    >
      <AppearanceForm />
    </ContentSection>
  )
}
