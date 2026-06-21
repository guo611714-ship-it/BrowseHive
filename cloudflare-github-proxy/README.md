# Cloudflare Workers GitHub 文件加速服务

本项目用于搭建 GitHub 文件代理加速服务，可实现 API、Git Clone、Releases、Archive、Gist、Raw 文件等场景的加速访问。

## 功能特性

| 功能 | 说明 |
|------|------|
| API 加速 | GitHub API 请求加速 |
| Git Clone | 仓库克隆加速 |
| Releases | release 文件下载加速 |
| Archive | 仓库归档下载加速 |
| Gist | Gist 内容访问加速 |
| Raw 文件 | 原始文件下载加速 |

**注意**: 本项目不可加速 GitHub 主站点，仅限上述 API 和文件下载场景。

## 部署前准备

### 必要材料
- Cloudflare 账号: [dash.cloudflare.com](https://dash.cloudflare.com)
- 自有域名（推荐在域名注册商注册）
- Wrangler CLI（可选，用于本地开发）

### Cloudflare Workers 配额
- 免费计划: 每天 10 万次请求
- 请求限额按北京时间 8 点重置

## 部署步骤

### 第一步: 登录 Cloudflare 并创建 Worker

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com)
2. 进入 **Workers & Pages** 界面
3. 点击 **创建应用程序**
4. 选择 **创建 Worker**
5. 为 Worker 命名（如 `github-proxy`）

### 第二步: 部署代码

**方法 A: 在线部署**
1. 在 Worker 编辑器中粘贴 [src/index.js](src/index.js) 的内容
2. 点击 **保存并部署**

**方法 B: 使用 Wrangler CLI（推荐）**

```bash
# 安装 Wrangler
npm install -g wrangler

# 登录 Cloudflare
wrangler login

# 部署
wrangler deploy
```

### 第三步：配置自定义域名和路由（可选）

如果您想使用自己的域名加速：

1. **添加 DNS 解析记录**
   - 进入 Cloudflare Dashboard 的域名管理
   - 在 DNS 设置中添加记录：
     - 类型: A 或 CNAME
     - 名称: 自定义子域名（如 `gh`）
     - 目标: `cle.182682.xyz`（ preferring IP 加速）

2. **配置 Worker 路由**
   - 在 Worker 设置的 **触发器** 选项卡
   - 点击 **添加路由**
   - 配置:
     - 路由: `your-subdomain.example.com/*`
     - 选择对应的域名区域
   - **重要**: 末尾必须带上 `/*` 通配符

### 第四步：等待部署生效

通常在几分钟内传播完毕。可通过 [Cloudflare 状态页](https://www.cloudflarestatus.com/) 查看进度。

## 使用方式

部署完成后，可以通过以下方式使用加速服务：

### 原始地址格式
```
https://github.com/用户名/仓库名/archive/main.zip
```

### 加速后格式
```
https://你的-worker-subdomain.workers.dev/用户名/仓库名/archive/main.zip
```

或使用自定义域名:
```
https://gh.yourdomain.com/用户名/仓库名/archive/main.zip
```

### 可加速的资源类型

| 资源路径 | 说明 |
|----------|------|
| `/repos/*/releases/*` | Release 文件下载 |
| `/tarball/*` | 压缩包下载 |
| `/archive/*` | 归档下载 |
| `/gists/*` | Gist 内容 |
| `/raw/*` | Raw 文件 |

### 使用示例

```bash
# 原始下载
curl -L https://github.com/username/repo/archive/main.zip -o repo.zip

# 使用加速（通过 Worker）
curl -L https://your-worker.workers.dev/username/repo/archive/main.zip -o repo.zip

# Raw 文件加速
curl -L https://your-worker.workers.dev/raw/username/repo/main/README.md

# Gist 加速
curl -L https://your-worker.workers.dev/gists/username/gist-id

# API 请求加速
curl -H "Accept: application/vnd.github.v3+json" \
  https://your-worker.workers.dev/repos/username/repo/releases
```

## 配置说明

### wrangler.toml 配置

```toml
name = "github-proxy"        # Worker 名称
main = "src/index.js"        # 入口文件
compatibility_date = "2024-01-01"  # 兼容性日期

# 可选环境变量
# [vars]
# UPSTREAM = "https://github.com"
```

### 高级配置

如需自定义缓存策略，可以修改 `src/index.js` 中的配置:

```javascript
cf: {
  cacheTtl: 3600,        // 缓存时间（秒）
  cacheEverything: false // 是否缓存所有响应
}
```

## 已知问题

- 由于 IP 归属地原因，加速服务可能被部分防火墙阻挠
- 如遇访问异常，检查 DNS 解析和路由配置是否正确
- API 请求有速率限制，请合理使用

## 测试验证

部署后可以执行以下测试：

```bash
# 测试 API 加速
curl -I https://your-worker.workers.dev/repos/cloudflare/workers-sdk/releases

# 测试 Raw 文件加速
curl -I https://your-worker.workers.dev/raw/cloudflare/workers-sdk/main/README.md

# 测试 archive 加速
curl -I https://your-worker.workers.dev/cloudflare/workers-sdk/archive/main.zip
```

预期应该返回 200 或 302 状态码，响应头包含 Cloudflare 相关头信息。

## 附录

### 相关链接

- 项目源码: https://gitee.com/geekertao/CF-Workers-GitHub-Proxy
- 作者主页: https://geekertao.cn/rainyun
- 示例加速站: https://github.akams.cn
- Cloudflare 状态页: https://www.cloudflarestatus.com/
- Worker 仪表盘: https://dash.cloudflare.com

### 注意事项

1. 请遵守 GitHub 的使用条款
2. 免费配额有限，不要用于大规模商业下载
3. 建议设置合理的缓存策略减少上游请求
4. 定期查看使用量，避免超出配额

## License

MIT
