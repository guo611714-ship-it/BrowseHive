/**
 * Cloudflare Workers GitHub 加速代理
 * 支持: API、Git Clone、Releases、Archive、Gist、Raw 文件加速
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 只处理配置的路由
    if (url.pathname === '/' || url.pathname === '/index.html') {
      return new Response('GitHub Proxy Service is running', {
        status: 200,
        headers: { 'Content-Type': 'text/plain' }
      });
    }

    // 构建 GitHub 目标 URL
    // 支持格式: /用户名/仓库名/archive/main.zip -> https://github.com/用户名/仓库名/archive/main.zip
    let githubUrl;

    if (url.pathname.startsWith('/raw/')) {
      // Raw 文件: /raw/用户名/仓库名/分支/路径
      githubUrl = `https://raw.githubusercontent.com${url.pathname.slice(4)}`;
    } else if (url.pathname.startsWith('/gists/')) {
      // Gist: /gists/用户名/gist-id
      githubUrl = `https://gist.githubusercontent.com${url.pathname}`;
    } else if (url.pathname.includes('/releases/')) {
      // Releases: /repos/用户名/仓库名/releases/download/版本/文件名
      githubUrl = `https://github.com${url.pathname}`;
    } else if (url.pathname.includes('/archive/')) {
      // Archive: /用户名/仓库名/archive/分支.zip
      githubUrl = `https://github.com${url.pathname}`;
    } else if (url.pathname.includes('/tarball/') || url.pathname.includes('/zipball/')) {
      // Tarball/Zipball
      githubUrl = `https://github.com${url.pathname}`;
    } else if (url.pathname.startsWith('/repos/')) {
      // API: /repos/...
      githubUrl = `https://api.github.com${url.pathname}`;
    } else if (url.pathname.startsWith('/')) {
      // 其他路径直接转发到 github.com
      githubUrl = `https://github.com${url.pathname}${url.search}`;
    } else {
      return new Response('Invalid path', { status: 400 });
    }

    try {
      // 转发请求到 GitHub
      const githubRequest = new Request(githubUrl, {
        method: request.method,
        headers: request.headers,
        body: request.body,
        redirect: 'manual'
      });

      // 重要: 不得泄露上游信息的头
      const excludedHeaders = ['host', 'origin', 'referer'];
      const modifiedHeaders = new Headers(githubRequest.headers);

      // 设置 User-Agent 避免被限制
      if (!modifiedHeaders.has('User-Agent')) {
        modifiedHeaders.set('User-Agent', 'Cloudflare-Workers-GitHub-Proxy');
      }

      // 如果是 API 请求，可以添加 Accept 头
      if (url.pathname.startsWith('/repos/') || url.pathname.startsWith('/gists/')) {
        if (!modifiedHeaders.has('Accept')) {
          modifiedHeaders.set('Accept', 'application/vnd.github.v3+json');
        }
      }

      const response = await fetch(githubRequest, {
        cf: {
          cacheTtl: 3600, // 缓存 1 小时
          cacheEverything: false,
          // 使用 Cloudflare 的优选网络
          // 可以配置为特定的数据中心
        }
      });

      // 构建响应头
      const responseHeaders = new Headers(response.headers);

      // CORS 支持
      responseHeaders.set('Access-Control-Allow-Origin', '*');
      responseHeaders.set('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
      responseHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');

      // 移除或修改可能暴露代理的头
      responseHeaders.delete('x-github-request-id');
      responseHeaders.delete('x-github-ot');
      responseHeaders.delete('x-github-media-type');

      // 告诉浏览器不要缓存 API 响应太久
      if (url.pathname.startsWith('/repos/') || url.pathname.startsWith('/gists/')) {
        responseHeaders.set('Cache-Control', 'public, max-age=300');
      }

      // 处理重定向
      if (response.status === 302 || response.status === 301) {
        const location = responseHeaders.get('Location');
        if (location) {
          // 将 GitHub 重定向转换为代理重定向
          const redirectUrl = new URL(location);
          if (redirectUrl.hostname === 'github.com' || redirectUrl.hostname === 'api.github.com') {
            // 保持代理域名，去除上游域名
            redirectUrl.hostname = url.hostname;
            redirectUrl.protocol = url.protocol;
            responseHeaders.set('Location', redirectUrl.toString());
          }
        }
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders
      });

    } catch (error) {
      return new Response(`Proxy error: ${error.message}`, { status: 500 });
    }
  }
};
