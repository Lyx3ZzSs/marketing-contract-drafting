FROM node:24-bookworm-slim
RUN npm install --global pnpm@11.25.0
WORKDIR /app
COPY package.json pnpm-lock.yaml .npmrc ./
RUN pnpm install --frozen-lockfile
COPY . .
CMD ["pnpm", "exec", "vite", "--host", "0.0.0.0", "--port", "5173"]
