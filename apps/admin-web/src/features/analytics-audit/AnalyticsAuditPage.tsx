// === TASK:WP-506:START ===
import { useMemo, useState } from 'react'

export interface PageMetadataDTO {
  page: number
  page_size: number
  total_items: number
  total_pages: number
}

export interface AnalyticsSummaryDTO {
  total_conversations: number
  emergency_events: number
  unresolved_conflicts: number
  average_response_ms: number
  top_intents: Array<{ intent: string; count: number }>
  channels: Array<{ channel: string; count: number }>
  pii_redaction_failures: number
  generated_at: string
}

export interface ConversationHistoryRecordDTO {
  message_id: string
  session_id: string
  channel: 'web_widget' | 'web_page' | 'admin_preview'
  role: 'user' | 'assistant' | 'system'
  content_preview: string
  intent: string
  tools_called: string[]
  emergency_triggered: boolean
  created_at: string
}

export interface ConversationHistoryPageDTO {
  items: ConversationHistoryRecordDTO[]
  page: PageMetadataDTO
}

export interface AnalyticsAuditFilters {
  intent?: string
  channel?: string
  emergencyOnly?: boolean
}

export interface AnalyticsAuditPageProps {
  summary: AnalyticsSummaryDTO
  history: ConversationHistoryPageDTO
  filters: AnalyticsAuditFilters
  onFiltersChange?: (filters: AnalyticsAuditFilters) => void
  onPageChange?: (page: number) => void
}

const piiPatterns = [
  /\b\d{9,12}\b/,
  /\b0\d{8,10}\b/,
  /\b\d{4}-\d{2}-\d{2}\b/,
  /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i,
]

export function containsPotentialPii(value: string): boolean {
  return piiPatterns.some((pattern) => pattern.test(value))
}

function safePreview(value: string): string {
  return containsPotentialPii(value) ? '[redacted]' : value
}

function formatMetric(value: number): string {
  return new Intl.NumberFormat('vi-VN').format(value)
}

export function AnalyticsAuditPage({
  summary,
  history,
  filters,
  onFiltersChange,
  onPageChange,
}: AnalyticsAuditPageProps) {
  const [draftFilters, setDraftFilters] = useState<AnalyticsAuditFilters>(filters)
  const unsafeRows = useMemo(
    () => history.items.filter((item) => containsPotentialPii(item.content_preview)),
    [history.items],
  )

  function updateFilter(next: AnalyticsAuditFilters) {
    setDraftFilters(next)
    onFiltersChange?.(next)
  }

  return (
    <main aria-label="Analytics and audit dashboard">
      <header>
        <h1>Analytics & audit</h1>
        <p>Chỉ hiển thị dữ liệu tổng hợp và conversation preview đã ẩn danh.</p>
      </header>

      <section aria-labelledby="analytics-summary-heading">
        <h2 id="analytics-summary-heading">Analytics summary</h2>
        <dl>
          <div><dt>Total conversations</dt><dd>{formatMetric(summary.total_conversations)}</dd></div>
          <div><dt>Emergency events</dt><dd>{formatMetric(summary.emergency_events)}</dd></div>
          <div><dt>Unresolved content conflicts</dt><dd>{formatMetric(summary.unresolved_conflicts)}</dd></div>
          <div><dt>Average response time</dt><dd>{formatMetric(summary.average_response_ms)} ms</dd></div>
          <div><dt>PII redaction failures</dt><dd>{formatMetric(summary.pii_redaction_failures)}</dd></div>
          <div><dt>Generated at</dt><dd>{summary.generated_at}</dd></div>
        </dl>
      </section>

      <section aria-labelledby="analytics-breakdown-heading">
        <h2 id="analytics-breakdown-heading">Intent and channel breakdown</h2>
        <h3>Top intents</h3>
        <ul>
          {summary.top_intents.map((item) => <li key={item.intent}>{item.intent}: {formatMetric(item.count)}</li>)}
        </ul>
        <h3>Channels</h3>
        <ul>
          {summary.channels.map((item) => <li key={item.channel}>{item.channel}: {formatMetric(item.count)}</li>)}
        </ul>
      </section>

      <section aria-labelledby="conversation-filters-heading">
        <h2 id="conversation-filters-heading">Conversation history filters</h2>
        <label htmlFor="intent-filter">Intent</label>
        <input
          id="intent-filter"
          value={draftFilters.intent ?? ''}
          onChange={(event) => updateFilter({ ...draftFilters, intent: event.target.value || undefined })}
        />
        <label htmlFor="channel-filter">Channel</label>
        <select
          id="channel-filter"
          value={draftFilters.channel ?? ''}
          onChange={(event) => updateFilter({ ...draftFilters, channel: event.target.value || undefined })}
        >
          <option value="">All</option>
          <option value="web_widget">web_widget</option>
          <option value="web_page">web_page</option>
          <option value="admin_preview">admin_preview</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={draftFilters.emergencyOnly ?? false}
            onChange={(event) => updateFilter({ ...draftFilters, emergencyOnly: event.target.checked })}
          />
          Emergency only
        </label>
      </section>

      <section aria-labelledby="conversation-history-heading">
        <h2 id="conversation-history-heading">Conversation audit history</h2>
        {unsafeRows.length > 0 ? <p role="alert">Potential PII was redacted from {unsafeRows.length} preview row(s).</p> : null}
        <table>
          <thead>
            <tr><th>Time</th><th>Session</th><th>Channel</th><th>Intent</th><th>Emergency</th><th>Preview</th><th>Tools</th></tr>
          </thead>
          <tbody>
            {history.items.map((item) => (
              <tr key={item.message_id}>
                <td>{item.created_at}</td>
                <td>{item.session_id}</td>
                <td>{item.channel}</td>
                <td>{item.intent}</td>
                <td>{item.emergency_triggered ? 'yes' : 'no'}</td>
                <td>{safePreview(item.content_preview)}</td>
                <td>{item.tools_called.join(', ') || 'none'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <nav aria-label="Conversation history pagination">
          <button type="button" disabled={history.page.page <= 1} onClick={() => onPageChange?.(history.page.page - 1)}>Previous page</button>
          <span>Page {history.page.page} of {history.page.total_pages}</span>
          <button type="button" disabled={history.page.page >= history.page.total_pages} onClick={() => onPageChange?.(history.page.page + 1)}>Next page</button>
        </nav>
      </section>
    </main>
  )
}
// === TASK:WP-506:END ===
