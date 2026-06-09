/**
 * AuthContext — 全局登录态管理.
 *
 * 来源: feihe 正式系统 `traveldev.feiheair.com/api/sys/logonV2` 接口
 * 响应头 `token: <value>`,前端拿到后存到 sessionStorage,后续请求自动塞
 * 到 `X-MCP-Token` (优先) / `Authorization: Bearer` (兜底) 头.
 *
 * 调用方注入 (Hub → opencode → feihe-travel MCP) 全链路透传:
 *   browser   →  http.ts interceptor  → Hub  _extract_mcp_token
 *   Hub bridge.chat(mcp_token=...)   →  opencode_chat 写 FH env
 *   opencode serve MCP client       →  feihe-travel HTTP header token:
 *
 * 持久化策略:
 *   - sessionStorage  (默认): 关闭 tab 即清, 适合内部工具
 *   - localStorage    (可选): 记住登录态, 通过 `persist=true` 切换
 *
 * 暴露 API:
 *   useAuth(): { token, loginInfo, isAuthenticated, login(), logout() }
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { ApiError, http, registerTokenGetter } from '../services/http';

const STORAGE_KEY_TOKEN = 'feihe.token';
const STORAGE_KEY_INFO = 'feihe.login_info';
const PERSIST_FLAG_KEY = 'feihe.persist_login';

export interface LoginInfo {
  userCode?: string;
  companyCode?: string;
  /** ISO 时间, 用于显示 "X 分钟前登录" */
  loggedInAt?: string;
  /** 原始响应里能拿到的非敏感字段 (e.g. userName) */
  displayName?: string;
}

export interface LoginRequest {
  /** 用户名, e.g. "013" */
  userCode: string;
  /** 公司代号, e.g. "10043" */
  companyCode: string;
  /** 原始明文密码 (仅在登录接口前用一次, 不持久化) */
  password: string;
  /** 可选图形验证码 (首次登录或风控触发时由后端要求) */
  captchaId?: string;
  captcha?: string;
  /** 记住登录态, 写 localStorage 而不是 sessionStorage */
  persist?: boolean;
}

export interface AuthState {
  /** feihe 后端 session token (response header `token`) */
  token: string | null;
  /** 登录返回的辅助信息 (不含敏感字段) */
  loginInfo: LoginInfo | null;
  /** 是否已登录 (token 非空) */
  isAuthenticated: boolean;
  /** 登录中 (loading 态) */
  isLoggingIn: boolean;
  /** 上次错误 (登录失败时显示) */
  error: string | null;
  /**
   * 上次登录失败是否需要刷新验证码.
   * LoginPage 看到 true → 自动 loadCaptcha().
   * 由 AuthContext 在 login 失败时, 检测 e.needsCaptcha 后设置.
   * LoginPage 在拿到 captcha 串后调用 clearNeedsCaptcha() 复位.
   */
  needsCaptcha: boolean;
}

export interface AuthApi extends AuthState {
  /**
   * 调用 feihe 登录接口, 成功则写入 token + loginInfo 并持久化.
   * 不抛异常, 失败时把错误写到 `error` 字段供 UI 展示.
   */
  login: (req: LoginRequest) => Promise<boolean>;
  /** 清空 token + loginInfo */
  logout: () => void;
  /** UI 主动清掉错误条 */
  clearError: () => void;
}

const AuthContext = createContext<AuthApi | null>(null);

// ---------------------------------------------------------------------------
// 存储抽象
// ---------------------------------------------------------------------------

function pickStorage(persist: boolean): Storage {
  if (typeof window === 'undefined') return sessionStorage;
  return persist ? window.localStorage : window.sessionStorage;
}

function readToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return (
      window.sessionStorage.getItem(STORAGE_KEY_TOKEN) ??
      window.localStorage.getItem(STORAGE_KEY_TOKEN) ??
      ''
    );
  } catch {
    return '';
  }
}

function readLoginInfo(): LoginInfo | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw =
      window.sessionStorage.getItem(STORAGE_KEY_INFO) ??
      window.localStorage.getItem(STORAGE_KEY_INFO);
    if (!raw) return null;
    return JSON.parse(raw) as LoginInfo;
  } catch {
    return null;
  }
}

function writeAuth(token: string, info: LoginInfo, persist: boolean): void {
  if (typeof window === 'undefined') return;
  const target = pickStorage(persist);
  try {
    target.setItem(STORAGE_KEY_TOKEN, token);
    target.setItem(STORAGE_KEY_INFO, JSON.stringify(info));
    // persist 模式同步写一份到 localStorage, 避免双 store 不一致
    if (persist) {
      window.localStorage.setItem(PERSIST_FLAG_KEY, '1');
    } else {
      window.localStorage.removeItem(PERSIST_FLAG_KEY);
    }
  } catch {
    // ignore quota / privacy 模式
  }
}

function clearAuth(): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY_TOKEN);
    window.sessionStorage.removeItem(STORAGE_KEY_INFO);
    window.localStorage.removeItem(STORAGE_KEY_TOKEN);
    window.localStorage.removeItem(STORAGE_KEY_INFO);
    window.localStorage.removeItem(PERSIST_FLAG_KEY);
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// 登录接口调用 (走 Hub 代理, 不直连 feihe 域名)
// ---------------------------------------------------------------------------

