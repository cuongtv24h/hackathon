// === TASK:WP-505:START ===
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ContentManagementPage } from './ContentManagementPage'

const draft = {
  content_id: 'CNT-001',
  title: 'Hướng dẫn khám BHYT',
  domain: 'bhyt',
  approval_state: 'draft' as const,
  version: '1.0.0',
  updated_at: '2026-07-18T00:00:00+00:00',
}

const conflict = {
  conflict_id: 'CON-001',
  source_chunk_ids: ['KCH-001', 'KCH-002'],
  conflicting_fields: ['price'],
  due_at: '2026-07-19T00:00:00+00:00',
  state: 'open' as const,
}

describe('ContentManagementPage', () => {
  it('shows the workflow action allowed for a draft', () => {
    const onWorkflowAction = vi.fn()
    render(<ContentManagementPage drafts={[draft]} conflicts={[]} onWorkflowAction={onWorkflowAction} />)

    fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
    expect(onWorkflowAction).toHaveBeenCalledWith('CNT-001', 'submit')
  })

  it('shows conflict alert and submits a resolution audit note', () => {
    const onResolveConflict = vi.fn()
    render(<ContentManagementPage drafts={[]} conflicts={[conflict]} onResolveConflict={onResolveConflict} />)

    expect(screen.getByRole('heading', { name: 'Cảnh báo conflict (1)' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Resolve conflict' }))
    fireEvent.change(screen.getByLabelText('Ghi chú xử lý CON-001'), { target: { value: 'Đã xác minh bảng giá mới.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Lưu resolution audit' }))
    expect(onResolveConflict).toHaveBeenCalledWith('CON-001', 'Đã xác minh bảng giá mới.')
  })

  it('does not allow resolution submission without an audit note', () => {
    render(<ContentManagementPage drafts={[]} conflicts={[conflict]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Resolve conflict' }))
    expect(screen.getByRole('button', { name: 'Lưu resolution audit' })).toBeDisabled()
  })

  it('renders the no-conflict state', () => {
    render(<ContentManagementPage drafts={[]} conflicts={[]} />)
    expect(screen.getByText('Không có conflict nội dung.')).toBeInTheDocument()
  })
})
// === TASK:WP-505:END ===
