/**
 * LoginPage — 全屏登录页.
 *
 * 何时显示: AuthContext.isAuthenticated === false 时, App 整树前面挡这一页.
 * 提交: 调 feihe 正式系统 /api/sys/logonV2, 拿 response header `token`.
 * 成功后: token 写 session/localStorage, AuthContext.isAuthenticated → true.
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  fetchGraphicsCaptcha,
  useAuth,
  type LoginRequest,
} from '../../contexts/AuthContext';
import { Button } from '../common/Button';
import { Input } from '../common/Input';
import './LoginPage.css';

interface LoginFormState {
  companyCode: string;
  userCode: string;
  password: string;
  captchaId: string;
  captcha: string;
  persist: boolean;
}

const DEFAULT_FORM: LoginFormState = {
  companyCode: '10043',
  userCode: '013',
  password: '',
  captchaId: '',
  captcha: '',
  persist: false,
};

export function LoginPage(): JSX.Element {
  const auth = useAuth();
  const [form, setForm] = useState<LoginFormState>(DEFAULT_FORM);
  const [captchaImg, setCaptchaImg] = useState<string | null>(null);
  const [captchaLoading, setCaptchaLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const loadCaptcha = useCallback(async () => {
    setCaptchaLoading(true);
    try {
      const { captchaId, imageDataUrl } = await fetchGraphicsCaptcha();
      setCaptchaImg(imageDataUrl);
      setForm((f) => ({ ...f, captchaId, captcha: '' }));
    } catch {
      // 验证码可选, 加载失败不阻塞登录 (后端可能没要求)
      setCaptchaImg(null);
      setForm((f) => ({ ...f, captchaId: '', captcha: '' }));
    } finally {
      setCaptchaLoading(false);
    }
  }, []);

  // 进入页面主动拉一次验证码
  useEffect(() => {
    loadCaptcha();
  }, [loadCaptcha]);

  const update = useCallback(<K extends keyof LoginFormState>(
    key: K,
    value: LoginFormState[K],
  ) => {
    setForm((f) => ({ ...f, [key]: value }));
  }, []);

  const onSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (!form.userCode.trim() || !form.companyCode.trim() || !form.password) {
        auth.clearError();
        return;
      }
      const req: LoginRequest = {
        companyCode: form.companyCode.trim(),
        userCode: form.userCode.trim(),
        password: form.password,
        captchaId: form.captchaId || undefined,
        captcha: form.captcha || undefined,
        persist: form.persist,
      };
      const ok = await auth.login(req);
      if (ok) {
        // 成功后清掉密码 (不要留 memory)
        setForm((f) => ({ ...f, password: '' }));
      } else if (auth.needsCaptcha) {
        // Hub 显式提示要验证码, 重拉一次
        loadCaptcha();
      }
    },
    [form, auth, loadCaptcha],
  );

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={onSubmit} autoComplete="off">
        <h1 className="login-title">OpenAgent</h1>
        <p className="login-subtitle">登录正式系统后即可使用</p>

        <div className="login-fields">
          <Input
            label="公司代号"
            value={form.companyCode}
            onChange={(e) => update('companyCode', e.target.value)}
            placeholder="10043"
            autoComplete="off"
            required
          />
          <Input
            label="用户名"
            value={form.userCode}
            onChange={(e) => update('userCode', e.target.value)}
            placeholder="013"
            autoComplete="username"
            required
          />
          <Input
            label="密码"
            type={showPassword ? 'text' : 'password'}
            value={form.password}
            onChange={(e) => update('password', e.target.value)}
            placeholder="请输入密码"
            autoComplete="current-password"
            required
            suffixIcon={
              <button
                type="button"
                className="login-eye"
                onClick={() => setShowPassword((s) => !s)}
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
                tabIndex={-1}
              >
                {showPassword ? '🙈' : '👁'}
              </button>
            }
          />
          {captchaImg && (
            <div className="login-captcha-row">
              <Input
                label="图形验证码"
                value={form.captcha}
                onChange={(e) => update('captcha', e.target.value)}
                placeholder="请输入验证码"
                className="login-captcha-input"
                autoComplete="off"
              />
              <button
                type="button"
                className="login-captcha-img-btn"
                onClick={loadCaptcha}
                disabled={captchaLoading}
                title="点击刷新"
              >
                {captchaLoading ? (
                  <span className="login-captcha-loading">…</span>
                ) : (
                  <img src={captchaImg} alt="captcha" />
                )}
              </button>
            </div>
          )}

          <label className="login-persist">
            <input
              type="checkbox"
              checked={form.persist}
              onChange={(e) => update('persist', e.target.checked)}
            />
            <span>记住登录态 (7 天)</span>
          </label>
        </div>

        {auth.error && (
          <div className="login-error" role="alert">
            {auth.error}
            <button
              type="button"
              className="login-error-close"
              onClick={auth.clearError}
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        )}

        <Button
          type="submit"
          variant="primary"
          size="large"
          loading={auth.isLoggingIn}
          disabled={
            auth.isLoggingIn ||
            !form.userCode.trim() ||
            !form.companyCode.trim() ||
            !form.password
          }
        >
          登录
        </Button>

        <p className="login-hint">
          登录请求由 <code>Hub 登录代理</code> 处理, 不直连飞鹤域名.
          <br />
          拿到 <code>token</code> 后, 后续请求自动注入
          <code> X-MCP-Token </code> 头, 一路透传到 opencode → 飞鹤 MCP.
        </p>
      </form>
    </div>
  );
}
