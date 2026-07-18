// === TASK:WP-505:START ===
import { useMemo, useState } from 'react'

export type ContentApprovalState = 'draft' | 'in_review' | 'approved' | 'published' | 'changes_requested'
export type ContentConflictState = 'open' | 'investigating' | 'resolved' | 'dismissed'
export type ContentWorkflowAction = 'submit' | 'approve' | 'request_changes' | 'publish'

export interface ContentDraft {
  content_id: string
  title: string
  domain: string
  approval_state: ContentApprovalState
  version: string
  updated_at: string
}

export interface ContentConflict {
  conflict_id: string
  source_chunk_ids: string[]
  conflicting_fields: string[]
  due_at: string
  state: ContentConflictState
  resolution_audit?: {
    resolved_by: string
    resolved_at: string
    resolution_note: string
  }
}

export interface ContentManagementPageProps {
  drafts: ContentDraft[]
  conflicts: ContentConflict[]
  onWorkflowAction?: (contentId: string, action: ContentWorkflowAction) => void
  onResolveConflict?: (conflictId: string, resolutionNote: string) => void
}

function availableActions(state: ContentApprovalState): ContentWorkflowAction[] {
  if (state === 'draft' || state === 'changes_requested') return ['submit']
  if (state === 'in_review') return ['approve', 'request_changes']
  if (state === 'approved') return ['publish']
  return []
}

function actionLabel(action: ContentWorkflowAction): string {
  return {
    submit: 'Gửi duyệt',
    approve: 'Phê duyệt',
    request_changes: 'Yêu cầu chỉnh sửa',
    publish: 'Xuất bản',
  }[action]
}

export function ContentManagementPage({
  drafts,
  conflicts,
  onWorkflowAction,
  onResolveConflict,
}: ContentManagementPageProps) {
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null)
  const [resolutionNote, setResolutionNote] = useState('')
  const openConflicts = useMemo(
    () => conflicts.filter((conflict) => conflict.state === 'open' || conflict.state === 'investigating'),
    [conflicts],
  )
  const selectedConflict = conflicts.find((conflict) => conflict.conflict_id === selectedConflictId)

  function submitResolution() {
    if (!selectedConflictId || !resolutionNote.trim()) return
    onResolveConflict?.(selectedConflictId, resolutionNote.trim())
    setResolutionNote('')
    setSelectedConflictId(null)
  }

  return (
    <main aria-label="Content management dashboard">
      <header>
        <h1>Quản lý nội dung</h1>
        <p>Tài khoản demo có toàn quyền xử lý workflow nội dung cho pilot.</p>
      </header>

      <section aria-labelledby="content-workflow-heading">
        <h2 id="content-workflow-heading">Content workflow</h2>
        <table>
          <thead>
            <tr><th>Nội dung</th><th>Domain</th><th>Phiên bản</th><th>Trạng thái</th><th>Thao tác</th></tr>
          </thead>
          <tbody>
            {drafts.map((draft) => (
              <tr key={draft.content_id}>
                <td>{draft.title}</td>
                <td>{draft.domain}</td>
                <td>{draft.version}</td>
                <td>{draft.approval_state}</td>
                <td>
                  {availableActions(draft.approval_state).map((action) => (
                    <button key={action} type="button" onClick={() => onWorkflowAction?.(draft.content_id, action)}>
                      {actionLabel(action)}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="content-conflicts-heading">
        <h2 id="content-conflicts-heading">Cảnh báo conflict ({openConflicts.length})</h2>
        {conflicts.length === 0 ? <p>Không có conflict nội dung.</p> : null}
        <ul>
          {conflicts.map((conflict) => (
            <li key={conflict.conflict_id}>
              <strong>{conflict.conflict_id}</strong>: {conflict.conflicting_fields.join(', ')} — {conflict.state}
              <p>Hạn xử lý: {conflict.due_at}</p>
              {conflict.resolution_audit ? (
                <p>Đã xử lý bởi {conflict.resolution_audit.resolved_by}: {conflict.resolution_audit.resolution_note}</p>
              ) : null}
              {(conflict.state === 'open' || conflict.state === 'investigating') ? (
                <button type="button" onClick={() => setSelectedConflictId(conflict.conflict_id)}>Resolve conflict</button>
              ) : null}
            </li>
          ))}
        </ul>
        {selectedConflict ? (
          <form onSubmit={(event) => { event.preventDefault(); submitResolution() }} aria-label="Conflict resolution form">
            <label htmlFor="resolution-note">Ghi chú xử lý {selectedConflict.conflict_id}</label>
            <textarea id="resolution-note" value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} />
            <button type="submit" disabled={!resolutionNote.trim()}>Lưu resolution audit</button>
          </form>
        ) : null}
      </section>
    </main>
  )
}
// === TASK:WP-505:END ===
