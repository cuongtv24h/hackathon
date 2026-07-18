// === TASK:WP-502:START ===
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { InformationResponse, type InformationAssistanceResponse } from './InformationResponse'

const answeredResponse: InformationAssistanceResponse = {
  outcome: 'answered',
  message: 'Bệnh viện tiếp nhận khám từ 7:00 đến 16:30 các ngày làm việc.',
  citations: [
    {
      source_id: 'gio-lam-viec-2026',
      title: 'Quy định giờ làm việc',
      url: 'https://hospital.example/gio-lam-viec',
      excerpt: 'Khoa khám bệnh tiếp nhận từ 7:00.',
      effective_date: '2026-01-01',
    },
  ],
  suggested_actions: [
    {
      action_id: 'book-appointment',
      label: 'Đặt lịch khám',
      type: 'appointment_booking',
    },
  ],
  conversation_state: { topic: 'gio_lam_viec' },
  explainability: {
    grounded: true,
    confidence: 'high',
    source_count: 1,
  },
}

describe('InformationResponse', () => {
  it('renders a grounded answer with accessible citation links and next actions', () => {
    render(<InformationResponse response={answeredResponse} />)

    expect(screen.getByLabelText('Response outcome')).toHaveTextContent('Đã trả lời dựa trên nguồn chính thức')
    expect(screen.getByText(answeredResponse.message)).toBeInTheDocument()

    const citations = screen.getByLabelText('Citations')
    const citationLink = within(citations).getByRole('link', { name: 'Quy định giờ làm việc' })
    expect(citationLink).toHaveAttribute('href', 'https://hospital.example/gio-lam-viec')
    expect(citationLink).toHaveAttribute('rel', 'noreferrer')
    expect(within(citations).getByText(/hiệu lực 2026-01-01/i)).toBeInTheDocument()
    expect(within(citations).getByText('Khoa khám bệnh tiếp nhận từ 7:00.')).toBeInTheDocument()

    expect(screen.getByLabelText('Explainability')).toHaveTextContent('Có căn cứ từ nguồn chính thức')
    expect(screen.getByLabelText('Explainability')).toHaveTextContent('Số nguồn: 1')
    expect(screen.getByRole('button', { name: 'Đặt lịch khám' })).toBeInTheDocument()
  })

  it('marks fallback content as not certain and does not imply grounded certainty', () => {
    render(
      <InformationResponse
        response={{
          outcome: 'fallback',
          message: 'Hiện chưa đủ dữ liệu chính thức để xác nhận thông tin này.',
          citations: [],
          suggested_actions: [{ action_id: 'contact', label: 'Liên hệ bệnh viện', type: 'contact' }],
          explainability: { grounded: false, confidence: 'low', source_count: 0 },
        }}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('không được hiển thị như câu trả lời chắc chắn')
    expect(screen.getByLabelText('Response outcome')).toHaveTextContent('Chưa đủ căn cứ để trả lời chắc chắn')
    expect(screen.getByLabelText('Explainability')).toHaveTextContent('Chưa đủ căn cứ từ nguồn chính thức')
    expect(screen.getByLabelText('Citations')).toHaveTextContent('Không có nguồn chính thức được đính kèm.')
    expect(screen.getByRole('button', { name: 'Liên hệ bệnh viện' })).toBeInTheDocument()
  })

  it('handles clarification-required responses as uncertain UI state', () => {
    render(
      <InformationResponse
        response={{
          outcome: 'clarification_required',
          message: 'Bạn vui lòng cho biết bạn cần hỏi về BHYT hay giá dịch vụ?',
          citations: [],
          suggested_actions: [],
          explainability: { grounded: false, source_count: 0 },
        }}
      />,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByLabelText('Response outcome')).toHaveTextContent('Cần thêm thông tin để trả lời chính xác')
    expect(screen.queryByLabelText('Suggested actions')).not.toBeInTheDocument()
  })
})
// === TASK:WP-502:END ===
