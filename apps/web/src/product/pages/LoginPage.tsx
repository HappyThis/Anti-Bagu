import { ArrowRight, CheckCircle, DeviceMobile, LockKey, Waveform } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../AuthContext'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()
  const [loading, setLoading] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const user = await login(username, password)
      const requestedPath = (location.state as { from?: string } | null)?.from
      navigate(requestedPath ?? (user.role === 'admin' ? '/admin' : '/tasks'), { replace: true })
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-brand-panel">
        <Link className="auth-brand" to="/">Anti-Bagu</Link>
        <div>
          <span>云端面试工作台</span>
          <h1>听清面试问题，及时看到回答提示。</h1>
          <p>创建面试、完成准备，然后在电脑或手机上查看建议回答。</p>
          <div className="auth-benefits">
            <span><Waveform size={20} weight="duotone" /><b>自动识别面试问题</b></span>
            <span><DeviceMobile size={20} weight="duotone" /><b>建议回答同步到手机</b></span>
            <span><CheckCircle size={20} weight="fill" /><b>面试结束后随时回顾</b></span>
          </div>
        </div>
        <small className="auth-security-note">你的服务凭据只保存在自己的电脑中</small>
      </section>
      <section className="auth-form-panel">
        <form className="auth-form" onSubmit={submit}>
          <span className="auth-icon"><LockKey size={25} /></span>
          <h2>登录 Anti-Bagu</h2>
          <p>继续准备面试或查看历史记录。</p>
          <label><span>用户名</span><input required autoComplete="username" placeholder="输入用户名" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label><span>密码</span><input required autoComplete="current-password" type="password" placeholder="输入密码" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {error ? <div className="form-error" role="alert">{error}</div> : null}
          <button className="primary-action" type="submit" disabled={loading}>
            {loading ? '登录中…' : '登录'}<ArrowRight size={19} />
          </button>
          <small>还没有账号？<Link to="/register">使用邀请码注册</Link></small>
          <p className="auth-terms">登录即表示你同意内测期间的数据处理规则。</p>
        </form>
      </section>
    </main>
  )
}
