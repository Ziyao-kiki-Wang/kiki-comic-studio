import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { getCaptcha, registerUser } from "../../lib/authApi";
import "./auth.css";

export default function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    phone: "",
    password: "",
    confirm: "",
    invitationCode: "",
    captcha: "",
  });
  const [captcha, setCaptcha] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
    if (form.password !== form.confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    try {
      const res = await registerUser({
        peopleName: form.name.trim(),
        peoplePhone: form.phone.trim(),
        peoplePassword: form.password,
        invitationCode: form.invitationCode.trim(),
        captcha_token: captcha?.captcha_token || "",
        captcha_input: form.captcha.trim(),
      });
      if (res.value && !res.success) {
        setError(res.value);
        refreshCaptcha();
        setForm((f) => ({ ...f, captcha: "" }));
        return;
      }
      // 注册成功 → 跳登录页
      navigate("/login", { state: { registered: true, phone: form.phone.trim() } });
    } catch {
      setError("网络错误，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">注册</h1>
        <p className="auth-subtitle">需要邀请码（内测中）</p>
        <form onSubmit={handleSubmit} className="auth-form">
          <label>
            昵称
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="怎么称呼你"
              required
            />
          </label>
          <label>
            手机号
            <input
              type="tel"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="11 位手机号"
              autoComplete="tel"
              required
            />
          </label>
          <label>
            邀请码
            <input
              type="text"
              value={form.invitationCode}
              onChange={(e) =>
                setForm({ ...form, invitationCode: e.target.value.toUpperCase() })
              }
              placeholder="6 位邀请码"
              maxLength={6}
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="8-18位，含大小写字母+数字"
              autoComplete="new-password"
              required
            />
          </label>
          <label>
            确认密码
            <input
              type="password"
              value={form.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })}
              placeholder="再输一遍"
              autoComplete="new-password"
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
            {loading ? "注册中…" : "注册"}
          </button>
        </form>
        <div className="auth-footer">
          已有账号？<Link to="/login">去登录</Link>
        </div>
      </div>
    </div>
  );
}
