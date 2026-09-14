import { useEffect, useState } from "react";
import { getUserDetail, getMyInvitationCodes, getPointsHistory } from "../../lib/authApi";
import { getUser, logout } from "../../lib/auth";
import "./auth.css";

export default function Profile() {
  const [detail, setDetail] = useState(null);
  const [codes, setCodes] = useState([]);
  const [history, setHistory] = useState(null);
  const user = getUser();

  useEffect(() => {
    getUserDetail().then((r) => r.success && setDetail(r.data)).catch(() => {});
    getMyInvitationCodes().then((r) => r.success && setCodes(r.data)).catch(() => {});
    getPointsHistory(1, 20).then((r) => r.success && setHistory(r.data)).catch(() => {});
  }, []);

  const usable = codes.filter((c) => c.invalid);

  return (
    <div className="auth-page" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      <div className="auth-card" style={{ maxWidth: 520 }}>
        <h1 className="auth-title">个人中心</h1>

        <section className="profile-section">
          <h3>账号信息</h3>
          <div className="profile-row"><span>昵称</span><b>{detail?.peopleName || user?.name}</b></div>
          <div className="profile-row"><span>手机号</span><b>{detail?.peoplePhone || user?.phone}</b></div>
          <div className="profile-row"><span>剩余积分</span><b className="points-badge">{detail?.points ?? "…"} 分</b></div>
          <button className="auth-submit" style={{ marginTop: 12, background: "#8a8175" }} onClick={logout}>
            退出登录
          </button>
        </section>

        <section className="profile-section">
          <h3>我的邀请码</h3>
          <p className="profile-hint">把可用邀请码分享给朋友，对方注册即自动发放奖励。</p>
          {usable.length === 0 && <p className="profile-hint">暂无可用邀请码</p>}
          {usable.map((c) => (
            <div key={c.id} className="invite-code-row">
              <code>{c.invitationCode}</code>
              <button
                onClick={() => { navigator.clipboard?.writeText(c.invitationCode); }}
              >复制</button>
            </div>
          ))}
        </section>

        <section className="profile-section">
          <h3>积分记录</h3>
          {!history?.list?.length && <p className="profile-hint">暂无记录</p>}
          <table className="points-table">
            <tbody>
              {history?.list?.map((r, i) => (
                <tr key={i}>
                  <td>{r.purpose}</td>
                  <td className={r.change >= 0 ? "pos" : "neg"}>
                    {r.change >= 0 ? "+" : ""}{r.change}
                  </td>
                  <td>余额 {r.balance}</td>
                  <td className="time">{r.use_time?.slice(0, 16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
