// === TASK:WP-504:START ===
export type EmergencyOutcome = 'emergency_triggered' | 'clarification_required' | 'not_triggered' | (string & {})

export interface SuggestedActionDTO {
  action_id: string
  label: string
  type: string
  payload?: Record<string, unknown>
}

export interface EmergencyProtocolContentDTO {
  title?: string
  instructions: string[]
  disclaimer?: string
}

export interface EmergencyContactDTO {
  label: string
  value: string
  type: 'hotline' | 'address' | 'url' | string
  configured_from: 'mock' | 'local_config' | string
}

export interface EmergencySafetyResponse {
  outcome: EmergencyOutcome
  level?: 1 | 2 | string
  path?: string
  protocol_content?: EmergencyProtocolContentDTO
  hotline?: string
  address?: string
  banner?: string
  event_id?: string
  suggested_actions?: SuggestedActionDTO[]
  contacts?: EmergencyContactDTO[]
}

export interface EmergencyBannerProps {
  response: EmergencySafetyResponse
}

function isMockConfigured(value?: string): boolean {
  return value?.toLowerCase() === 'mock'
}

function formatLevel(level?: EmergencySafetyResponse['level']): string {
  return level ? `Level ${level}` : 'Emergency safety'
}

export function EmergencyBanner({ response }: EmergencyBannerProps) {
  if (response.outcome === 'not_triggered') {
    return null
  }

  const contacts = response.contacts ?? [
    ...(response.hotline
      ? [{ label: 'Hotline', value: response.hotline, type: 'hotline', configured_from: 'mock' as const }]
      : []),
    ...(response.address
      ? [{ label: 'Địa chỉ', value: response.address, type: 'address', configured_from: 'mock' as const }]
      : []),
  ]

  const isLevelOne = response.level === 1 || response.level === '1'
  const title = response.banner ?? response.protocol_content?.title ?? 'Cảnh báo an toàn khẩn cấp'

  return (
    <aside aria-label="Emergency safety banner" aria-live="assertive" role="alert">
      <header>
        <strong>{formatLevel(response.level)}</strong>
        <h2>{title}</h2>
      </header>

      {response.outcome === 'clarification_required' ? (
        <p>Vui lòng cung cấp thêm thông tin để xác định hướng dẫn an toàn phù hợp.</p>
      ) : null}

      {response.protocol_content ? (
        <section aria-label="Emergency protocol">
          <h3>Hướng dẫn an toàn</h3>
          <ol>
            {response.protocol_content.instructions.map((instruction) => (
              <li key={instruction}>{instruction}</li>
            ))}
          </ol>
          {response.protocol_content.disclaimer ? <p>{response.protocol_content.disclaimer}</p> : null}
        </section>
      ) : null}

      {contacts.length > 0 ? (
        <section aria-label="Emergency contacts">
          <h3>Liên hệ khẩn cấp</h3>
          <ul>
            {contacts.map((contact) => (
              <li key={`${contact.type}-${contact.value}`}>
                {contact.type === 'hotline' ? <a href={`tel:${contact.value}`}>{contact.label}: {contact.value}</a> : null}
                {contact.type === 'url' ? <a href={contact.value}>{contact.label}</a> : null}
                {contact.type !== 'hotline' && contact.type !== 'url' ? <span>{contact.label}: {contact.value}</span> : null}
                {isMockConfigured(contact.configured_from) ? (
                  <small> Cảnh báo cấu hình: giá trị mock, cần cấu hình chính thức.</small>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {isLevelOne && response.suggested_actions && response.suggested_actions.length > 0 ? (
        <section aria-label="Level-1 contact handoff">
          <h3>Chuyển tiếp liên hệ Level-1</h3>
          <ul>
            {response.suggested_actions.map((action) => (
              <li key={action.action_id}>
                <button type="button">{action.label}</button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {response.event_id ? <p>Mã sự kiện: {response.event_id}</p> : null}
      <p>Đây không phải là chẩn đoán y khoa. Nếu nguy hiểm hiện hữu, hãy gọi cấp cứu hoặc đến cơ sở y tế gần nhất.</p>
    </aside>
  )
}
// === TASK:WP-504:END ===
