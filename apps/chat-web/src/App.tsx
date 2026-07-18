// === TASK:WP-500:START ===
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { AppointmentFlow, type AppointmentBookingResponse, type AppointmentStatusResponse } from './features/appointments/AppointmentFlow'
import { EmergencyBanner, type EmergencySafetyResponse } from './features/emergency-safety/EmergencyBanner'
import { InformationResponse, type InformationAssistanceResponse } from './features/information-assistance/InformationResponse'
import { ChatClient, ChatClientError, type ChatCapability, type CapabilityResponseEnvelope, type FoundationPage } from './shared/ChatClient'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? ''
const sessionId = `web-${crypto.randomUUID()}`

type Specialty = { specialty_id: string; name: string; description?: string }
type Doctor = { doctor_id: string; full_name: string; title: string; profile_summary?: string }
type AvailableSlot = { slot_id: string; date: string; time: string; room: string }
type BookingStep = 'specialty' | 'doctor' | 'slot' | 'patient'
type ChatMessage = { id: string; side: 'assistant' | 'user'; text?: string; envelope?: CapabilityResponseEnvelope }

const quickActions = [
  { id: 'price', icon: '₫', title: 'Giá dịch vụ', prompt: 'Cho tôi biết bảng giá dịch vụ kỹ thuật.' },
  { id: 'process', icon: '⌁', title: 'Quy trình khám', prompt: 'Hướng dẫn quy trình tiếp đón và khám bệnh.' },
  { id: 'insurance', icon: '✚', title: 'Thông tin BHYT', prompt: 'Tôi cần hướng dẫn khám chữa bệnh bằng BHYT.' },
  { id: 'booking', icon: '◷', title: 'Đặt lịch khám', prompt: '' },
  { id: 'status', icon: '⌕', title: 'Tra cứu lịch hẹn', prompt: '' },
  { id: 'emergency', icon: '!', title: 'Tình huống khẩn cấp', prompt: 'Tôi cần hỗ trợ khẩn cấp.' },
]

