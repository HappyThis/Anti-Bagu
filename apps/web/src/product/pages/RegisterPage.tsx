import { ArrowRight, CheckCircle, Key, ShieldCheck, UserCircle } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../AuthContext'

export function RegisterPage() {
  const navigate = useNavigate()
  const { register } = useAuth()
  const [loading, setLoading] = useState(false)
  const [activationKey, setActivationKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await register(activationKey, username, password)
      navigate('/login', { replace: true })
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-brand-panel auth-brand-panel--register">
        <Link className="auth-brand" to="/">Anti-Bagu</Link>
        <div>
          <span>受邀注册</span>
          <h1>一个激活密钥，只绑定一个用户。</h1>
          <p>注册成功后密钥立即作废，你的任务、音频和模型 Key 只属于当前账户。</p>
          <div className="auth-benefits">
            <span><Key size={20} weight="duotone" /><b>一次性密钥验证身份</b></span>
            <span><UserCircle size={20} weight="duotone" /><b>只需用户名即可注册</b></span>
            <span><ShieldCheck size={20} weight="fill" /><b>平台不收集邮箱和手机号</b></span>
          </div>
        </div>
        <small className="auth-security-note"><CheckCircle size={16} weight="fill" />密钥消费后立即失效</small>
      </section>
      <section className="auth-form-panel">
        <form className="auth-form" onSubmit={submit}>
          <span className="auth-icon"><Key size={25} /></span>
          <h2>创建账户</h2>
          <p>填写管理员提供的一次性激活密钥。</p>
          <label><span>激活密钥</span><input required autoComplete="one-time-code" placeholder="AB-XXXX-XXXX-XXXX" value={activationKey} onChange={(event) => setActivationKey(event.target.value.toUpperCase())} /></label>
          <label><span>用户名</span><input required autoComplete="username" minLength={3} maxLength={32} pattern="[A-Za-z0-9._-]+" placeholder="3–32 位字母、数字或 . _ -" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label><span>密码</span><input required autoComplete="new-password" minLength={8} type="password" placeholder="至少 8 位字符" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {error ? <div className="form-error" role="alert">{error}</div> : null}
          <button className="primary-action" type="submit" disabled={loading}>
            {loading ? '正在验证…' : '验证并注册'}<ArrowRight size={19} />
          </button>
          <small>已经注册？<Link to="/login">返回登录</Link></small>
          <p className="auth-terms">当前仅向获得管理员邀请的内测用户开放。</p>
        </form>
      </section>
    </main>
  )
}
