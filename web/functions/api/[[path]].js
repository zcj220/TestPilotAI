/**
 * Cloudflare Pages Function — API 反向代理
 *
 * 将所有 /api/* 请求透明代理到后端服务器，
 * 解决 Cloudflare Pages 静态托管无法访问后端 API 的问题。
 */

const BACKEND = 'https://testpilot.xinzaoai.com';

export async function onRequest(context) {
  const url = new URL(context.request.url);
  const target = BACKEND + url.pathname + url.search;

  // 透传原始请求（方法、Headers、Body）
  const req = new Request(target, {
    method: context.request.method,
    headers: context.request.headers,
    body: context.request.body,
    redirect: 'follow',
  });

  const res = await fetch(req);

  // 透传响应，追加 CORS 头
  const headers = new Headers(res.headers);
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  headers.set('Access-Control-Allow-Headers', 'Content-Type,Authorization');

  if (context.request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers });
  }

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
}
