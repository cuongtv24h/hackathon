// === TASK:WP-502:START ===
export type InformationOutcome =
  | 'answered'
  | 'clarification_required'
  | 'fallback'
  | 'refused'
  | 'emergency_rerouted'
  | (string & {})

export interface CitationDTO {
  source_id: string
  title: string
  source_type?: string
  url?: string
  excerpt?: string
  version?: string
  effective_date?: string
}

export interface SuggestedActionDTO {
  action_id: string
  label: string
  type: string
  payload?: Record<string, unknown>
}

export interface ExplainabilityDTO {
  grounded: boolean
  confidence?: 'low' | 'medium' | 'high' | string
  rationale?: string
  source_count?: number
}

export interface InformationAssistanceResponse {
  outcome: InformationOutcome
  message: string
  citations: CitationDTO[]
  suggested_actions: SuggestedActionDTO[]
  conversation_state?: Record<string, unknown>
  explainability?: ExplainabilityDTO
}

export interface InformationResponseProps {
  response: InformationAssistanceResponse
}

const uncertainOutcomes: InformationOutcome[] = ['clarification_required', 'fallback', 'refused', 'emergency_rerouted']

function outcomeLabel(outcome: InformationOutcome): string {
  switch (outcome) {
    case 'answered':
      return 'Đã trả lời dựa trên nguồn chính thức'
    case 'clarification_required':
      return 'Cần thêm thông tin để trả lời chính xác'
    case 'fallback':
      return 'Chưa đủ căn cứ để trả lời chắc chắn'
    case 'refused':
      return 'Không thể trả lời nội dung này'
    case 'emergency_rerouted':
      return 'Đã chuyển sang hướng dẫn an toàn khẩn cấp'
    default:
      return `Trạng thái: ${outcome}`
  }
}

function isUncertain(outcome: InformationOutcome): boolean {
  return uncertainOutcomes.includes(outcome)
}

export function InformationResponse({ response }: InformationResponseProps) {
  const showUncertainNotice = isUncertain(response.outcome)
  const sourceCount = response.explainability?.source_count ?? response.citations.length

  return (
    <article aria-label="Information assistance response">
      <header>
        <p aria-label="Response outcome">{outcomeLabel(response.outcome)}</p>
        {showUncertainNotice ? (
          <p role="alert">
            Nội dung này không được hiển thị như câu trả lời chắc chắn. Vui lòng xem hướng dẫn tiếp theo hoặc cung cấp
            thêm thông tin.
          </p>
        ) : null}
      </header>

      <p>{response.message}</p>

      {response.explainability ? (
        <section aria-label="Explainability">
          <h3>Độ tin cậy</h3>
          <p>{response.explainability.grounded ? 'Có căn cứ từ nguồn chính thức' : 'Chưa đủ căn cứ từ nguồn chính thức'}</p>
          <p>Số nguồn: {sourceCount}</p>
          {response.explainability.confidence ? <p>Mức tin cậy: {response.explainability.confidence}</p> : null}
        </section>
      ) : null}

      <section aria-label="Citations">
        <h3>Nguồn tham khảo</h3>
        {response.citations.length > 0 ? (
          <ul>
            {response.citations.map((citation) => (
              <li key={citation.source_id}>
                {citation.url ? (
                  <a href={citation.url} target="_blank" rel="noreferrer">
                    {citation.title}
                  </a>
                ) : (
                  <span>{citation.title}</span>
                )}
                {citation.effective_date ? <span> — hiệu lực {citation.effective_date}</span> : null}
                {citation.excerpt ? <blockquote>{citation.excerpt}</blockquote> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p>Không có nguồn chính thức được đính kèm.</p>
        )}
      </section>

      {response.suggested_actions.length > 0 ? (
        <section aria-label="Suggested actions">
          <h3>Hành động tiếp theo</h3>
          <ul>
            {response.suggested_actions.map((action) => (
              <li key={action.action_id}>
                <button type="button">{action.label}</button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  )
}
// === TASK:WP-502:END ===
