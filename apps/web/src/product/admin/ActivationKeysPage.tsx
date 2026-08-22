import { Copy, FunnelSimple, Key, MagnifyingGlass, Plus, Prohibit, X } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface ActivationKeyRecord {
  id: string
  key_hint: string
  display_key: string | null
  status: 'unused' | 'used' | 'revoked' | 'expired'
  created_at: string
  expires_at: string
  bound_username: string | null
}

const STATUS_LABEL = {
  unused: '未使用',
  used: '已使用',
  revoked: '已吊销',
  expired: '已过期',
}

export function ActivationKeysPage() {
  const { session } = useAuth()
  const [keys, setKeys] = useState<ActivationKeyRecord[]>([])
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  const refresh = useCallback(async () => {
    if (!session) return
    setKeys(await apiRequest<ActivationKeyRecord[]>('/admin/activation-keys', {}, session.token))
  }, [session])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const visibleKeys = keys.filter((key) => `${key.key_hint} ${key.bound_username ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()))

  async function createKey() {
    if (!session) return
    const record = await apiRequest<ActivationKeyRecord>('/admin/activation-keys', {
      method: 'POST',
      body: JSON.stringify({ valid_days: 30 }),
    }, session.token)
    setCreatedKey(record.display_key)
    await refresh()
  }

  async function revoke(id: string) {
    if (!session) return
    await apiRequest(`/admin/activation-keys/${id}/revoke`, { method: 'POST' }, session.token)
    await refresh()
  }

  return (
    <section className="admin-page">
      <div className="page-title-actions">
        <div><span className="eyebrow">用户邀请</span><h1>注册邀请码</h1><p className="page-lead">每个邀请码只能注册一个账号，使用后自动失效。</p></div>
        <button className="primary-action" type="button" onClick={() => void createKey()}><Plus size={19} />生成邀请码</button>
      </div>

      {createdKey ? (
        <div className="created-key-banner">
          <Key size={25} />
          <div><strong>新邀请码已生成</strong><code>{createdKey}</code><span>请立即复制并发送给受邀用户，关闭后不再完整显示。</span></div>
          <button type="button" onClick={() => navigator.clipboard.writeText(createdKey)}><Copy size={19} />复制</button>
          <button className="icon-button" type="button" onClick={() => setCreatedKey(null)} aria-label="关闭"><X size={19} /></button>
        </div>
      ) : null}

      <div className="table-toolbar"><div><strong>{keys.length} 个邀请码</strong><span>其中 {keys.filter((key) => key.status === 'unused').length} 个可用</span></div><div className="toolbar-actions"><label className="search-field"><MagnifyingGlass size={18} /><input placeholder="搜索邀请码或用户名" value={query} onChange={(event) => setQuery(event.target.value)} /></label><button className="secondary-action compact-action" type="button"><FunnelSimple size={18} />筛选</button></div></div>
      <div className="data-table">
        <div className="table-head"><span>邀请码</span><span>状态</span><span>创建时间</span><span>有效期至</span><span>注册用户</span><span>操作</span></div>
        {visibleKeys.map((key) => {
          const label = STATUS_LABEL[key.status]
          return (
            <div className="table-row" key={key.id}>
              <code>{key.key_hint}</code>
              <span><em className={`status-badge status-badge--${label}`}>{label}</em></span>
              <time>{formatDate(key.created_at)}</time><time>{formatDate(key.expires_at)}</time><span>{key.bound_username ?? '—'}</span>
              <span>{key.status === 'unused' ? <button className="table-action" type="button" onClick={() => void revoke(key.id)}><Prohibit size={17} />吊销</button> : '—'}</span>
            </div>
          )
        })}
        {visibleKeys.length === 0 ? <div className="table-empty-state"><MagnifyingGlass size={24} /><strong>没有匹配的邀请码</strong><span>可以生成一个新的邀请码</span></div> : null}
      </div>
      <div className="table-pagination"><span>显示 {visibleKeys.length} / {keys.length} 条</span><div><button type="button" disabled>上一页</button><b>1</b><button type="button" disabled>下一页</button></div></div>
    </section>
  )
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}
