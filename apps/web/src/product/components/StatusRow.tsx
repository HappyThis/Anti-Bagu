import { CellSignalFull, CheckCircle, WarningCircle, type Icon } from '@phosphor-icons/react'

interface StatusRowProps {
  icon: Icon
  label: string
  detail: string
  latency: string
  checking?: boolean
  ok?: boolean | null
}

export function StatusRow({
  icon: StatusIcon,
  label,
  detail,
  latency,
  checking = false,
  ok = true,
}: StatusRowProps) {
  return (
    <div className={`status-row ${checking ? 'status-row--checking' : ''} ${ok === false ? 'status-row--failed' : ''}`}>
      <StatusIcon className="status-row-icon" size={28} weight="duotone" />
      <strong>{label}</strong>
      <span className="status-detail">{detail}</span>
      <CellSignalFull className="signal-icon" size={22} weight="fill" aria-hidden="true" />
      <span className="latency-label">延迟 <b>{checking ? '检测中' : latency}</b></span>
      <span className={`status-ok ${ok === false ? 'status-ok--failed' : ''}`}>
        {ok === false ? <WarningCircle size={18} weight="fill" /> : <CheckCircle size={18} weight="fill" />}
        {checking ? '检查中' : ok === false ? '未通过' : '正常'}
      </span>
    </div>
  )
}
