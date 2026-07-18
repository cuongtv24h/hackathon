// === TASK:WP-504:START ===
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EmergencyBanner, type EmergencySafetyResponse } from './EmergencyBanner'

const triggeredLevelOne: EmergencySafetyResponse = {
  outcome: 'emergency_triggered',
  level: 1,
  path: 'contact_handoff',
  banner: 'Có dấu hiệu cần hỗ trợ khẩn cấp',
  event_id: 'evt-emergency-1',
  protocol_content: {
    title: 'Giữ an toàn trong khi liên hệ bệnh viện',
    instructions: ['Dừng hoạt động đang làm.', 'Gọi hotline hoặc nhờ người thân hỗ trợ.', 'Chuẩn bị thông tin vị trí hiện tại.'],
    disclaimer: 'Không tự dùng thuốc nếu chưa có chỉ định.',
  },
  contacts: [
    { label: 'Hotline cấp cứu', value: '115', type: 'hotline', configured_from: 'mock' },
    { label: 'Địa chỉ bệnh viện', value: 'Số 1 Trần Hưng Đạo', type: 'address', configured_from: 'mock' },
    { label: 'Trang hướng dẫn', value: 'https://hospital.example/emergency', type: 'url', configured_from: 'local_config' },
  ],
  suggested_actions: [{ action_id: 'call-hospital', label: 'Gọi bệnh viện', type: 'contact' }],
}

describe('EmergencyBanner', () => {
  it('renders high-priority emergency protocol, contact links, mock config warnings, and Level-1 handoff', () => {
    render(<EmergencyBanner response={triggeredLevelOne} />)

    const banner = screen.getByRole('alert', { name: 'Emergency safety banner' })
    expect(banner).toHaveAttribute('aria-live', 'assertive')
    expect(within(banner).getByText('Level 1')).toBeInTheDocument()
    expect(within(banner).getByRole('heading', { name: 'Có dấu hiệu cần hỗ trợ khẩn cấp' })).toBeInTheDocument()

    const protocol = within(banner).getByLabelText('Emergency protocol')
    expect(within(protocol).getByText('Dừng hoạt động đang làm.')).toBeInTheDocument()
    expect(within(protocol).getByText('Không tự dùng thuốc nếu chưa có chỉ định.')).toBeInTheDocument()

    const contacts = within(banner).getByLabelText('Emergency contacts')
    expect(within(contacts).getByRole('link', { name: 'Hotline cấp cứu: 115' })).toHaveAttribute('href', 'tel:115')
    expect(within(contacts).getByRole('link', { name: 'Trang hướng dẫn' })).toHaveAttribute(
      'href',
      'https://hospital.example/emergency',
    )
    expect(within(contacts).getAllByText(/Cảnh báo cấu hình: giá trị mock/i)).toHaveLength(2)

    const handoff = within(banner).getByLabelText('Level-1 contact handoff')
    expect(within(handoff).getByRole('button', { name: 'Gọi bệnh viện' })).toBeInTheDocument()
    expect(within(banner).getByText('Mã sự kiện: evt-emergency-1')).toBeInTheDocument()
    expect(within(banner).getByText(/không phải là chẩn đoán y khoa/i)).toBeInTheDocument()
  })

  it('uses hotline and address fallback fields with mock configuration warnings', () => {
    render(
      <EmergencyBanner
        response={{
          outcome: 'emergency_triggered',
          level: 2,
          hotline: '024-0000-0000',
          address: 'Cổng cấp cứu',
          banner: 'Kích hoạt hướng dẫn khẩn cấp',
        }}
      />,
    )

    const contacts = screen.getByLabelText('Emergency contacts')
    expect(within(contacts).getByRole('link', { name: 'Hotline: 024-0000-0000' })).toHaveAttribute(
      'href',
      'tel:024-0000-0000',
    )
    expect(within(contacts).getByText('Địa chỉ: Cổng cấp cứu')).toBeInTheDocument()
    expect(within(contacts).getAllByText(/giá trị mock/i)).toHaveLength(2)
    expect(screen.queryByLabelText('Level-1 contact handoff')).not.toBeInTheDocument()
  })

  it('renders clarification-required state without medical certainty', () => {
    render(
      <EmergencyBanner
        response={{
          outcome: 'clarification_required',
          banner: 'Cần thêm thông tin an toàn',
          suggested_actions: [],
        }}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Vui lòng cung cấp thêm thông tin')
    expect(screen.getByRole('alert')).toHaveTextContent('Đây không phải là chẩn đoán y khoa')
  })

  it('does not render a banner when emergency safety is not triggered', () => {
    const { container } = render(<EmergencyBanner response={{ outcome: 'not_triggered' }} />)

    expect(container).toBeEmptyDOMElement()
  })
})
// === TASK:WP-504:END ===
