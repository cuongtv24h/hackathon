// === TASK:WP-503:START ===
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AppointmentFlow } from './AppointmentFlow'

describe('AppointmentFlow', () => {
  it('requires an explicit confirmation before creating an appointment', () => {
    const onConfirmBooking = vi.fn()
    render(
      <AppointmentFlow
        bookingResponse={{ outcome: 'confirmation_required', prompt: 'Kiểm tra lại thông tin lịch hẹn.' }}
        onConfirmBooking={onConfirmBooking}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận đặt lịch' }))
    expect(onConfirmBooking).toHaveBeenCalledOnce()
  })

  it('shows a pending appointment with its reference', () => {
    render(
      <AppointmentFlow
        bookingResponse={{
          outcome: 'appointment_pending',
          appointment: { appointment_id: 'HEN-2026-0001', status: 'pending', doctor_id: 'DR-001' },
        }}
      />,
    )

    expect(screen.getByText('HEN-2026-0001')).toBeInTheDocument()
    expect(screen.getByText('pending')).toBeInTheDocument()
  })

  it('renders a safe not-found result and its next step', () => {
    const onNextStep = vi.fn()
    render(
      <AppointmentFlow
        statusResponse={{
          outcome: 'not_found',
          message: 'Không tìm thấy lịch hẹn với mã đã cung cấp.',
          next_steps: [{ action: 'verify_appointment_code', label: 'Kiểm tra lại mã lịch hẹn' }],
        }}
        onNextStep={onNextStep}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra lại mã lịch hẹn' }))
    expect(onNextStep).toHaveBeenCalledWith('verify_appointment_code')
  })

  it('renders an unavailable booking fallback', () => {
    render(<AppointmentFlow bookingResponse={{ outcome: 'unavailable' }} />)
    expect(screen.getByText('Hiện chưa thể đặt lịch. Vui lòng thử lại sau.')).toBeInTheDocument()
  })
})
// === TASK:WP-503:END ===
