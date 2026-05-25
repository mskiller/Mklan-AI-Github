FROM node:22-bookworm-slim AS deps

WORKDIR /workspace/frontend

COPY frontend/package.json ./

RUN npm install

FROM node:22-bookworm-slim AS builder

WORKDIR /workspace/frontend

ARG NEXT_PUBLIC_API_BASE_URL=/api
ARG INTERNAL_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV INTERNAL_API_BASE_URL=${INTERNAL_API_BASE_URL}

COPY --from=deps /workspace/frontend/node_modules ./node_modules
COPY frontend ./

RUN npm run build && mkdir -p /workspace/frontend/public

FROM node:22-bookworm-slim AS runner

ENV NODE_ENV=production

WORKDIR /workspace/frontend

COPY --from=builder /workspace/frontend/.next/standalone ./
COPY --from=builder /workspace/frontend/.next/static ./.next/static
COPY --from=builder /workspace/frontend/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