function App() {
  const [input, setInput] = useState('')
  const [mode, setMode] = useState<'chat' | 'booking' | 'status'>('chat')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 'welcome', side: 'assistant', text: 'Xin chào, tôi là Trợ lý Bệnh viện. Tôi có thể hỗ trợ bạn tra cứu thông tin, hướng dẫn BHYT, đặt lịch khám hoặc xử lý tình huống khẩn cấp.' },
  ])
  const [specialties, setSpecialties] = useState<Specialty[]>([])
  const [doctors, setDoctors] = useState<Doctor[]>([])
  const [slots, setSlots] = useState<AvailableSlot[]>([])
  const [bookingStep, setBookingStep] = useState<BookingStep>('specialty')
  const [booking, setBooking] = useState({ visit_type: 'first_visit', specialty_id: '', doctor_id: '', slot_id: '', patient_name: '', patient_phone: '', patient_dob: '', has_insurance: false, visit_reason: '' })
  const [bookingIdempotencyKey, setBookingIdempotencyKey] = useState<string | null>(null)
  const [referenceLoading, setReferenceLoading] = useState(false)
  const context = useMemo(() => ({ channel: 'web_page' as const, locale: 'vi-VN' as const }), [])
  const client = useMemo(() => new ChatClient({ baseUrl: apiBaseUrl }), [])
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const target = endRef.current
    if (target && typeof target.scrollIntoView === 'function') target.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, mode, bookingStep])

  useEffect(() => {
    if (mode !== 'booking' || specialties.length) return
    setReferenceLoading(true)
    void client.get<FoundationPage<Specialty>>('/v1/foundation/specialties')
      .then((page) => setSpecialties(page.items))
      .catch(() => setError('Không thể tải danh sách chuyên khoa. Vui lòng thử lại.'))
      .finally(() => setReferenceLoading(false))
  }, [client, mode, specialties.length])

  useEffect(() => {
    if (!booking.specialty_id) return
    setReferenceLoading(true)
    void client.get<FoundationPage<Doctor>>(`/v1/foundation/doctors?specialty_id=${encodeURIComponent(booking.specialty_id)}`)
      .then((page) => setDoctors(page.items))
      .catch(() => setError('Không thể tải danh sách bác sĩ. Vui lòng thử lại.'))
      .finally(() => setReferenceLoading(false))
  }, [booking.specialty_id, client])

  useEffect(() => {
    if (!booking.doctor_id) return
    setReferenceLoading(true)
    void client.get<FoundationPage<AvailableSlot>>(`/v1/foundation/doctors/${encodeURIComponent(booking.doctor_id)}/available-slots`)
      .then((page) => setSlots(page.items))
      .catch(() => setError('Không thể tải khung giờ khám. Vui lòng thử lại.'))
      .finally(() => setReferenceLoading(false))
  }, [booking.doctor_id, client])

  function addUser(text: string) { setMessages((current) => [...current, { id: crypto.randomUUID(), side: 'user', text }]) }
  function addEnvelope(envelope: CapabilityResponseEnvelope) { setMessages((current) => [...current, { id: crypto.randomUUID(), side: 'assistant', envelope }]) }

  async function execute(capability: ChatCapability, text: string, extra: Record<string, unknown> = {}) {
    setLoading(true); setError(null); addUser(text || 'Yêu cầu hỗ trợ')
    const payload = capability === 'appointment_status'
      ? { request_id: crypto.randomUUID(), session_id: sessionId, appointment_reference: { appointment_id: text.trim() }, ...extra }
      : { request_id: crypto.randomUUID(), session_id: sessionId, message: text, ...extra }
    try {
      if (capability === 'information_assistance') {
        await client.sendStream({ capability, payload, context }, (event, envelope) => { if (event === 'completed') addEnvelope(envelope) })
      } else addEnvelope(await client.send({ capability, payload, context }))
    } catch (caught) {
      setError(caught instanceof ChatClientError ? caught.message : 'Không thể kết nối tới dịch vụ. Vui lòng thử lại.')
    } finally { setLoading(false) }
  }

  async function submitChat(event: FormEvent) {
    event.preventDefault()
    if (!input.trim() || loading) return
    const value = input.trim(); setInput('')
    await execute('information_assistance', value)
  }

  async function submitBooking(confirmed = false) {
    const key = bookingIdempotencyKey ?? crypto.randomUUID()
    setBookingIdempotencyKey(key)
    const label = confirmed ? 'Xác nhận đặt lịch' : 'Kiểm tra thông tin đặt lịch'
    setLoading(true); setError(null); addUser(label)
    try {
      const envelope = await client.send({
        capability: 'appointment_booking', context, idempotencyKey: confirmed ? key : undefined,
        payload: { request_id: crypto.randomUUID(), session_id: sessionId, message: confirmed ? 'confirm' : '', form_data: { ...booking, confirmed, idempotency_key: key } },
      })
      addEnvelope(envelope)
      if ((envelope.result as Record<string, unknown>).outcome === 'created') { setBookingIdempotencyKey(null); setMode('chat') }
    } catch (caught) { setError(caught instanceof ChatClientError ? caught.message : 'Không thể xử lý đặt lịch. Vui lòng thử lại.') }
    finally { setLoading(false) }
  }

  function chooseAction(action: typeof quickActions[number]) {
    setError(null)
    if (action.id === 'booking') { setMode('booking'); setBookingStep('specialty'); return }
    if (action.id === 'status') { setMode('status'); return }
    void execute(action.id === 'emergency' ? 'emergency_safety' : 'information_assistance', action.prompt)
  }

  function renderEnvelope(envelope: CapabilityResponseEnvelope) {
    const data = envelope.result as Record<string, unknown>
    if (envelope.capability === 'information_assistance') return <InformationResponse response={data as unknown as InformationAssistanceResponse} />
    if (envelope.capability === 'emergency_safety') return <EmergencyBanner response={data as unknown as EmergencySafetyResponse} />
    if (envelope.capability === 'appointment_booking') return <AppointmentFlow bookingResponse={data as unknown as AppointmentBookingResponse} onConfirmBooking={() => void submitBooking(true)} onCancelBooking={() => setMode('chat')} />
    return <AppointmentFlow statusResponse={data as unknown as AppointmentStatusResponse} />
  }

  return <main className="chat-page" aria-label="Hospital Assistant chat">
    <section className="chat-shell">
      <header className="chat-header"><div className="brand-mark">✚</div><div><h1>Trợ lý Bệnh viện</h1><span><i /> Trực tuyến · Hỗ trợ 24/7</span></div><button className="new-chat" onClick={() => { setMessages(messages.slice(0, 1)); setMode('chat') }}>↺ Cuộc trò chuyện mới</button></header>
      <section className="conversation" aria-live="polite">
        {messages.map((item) => <article key={item.id} className={`message ${item.side}`}><div className="avatar">{item.side === 'assistant' ? '✚' : 'Bạn'}</div><div className="bubble">{item.text ? <p>{item.text}</p> : null}{item.envelope ? renderEnvelope(item.envelope) : null}</div></article>)}
        {mode === 'chat' && messages.length === 1 ? <section className="quick-actions" aria-label="Gợi ý hỗ trợ"><p>Bạn đang cần hỗ trợ về vấn đề nào?</p><div>{quickActions.map((action) => <button key={action.id} onClick={() => chooseAction(action)}><b>{action.icon}</b><span>{action.title}</span><small>›</small></button>)}</div></section> : null}
        {mode === 'booking' ? <section className="guided-card" aria-label="Đặt lịch khám"><button className="back-link" onClick={() => setMode('chat')}>← Quay lại</button><p className="eyebrow">ĐẶT LỊCH KHÁM · BƯỚC {bookingStep === 'specialty' ? '1' : bookingStep === 'doctor' ? '2' : bookingStep === 'slot' ? '3' : '4'}/4</p>
          {bookingStep === 'specialty' ? <><h2>Chọn chuyên khoa</h2><div className="choice-grid">{specialties.map((x) => <button onClick={() => { setBooking({ ...booking, specialty_id: x.specialty_id, doctor_id: '', slot_id: '' }); setBookingStep('doctor') }} key={x.specialty_id}><b>{x.name}</b><span>{x.description || 'Tư vấn và khám theo chuyên khoa'}</span></button>)}</div></> : null}
          {bookingStep === 'doctor' ? <><h2>Chọn bác sĩ</h2><div className="choice-grid">{doctors.map((x) => <button onClick={() => { setBooking({ ...booking, doctor_id: x.doctor_id, slot_id: '' }); setBookingStep('slot') }} key={x.doctor_id}><b>{x.title} {x.full_name}</b><span>{x.profile_summary || 'Bác sĩ chuyên khoa'}</span></button>)}</div><button className="text-button" onClick={() => setBookingStep('specialty')}>Chọn lại chuyên khoa</button></> : null}
          {bookingStep === 'slot' ? <><h2>Chọn khung giờ còn trống</h2><div className="slot-grid">{slots.map((x) => <button onClick={() => { setBooking({ ...booking, slot_id: x.slot_id }); setBookingStep('patient') }} key={x.slot_id}><b>{x.time}</b><span>{x.date} · {x.room}</span></button>)}</div><button className="text-button" onClick={() => setBookingStep('doctor')}>Chọn lại bác sĩ</button></> : null}
          {bookingStep === 'patient' ? <form className="patient-form" onSubmit={(event) => { event.preventDefault(); void submitBooking(false) }}><h2>Thông tin người khám</h2><div className="visit-toggle"><button type="button" className={booking.visit_type === 'first_visit' ? 'selected' : ''} onClick={() => setBooking({ ...booking, visit_type: 'first_visit' })}>Khám lần đầu</button><button type="button" className={booking.visit_type === 'follow_up' ? 'selected' : ''} onClick={() => setBooking({ ...booking, visit_type: 'follow_up' })}>Tái khám</button></div><label>Họ và tên<input required value={booking.patient_name} onChange={(e) => setBooking({ ...booking, patient_name: e.target.value })} /></label><label>Số điện thoại<input required inputMode="tel" value={booking.patient_phone} onChange={(e) => setBooking({ ...booking, patient_phone: e.target.value })} /></label><label>Ngày sinh<input required type="date" value={booking.patient_dob} onChange={(e) => setBooking({ ...booking, patient_dob: e.target.value })} /></label><label>Lý do khám<input required value={booking.visit_reason} onChange={(e) => setBooking({ ...booking, visit_reason: e.target.value })} /></label><label className="check"><input type="checkbox" checked={booking.has_insurance} onChange={(e) => setBooking({ ...booking, has_insurance: e.target.checked })} /> Tôi có thẻ BHYT</label><button className="primary" disabled={loading}>Kiểm tra và xác nhận</button></form> : null}
          {referenceLoading ? <p className="loading-copy">Đang tải dữ liệu đặt lịch…</p> : null}</section> : null}
        {mode === 'status' ? <section className="guided-card status-card"><button className="back-link" onClick={() => setMode('chat')}>← Quay lại</button><h2>Tra cứu lịch hẹn</h2><p>Nhập mã lịch hẹn của bạn để xem trạng thái mới nhất.</p><form onSubmit={(event) => { event.preventDefault(); const id = input.trim(); if (id) { setInput(''); setMode('chat'); void execute('appointment_status', id) } }}><input aria-label="Mã lịch hẹn" placeholder="Ví dụ: HEN-2026-0001" value={input} onChange={(e) => setInput(e.target.value)} /><button className="primary" disabled={!input.trim() || loading}>Tra cứu lịch</button></form></section> : null}
        {loading ? <div className="typing"><i /><i /><i /> Đang xử lý yêu cầu…</div> : null}
        {error ? <p className="error" role="alert">{error}</p> : null}<div ref={endRef} />
      </section>
      <footer className="composer"><form onSubmit={submitChat}><textarea aria-label="Nội dung" placeholder="Nhập câu hỏi của bạn…" value={input} onChange={(e) => setInput(e.target.value)} disabled={loading || mode !== 'chat'} /><button aria-label="Gửi" disabled={!input.trim() || loading || mode !== 'chat'}>↑</button></form><p>Thông tin chỉ mang tính tham khảo, không thay thế tư vấn y tế trực tiếp.</p></footer>
    </section>
  </main>
}

export default App
// === TASK:WP-500:END ===
