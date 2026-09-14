// 认证状态管理：token 存 localStorage，全站 fetch 自动带 Bearer。
// 后端 pay-account-service 平移契约：业务失败 HTTP 200 + {value: msg}。

const TOKEN_KEY = "comic_token";
const USER_KEY = "comic_user";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export function isLoggedIn() {
  return !!getToken();
}

export function saveLoginState(response, phone) {
  // response: { token, name, peopleId, status }
  const token = (response.token || "").replace(/^Bearer\s+/, "");
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(
    USER_KEY,
    JSON.stringify({
      peopleId: response.peopleId,
      name: response.name,
      phone: phone || "",
      status: response.status,
    })
  );
}

export function clearLoginState() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function logout() {
  clearLoginState();
  // 跳登录页，带上回跳目标由路由守卫处理
  window.location.href = "/login";
}
