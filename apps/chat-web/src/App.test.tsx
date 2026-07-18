// === TASK:WP-500:START ===
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

describe('App conversational experience', () => {
  it('welcomes the visitor and presents JTBD quick actions', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /trợ lý bệnh viện/i })).toBeInTheDocument()
    expect(screen.getByText(/tôi có thể hỗ trợ bạn/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /giá dịch vụ/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /đặt lịch khám/i })).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('guides appointment selection through specialty, doctor and slot buttons', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/v1/foundation/specialties')) return new Response(JSON.stringify({ items: [{ specialty_id: 'SP-01', name: 'Tim mạch', description: 'Khám tim mạch' }] }), { status: 200 })
      if (url.includes('/v1/foundation/doctors?specialty_id=SP-01')) return new Response(JSON.stringify({ items: [{ doctor_id: 'DOC-01', full_name: 'Nguyễn Văn A', title: 'BS.', profile_summary: 'Bác sĩ tim mạch' }] }), { status: 200 })
      if (url.includes('/v1/foundation/doctors/DOC-01/available-slots')) return new Response(JSON.stringify({ items: [{ slot_id: 'SL-01', date: '2026-07-20', time: '09:00', room: 'P101' }] }), { status: 200 })
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetcher)
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: /đặt lịch khám/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /tim mạch/i })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /tim mạch/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /nguyễn văn a/i })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /nguyễn văn a/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /09:00/i })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /09:00/i }))
    expect(screen.getByRole('heading', { name: /thông tin người khám/i })).toBeInTheDocument()
  })

  it('routes a typed booking intent to the guided booking flow without calling the LLM capability', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/v1/foundation/specialties')) {
        return new Response(JSON.stringify({ items: [{ specialty_id: 'SP-01', name: 'Tim mạch' }] }), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetcher)
    render(<App />)

    fireEvent.change(screen.getByLabelText(/nội dung/i), { target: { value: 'Tôi muốn đặt lịch khám' } })
    fireEvent.submit(screen.getByLabelText(/nội dung/i).closest('form')!)

    await waitFor(() => expect(screen.getByRole('heading', { name: /chọn chuyên khoa/i })).toBeInTheDocument())
    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('/v1/foundation/specialties'),
      expect.anything(),
    )
    expect(fetcher.mock.calls.some(([url]) => String(url).includes('information-assistance:execute'))).toBe(false)
  })
})
// === TASK:WP-500:END ===