// Hub auth endpoints. The shared HTTP client adds config.apiBaseUrl:
// dev/proxy uses /api/auth/*, while direct Hub deployments use /auth/*.
//   - Hub 代为调 https://traveldev.feiheair.com/api/sys/logonV2 (避开 CORS)
//   - 密码 / 凭证只在 Hub→feihe 这一次 HTTPS 走, 不进前端 console
//   - 成功时 Hub 返 { success, token, login_info }, 前端拿 token 写本地
const HUB_LOGON_PATH = '/auth/logon';
const HUB_CAPTCHA_PATH = '/auth/captcha';

interface HubLogonSuccess {
  success: true;
  token: string;
  login_info: LoginInfo;
}

interface HubLogonError {
  success: false;
  code: string;
  error: string;
  /** feihe 后端说要验证码但前端没带 → 重拉 captcha */
  needs_captcha?: boolean;
}

interface HubCaptchaResponse {
  captchaId: string;
  imageDataUrl: string;
}

async function callLogonViaHub(req: LoginRequest): Promise<{
  token: string;
  info: LoginInfo;
}> {
  try {
    const parsed = await http.post<HubLogonSuccess>(
      HUB_LOGON_PATH,
      {
        company_code: req.companyCode,
        user_code: req.userCode,
        password: req.password,
        captcha_id: req.captchaId ?? null,
        captcha: req.captcha ?? null,
      },
      { skipAuth: true },
    );
    return {
      token: parsed.token,
      info: parsed.login_info,
    };
  } catch (e) {
    const err = e instanceof ApiError ? (e.body as HubLogonError | null) : null;
    const message =
      err && err.success === false
        ? err.error
        : e instanceof Error
          ? e.message
          : '登录失败';
    if (err?.needs_captcha) {
      const e = new Error(message) as Error & { needsCaptcha?: boolean };
      e.needsCaptcha = true;
      throw e;
    }
    throw new Error(message);
  }
}

/**
 * 拉图形验证码 — 走 Hub 登录代理, 由配置决定是否带 /api 前缀.
 * 拿到 captchaId + imageDataUrl 后, 下次调 logon 时带回 captchaId + 用户输入的 captcha 串.
 */
export async function fetchGraphicsCaptcha(): Promise<{
  captchaId: string;
  /** base64 dataURL, 直接塞 <img src> */
  imageDataUrl: string;
}> {
  const j = await http.get<HubCaptchaResponse>(HUB_CAPTCHA_PATH, {
    skipAuth: true,
  });
  if (!j.captchaId || !j.imageDataUrl) {
    throw new Error('Hub 验证码响应缺少 captchaId/imageDataUrl');
  }
  return j;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps): JSX.Element {
  const [token, setToken] = useState<string>(() => readToken());
  const [loginInfo, setLoginInfo] = useState<LoginInfo | null>(() => readLoginInfo());
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsCaptcha, setNeedsCaptcha] = useState(false);

  // 跨 tab 同步: 监听 storage 事件, 一个 tab 登出 / 登录, 其它 tab 跟着更新
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY_TOKEN || e.key === STORAGE_KEY_INFO) {
        setToken(readToken());
        setLoginInfo(readLoginInfo());
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  // 把"读 token"注册进 http.ts — 所有 request 自动塞 X-MCP-Token 头.
  // 卸载时 unregister, 避免 HMR / 重复 Provider 时旧 getter 残留.
  useEffect(() => {
    registerTokenGetter(() => token || readToken() || null);
    return () => registerTokenGetter(null);
  }, [token]);

  const login = useCallback(async (req: LoginRequest): Promise<boolean> => {
    setIsLoggingIn(true);
    setError(null);
    setNeedsCaptcha(false);
    try {
      const { token: t, info } = await callLogonViaHub(req);
      writeAuth(t, info, !!req.persist);
      setToken(t);
      setLoginInfo(info);
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : '登录失败';
      setError(msg);
      // Hub 显式给的 needsCaptcha flag, 优先用
      const flag = (e as Error & { needsCaptcha?: boolean })?.needsCaptcha;
      if (flag) {
        setNeedsCaptcha(true);
      } else if (typeof msg === 'string' && /验证码|captcha/i.test(msg)) {
        // 兜底: Hub 没返 flag 但消息含验证码相关
        setNeedsCaptcha(true);
      }
      return false;
    } finally {
      setIsLoggingIn(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setToken('');
    setLoginInfo(null);
    setError(null);
    setNeedsCaptcha(false);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
    setNeedsCaptcha(false);
  }, []);

  const value = useMemo<AuthApi>(
    () => ({
      token,
      loginInfo,
      isAuthenticated: token.length > 0,
      isLoggingIn,
      error,
      needsCaptcha,
      login,
      logout,
      clearError,
    }),
    [token, loginInfo, isLoggingIn, error, needsCaptcha, login, logout, clearError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
