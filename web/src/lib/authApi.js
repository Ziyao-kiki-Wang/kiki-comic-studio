// 账户域 API（/api/auth/*、/api/user/*）。
// 契约：业务失败 HTTP 200 + {value: msg}；成功见各函数注释。
//
// production 下 API_BASE 留空 → 请求走同源，由 nginx 把 /api/* 反代到后端 8002。
// 本地开发时 VITE_API_BASE 指向后端（默认 http://127.0.0.1:8000）。
const API_BASE =
  import.meta.env.VITE_API_BASE ??
  (import.meta.env.PROD ? "" : "http://127.0.0.1:8000");

import { getToken } from "./auth";

async function post(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(20000), // 20s 超时，兜底慢网络
  });
  return res.json();
}

async function get(path) {
  const token = getToken();
  const res = await fetch(API_BASE + path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal: AbortSignal.timeout(20000),
  });
  return res.json();
}

/** 图形验证码 → { success, data: { captcha_token, image_base64, expires_in } } */
export function getCaptcha() {
  return get("/api/auth/captcha");
}

/**
 * 密码登录 → 成功 { token, name, peopleId, status }；失败 { value: msg }
 */
export function loginByPassword(payload) {
  return post("/api/auth/login", payload);
}

/** 注册 → { success: true, value: "操作成功" }；失败 { value: msg } */
export function registerUser(payload) {
  return post("/api/auth/register", payload);
}

/** 当前用户详情 → { success, data: { peopleId, peopleName, points, ... } } */
export function getUserDetail() {
  return get("/api/user/detail");
}

/** 我的邀请码 → { success, data: [{invitationCode, invalid, ...}] } */
export function getMyInvitationCodes() {
  return get("/api/user/invitations");
}

/** 积分余额 → { success, data: { points } } */
export async function getPoints() {
  return get("/api/user/points");
}

/** 积分流水 → { success, data: { list, currPage, totalPage, totalRow } } */
export function getPointsHistory(pageNumber = 1, pageSize = 10) {
  const token = getToken();
  return fetch(API_BASE + "/api/user/points/history", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ pageNumber, pageSize }),
  }).then((r) => r.json());
}
