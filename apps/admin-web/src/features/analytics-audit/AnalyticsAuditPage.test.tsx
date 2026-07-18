// === TASK:WP-506:START ===
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { AnalyticsAuditPage, containsPotentialPii } from './AnalyticsAuditPage'

const summary = {
  total_conversations: 1234,
  emergency_events: 7,
  unresolved_conflicts: 2,
  average_response_ms: 480,
  top_intents: [
    { intent: 'information_assistance', count: 900 },
    { intent: 'appointment_status', count: 120 },
  ],
  channels: [
    { channel: 'web_widget', count: 800 },
    { channel: 'web_page', count: 434 },
  ],
  pii_redaction_failures: 0,
  generated_at: '2026-07-18T06:00:00Z',
}

const history = {
  items: [
    {
      message_id: 'MSG-001',
      session_id: 'SES-001',
      channel: 'web_widget' as const,
      role: 'user' as const,
      content_preview: 'Cho tôi hỏi lịch khám tim mạch',
      intent: 'information_assistance',
      tools_called: ['knowledge_search'],
      emergency_triggered: false,
      created_at: '2026-07-18T06:01:00Z',
    },
    {
      message_id: 'MSG-002',
      session_id: 'SES-002',
      channel: 'web_page' as const,
      role: 'user' as const,
      content_preview: 'Số điện thoại 0912345678 cần được ẩn',
      intent: 'appointment_status',
      tools_called: [],
      emergency_triggered: true,
      created_at: '2026-07-18T06:02:00Z',
    },
  ],
  page: {
    page: 2,
    page_size: 10,
    total_items: 25,
    total_pages: 3,
  },
}

describe('AnalyticsAuditPage', () => {
  it('renders analytics summary and breakdown without provider or network calls', () => {
    render(<AnalyticsAuditPage summary={summary} history={history} filters={{}} />)

    expect(screen.getByRole('heading', { name: 'Analytics summary' })).toBeInTheDocument()
    expect(screen.getByText('1.234')).toBeInTheDocument()
    expect(screen.getByText('information_assistance: 900')).toBeInTheDocument()
    expect(screen.getByText('web_widget: 800')).toBeInTheDocument()
  })

  it('redacts potential PII from conversation previews', () => {
    render(<AnalyticsAuditPage summary={summary} history={history} filters={{}} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Potential PII was redacted from 1 preview row(s).')
    expect(screen.queryByText(/0912345678/)).not.toBeInTheDocument()
    const row = screen.getByRole('row', { name: /SES-002/ })
    expect(within(row).getByText('[redacted]')).toBeInTheDocument()
  })

  it('emits filter changes using the contract-shaped filter object', () => {
    const onFiltersChange = vi.fn()
    render(<AnalyticsAuditPage summary={summary} history={history} filters={{}} onFiltersChange={onFiltersChange} />)

    fireEvent.change(screen.getByLabelText('Intent'), { target: { value: 'appointment_status' } })
    expect(onFiltersChange).toHaveBeenLastCalledWith({ intent: 'appointment_status' })

    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'web_page' } })
    expect(onFiltersChange).toHaveBeenLastCalledWith({ intent: 'appointment_status', channel: 'web_page' })

    fireEvent.click(screen.getByLabelText('Emergency only'))
    expect(onFiltersChange).toHaveBeenLastCalledWith({ intent: 'appointment_status', channel: 'web_page', emergencyOnly: true })
  })

  it('emits pagination requests according to PageMetadataDTO', () => {
    const onPageChange = vi.fn()
    render(<AnalyticsAuditPage summary={summary} history={history} filters={{}} onPageChange={onPageChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    expect(onPageChange).toHaveBeenCalledWith(1)
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(onPageChange).toHaveBeenCalledWith(3)
  })

  it('detects common PII-shaped values before display', () => {
    expect(containsPotentialPii('email patient@example.com')).toBe(true)
    expect(containsPotentialPii('DOB 1990-01-01')).toBe(true)
    expect(containsPotentialPii('safe analytics aggregate')).toBe(false)
  })
})
// === TASK:WP-506:END ===
