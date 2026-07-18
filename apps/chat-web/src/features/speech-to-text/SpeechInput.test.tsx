import { StrictMode, useState } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SpeechInput } from './SpeechInput'
import type {
  SpeechRecognitionHandlers,
  SpeechRecognitionProvider,
  SpeechRecognitionSession,
} from './types'

function createProvider(supported = true) {
  let handlers: SpeechRecognitionHandlers | undefined
  const session: SpeechRecognitionSession = {
    start: vi.fn(),
    stop: vi.fn(),
    abort: vi.fn(),
  }
  const provider: SpeechRecognitionProvider = {
    isSupported: () => supported,
    create: vi.fn((_options, nextHandlers) => {
      handlers = nextHandlers
      return session
    }),
  }
  return {
    provider,
    session,
    handlers: () => {
      if (!handlers) throw new Error('Recognition session was not created')
      return handlers
    },
  }
}

function EditableTranscript({
  provider,
  onSubmit,
}: {
  provider: SpeechRecognitionProvider
  onSubmit: () => void
}) {
  const [value, setValue] = useState('')
  return (
    <form onSubmit={(event) => { event.preventDefault(); onSubmit() }}>
      <label htmlFor="transcript">Nội dung</label>
      <textarea id="transcript" value={value} onChange={(event) => setValue(event.target.value)} />
      <SpeechInput value={value} onChange={setValue} provider={provider} />
      <button type="submit">Gửi câu hỏi</button>
    </form>
  )
}

describe('SpeechInput', () => {
  it('fills an editable transcript and never submits it automatically', () => {
    const fake = createProvider()
    const onSubmit = vi.fn()
    render(<EditableTranscript provider={fake.provider} onSubmit={onSubmit} />)

    fireEvent.click(screen.getByRole('button', { name: /bắt đầu nhập bằng giọng nói/i }))
    expect(fake.provider.create).toHaveBeenCalledWith(
      { locale: 'vi-VN' },
      expect.objectContaining({
        onStart: expect.any(Function),
        onTranscript: expect.any(Function),
      }),
    )
    expect(fake.session.start).toHaveBeenCalledOnce()

    act(() => fake.handlers().onTranscript({ transcript: 'Tôi muốn đặt lịch', isFinal: true }))
    expect(screen.getByLabelText('Nội dung')).toHaveValue('Tôi muốn đặt lịch')
    expect(onSubmit).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Nội dung'), {
      target: { value: 'Tôi muốn đặt lịch khám tim' },
    })
    expect(screen.getByLabelText('Nội dung')).toHaveValue('Tôi muốn đặt lịch khám tim')
    expect(onSubmit).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /gửi câu hỏi/i }))
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it('lets the user stop recognition and exposes the listening state accessibly', () => {
    const fake = createProvider()
    render(<SpeechInput value="" onChange={vi.fn()} provider={fake.provider} />)

    fireEvent.click(screen.getByRole('button', { name: /bắt đầu/i }))
    const stopButton = screen.getByRole('button', { name: /dừng nhập/i })
    expect(stopButton).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(stopButton)
    expect(fake.session.stop).toHaveBeenCalledOnce()
    expect(screen.getByText(/đang hoàn tất/i)).toBeInTheDocument()
  })

  it('shows permission failures and keeps keyboard input available', () => {
    const fake = createProvider()
    render(<EditableTranscript provider={fake.provider} onSubmit={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /bắt đầu/i }))
    act(() => fake.handlers().onError({
      code: 'not-allowed',
      message: 'Không thể dùng micro. Hãy cấp quyền micro cho trình duyệt rồi thử lại.',
    }))

    expect(screen.getByText(/cấp quyền micro/i)).toBeInTheDocument()
    expect(screen.getByLabelText('Nội dung')).not.toBeDisabled()
  })

  it('disables only the voice action when the browser is unsupported', () => {
    const fake = createProvider(false)
    render(<EditableTranscript provider={fake.provider} onSubmit={vi.fn()} />)

    expect(screen.getByRole('button', { name: /bắt đầu nhập bằng giọng nói/i })).toBeDisabled()
    expect(screen.getByText(/vẫn có thể dùng bàn phím/i)).toBeInTheDocument()
    expect(screen.getByLabelText('Nội dung')).not.toBeDisabled()
  })

  it('aborts an active recognition session when unmounted', () => {
    const fake = createProvider()
    const view = render(<SpeechInput value="" onChange={vi.fn()} provider={fake.provider} />)

    fireEvent.click(screen.getByRole('button', { name: /bắt đầu/i }))
    view.unmount()

    expect(fake.session.abort).toHaveBeenCalledOnce()
  })

  it('accepts recognition events when the app runs in React StrictMode', () => {
    const fake = createProvider()
    const onChange = vi.fn()
    render(
      <StrictMode>
        <SpeechInput value="" onChange={onChange} provider={fake.provider} />
      </StrictMode>,
    )

    fireEvent.click(screen.getByRole('button', { name: /bắt đầu/i }))
    act(() => fake.handlers().onTranscript({ transcript: 'Giờ khám hôm nay', isFinal: true }))

    expect(onChange).toHaveBeenCalledWith('Giờ khám hôm nay')
  })

  it('ignores late browser events after the composer becomes disabled', () => {
    const fake = createProvider()
    const onChange = vi.fn()
    const view = render(<SpeechInput value="" onChange={onChange} provider={fake.provider} />)

    fireEvent.click(screen.getByRole('button', { name: /bắt đầu/i }))
    view.rerender(<SpeechInput value="" onChange={onChange} provider={fake.provider} disabled />)
    act(() => fake.handlers().onTranscript({ transcript: 'Sự kiện đến muộn', isFinal: true }))

    expect(fake.session.abort).toHaveBeenCalledOnce()
    expect(onChange).not.toHaveBeenCalled()
  })
})
