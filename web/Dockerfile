# TestPilot AI — Web 前端镜像
#
# 多阶段构建：
#   Stage 1: Node 构建 React 应用
#   Stage 2: Nginx 提供静态文件
#
# 构建：docker build -t testpilot/web ./web
# 运行：docker run -p 3000:80 testpilot/web

# ── Stage 1: 构建 ────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: Nginx 运行 ──────────────────────────
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
