import { useEffect, useState } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { getCaptcha, loginByPassword } from "../../lib/authApi";
import { saveLoginState } from "../../lib/auth";
import "./auth.css";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ phone: "", password: "", captcha: "" });
  const [captcha, setCaptcha] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const from = location.state?.from || "/";

  async function refreshCaptcha() {
    try {
      const res = await getCaptcha();
      if (res.success) setCaptcha(res.data);
    } catch {
      setError("验证码加载失败，请刷新重试");
    }
  }

  useEffect(() => {
    refreshCaptcha();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await loginByPassword({
        peoplePhone: form.phone.trim(),
        peoplePassword: form.password,
        captcha_token: captcha?.captcha_token || "",
        captcha_input: form.captcha.trim(),
      });
      if (res.value) {
        setError(res.value);
        refreshCaptcha(); // 验证码一次性，失败要换新的
        setForm((f) => ({ ...f, captcha: "" }));
        return;
      }
      saveLoginState(res, form.phone.trim());
      navigate(from, { replace: true });
    } catch {
      setError("网络错误，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">登录</h1>
        <p className="auth-subtitle">AI 漫画工坊</p>
        <form onSubmit={handleSubmit} className="auth-form">
          <label>
            手机号
            <input
              type="tel"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="请输入手机号"
              autoComplete="tel"
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="请输入密码"
              autoComplete="current-password"
              required
            />
          </label>
          <label>
            验证码
            <div className="captcha-row">
              <input
                type="text"
                value={form.captcha}
                onChange={(e) => setForm({ ...form, captcha: e.target.value })}
                placeholder="右图字符"
                maxLength={4}
                required
              />
              {captcha ? (
                <img
                  className="captcha-img"
                  src={`data:image/png;base64,${captcha.image_base64}`}
                  alt="验证码"
                  onClick={refreshCaptcha}
                  title="点击刷新"
                />
              ) : (
                <button type="button" className="captcha-loading" onClick={refreshCaptcha}>
                  刷新
                </button>
              )}
            </div>
          </label>
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? "登录中…" : "登录"}
          </button>
        </form>
        <div className="auth-footer">
          还没有账号？<Link to="/register">邀请码注册</Link>
        </div>
      </div>
    </div>
  );
}
