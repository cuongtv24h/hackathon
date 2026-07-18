// === TASK:WP-503:START ===
export type AppointmentBookingOutcome =
  | 'collecting_information'
  | 'confirmation_required'
  | 'appointment_pending'
  | 'cancelled'
  | 'redirected'
  | 'unavailable'

export type AppointmentStatusOutcome = 'found' | 'not_found' | 'redirected' | 'unavailable'

export interface AppointmentSummary {
  appointment_id: string
  doctor_id?: string
  slot_id?: string
  status: 'pending' | 'confirmed' | 'cancelled' | 'rejected' | 'completed'
}

export interface BookingFlowState {
  step: string
  missing_fields?: string[]
}

export interface AppointmentBookingResponse {
  outcome: AppointmentBookingOutcome
  prompt?: string
  options?: Array<{ value: string; label: string }>
  appointment?: AppointmentSummary | null
  flow_state?: BookingFlowState
}

export interface AppointmentStatusResponse {
  outcome: AppointmentStatusOutcome
  message: string
  appointment?: AppointmentSummary | null
  next_steps?: Array<{ action: string; label: string }>
}

export interface AppointmentFlowProps {
  bookingResponse?: AppointmentBookingResponse
  statusResponse?: AppointmentStatusResponse
  onConfirmBooking?: () => void
  onCancelBooking?: () => void
  onSelectOption?: (value: string) => void
  onNextStep?: (action: string) => void
}

function AppointmentCard({ appointment }: { appointment: AppointmentSummary }) {
  return (
    <dl aria-label="Appointment summary">
      <dt>Mã lịch hẹn</dt>
      <dd>{appointment.appointment_id}</dd>
      <dt>Trạng thái</dt>
      <dd>{appointment.status}</dd>
      {appointment.doctor_id ? <><dt>Bác sĩ</dt><dd>{appointment.doctor_id}</dd></> : null}
      {appointment.slot_id ? <><dt>Khung giờ</dt><dd>{appointment.slot_id}</dd></> : null}
    </dl>
  )
}

function BookingState({ response, onConfirmBooking, onCancelBooking, onSelectOption }: {
  response: AppointmentBookingResponse
  onConfirmBooking?: () => void
  onCancelBooking?: () => void
  onSelectOption?: (value: string) => void
}) {
  if (response.outcome === 'confirmation_required') {
    return (
      <section aria-label="Booking confirmation">
        <p>{response.prompt ?? 'Vui lòng xác nhận thông tin đặt lịch trước khi tạo lịch hẹn.'}</p>
        <button type="button" onClick={onConfirmBooking}>Xác nhận đặt lịch</button>
        <button type="button" onClick={onCancelBooking}>Hủy</button>
      </section>
    )
  }

  if (response.outcome === 'appointment_pending' && response.appointment) {
    return (
      <section aria-label="Pending appointment">
        <p>Lịch hẹn đã được ghi nhận và đang chờ xác nhận.</p>
        <AppointmentCard appointment={response.appointment} />
      </section>
    )
  }

  if (response.outcome === 'collecting_information') {
    return (
      <section aria-label="Booking information collection">
        <p>{response.prompt ?? 'Vui lòng cung cấp thông tin còn thiếu để đặt lịch.'}</p>
        {response.flow_state?.missing_fields?.length ? (
          <p>Thông tin cần bổ sung: {response.flow_state.missing_fields.join(', ')}</p>
        ) : null}
        <div>
          {response.options?.map((option) => (
            <button key={option.value} type="button" onClick={() => onSelectOption?.(option.value)}>
              {option.label}
            </button>
          ))}
        </div>
      </section>
    )
  }

  return (
    <section aria-label="Booking unavailable">
      <p>{response.outcome === 'redirected' ? 'Vui lòng liên hệ bộ phận tiếp nhận để được hỗ trợ đặt lịch.' : 'Hiện chưa thể đặt lịch. Vui lòng thử lại sau.'}</p>
    </section>
  )
}

function StatusState({ response, onNextStep }: {
  response: AppointmentStatusResponse
  onNextStep?: (action: string) => void
}) {
  if (response.outcome === 'found' && response.appointment) {
    return (
      <section aria-label="Appointment status">
        <p>{response.message}</p>
        <AppointmentCard appointment={response.appointment} />
        {response.next_steps?.map((step) => (
          <button key={step.action} type="button" onClick={() => onNextStep?.(step.action)}>{step.label}</button>
        ))}
      </section>
    )
  }

  return (
    <section aria-label="Appointment lookup result">
      <p>{response.message}</p>
      {response.next_steps?.map((step) => (
        <button key={step.action} type="button" onClick={() => onNextStep?.(step.action)}>{step.label}</button>
      ))}
    </section>
  )
}

export function AppointmentFlow({
  bookingResponse,
  statusResponse,
  onConfirmBooking,
  onCancelBooking,
  onSelectOption,
  onNextStep,
}: AppointmentFlowProps) {
  if (statusResponse) {
    return <StatusState response={statusResponse} onNextStep={onNextStep} />
  }

  if (bookingResponse) {
    return (
      <BookingState
        response={bookingResponse}
        onConfirmBooking={onConfirmBooking}
        onCancelBooking={onCancelBooking}
        onSelectOption={onSelectOption}
      />
    )
  }

  return <p role="status">Chưa có thông tin lịch hẹn để hiển thị.</p>
}
// === TASK:WP-503:END ===
