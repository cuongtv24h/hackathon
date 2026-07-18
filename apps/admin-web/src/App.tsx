// === TASK:WP-500:START ===
import { useEffect, useState } from 'react'
import { AnalyticsAuditPage } from './features/analytics-audit/AnalyticsAuditPage'
import { ContentManagementPage } from './features/content-management/ContentManagementPage'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? ''

function App() {
  const [dashboard, setDashboard] = useState<any>(null)
  const [history, setHistory] = useState<any>(null)
  const [conflicts, setConflicts] = useState<any[]>([])
  const [drafts, setDrafts] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  async function load() {
    setLoading(true); setError(null)
    try {
      const [summary, historyResponse, conflictResponse, draftResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/v1/admin/dashboard`).then((response) => response.json()),
        fetch(`${apiBaseUrl}/v1/admin/history`).then((response) => response.json()),
        fetch(`${apiBaseUrl}/v1/admin/content/conflicts`).then((response) => response.json()),
        fetch(`${apiBaseUrl}/v1/admin/content/drafts`).then((response) => response.json()),
      ])
      setDashboard(summary); setHistory(historyResponse); setConflicts(conflictResponse.conflicts ?? []); setDrafts(draftResponse.drafts ?? [])
    } catch { setError('Không thể tải dashboard. Vui lòng thử lại.') } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  async function resolveConflict(conflictId: string, note: string) {
    await fetch(`${apiBaseUrl}/v1/admin/content/conflicts/${conflictId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ state: 'resolved', note, actor: 'demo-admin' }) })
    await load()
  }
  async function workflowAction(draftId: string, action: string) {
    const endpoint = action === 'submit' ? 'submit' : action === 'publish' ? 'publish' : 'review'
    const body = endpoint === 'review' ? { actor: 'demo-admin', approved: action === 'approve', rejection_reason: action === 'request_changes' ? 'Changes requested' : '' } : { actor: 'demo-admin' }
    const response = await fetch(`${apiBaseUrl}/v1/admin/content/drafts/${draftId}/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (!response.ok) throw new Error('workflow failed')
    await load()
  }
  if (loading) return <p role="status">Đang tải dashboard…</p>
  if (error) return <main><p role="alert">{error}</p><button onClick={() => void load()}>Thử lại</button></main>
  const normalizedConflicts = conflicts.map((item) => ({ ...item, due_at: item.due_at, resolution_audit: item.resolved_at ? { resolved_by: item.resolved_by, resolved_at: item.resolved_at, resolution_note: item.resolution_note } : undefined }))
  const normalizedDrafts = drafts.map((item) => ({ content_id: item.draft_id, title: item.source_id || item.draft_id, domain: item.domain, approval_state: item.status === 'submitted' ? 'in_review' : item.status, version: item.version, updated_at: item.updated_at }))
  return <>
    <ContentManagementPage drafts={normalizedDrafts} conflicts={normalizedConflicts} onWorkflowAction={(id, action) => void workflowAction(id, action)} onResolveConflict={(id, note) => void resolveConflict(id, note)} />
    <AnalyticsAuditPage summary={{ total_conversations: dashboard.total_conversations, emergency_events: dashboard.emergency_events, unresolved_conflicts: dashboard.unresolved_conflicts, average_response_ms: 0, top_intents: dashboard.top_intents, channels: [], pii_redaction_failures: 0, generated_at: dashboard.generated_at }} history={{ items: (history.items ?? []).map((item: any) => ({ message_id: item.message_id, session_id: item.session_id, channel: item.channel, role: item.role, content_preview: item.content_redacted, intent: item.intent, tools_called: item.tools_called ?? [], emergency_triggered: item.emergency_triggered, created_at: item.created_at })), page: { page: 1, page_size: 50, total_items: history.total, total_pages: 1 } }} filters={{}} />
  </>
}

export default App
// === TASK:WP-500:END ===
