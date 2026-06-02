# Wangsu CDNPro Handbook / 网宿 CDNPro 接入手册

A hands-on handbook for serving content from an AWS S3 bucket through Wangsu CDNPro. It walks through the three pieces of configuration this setup requires — TLS certificates, the S3 origin, and signed-URL access control. Each chapter stands on its own; read only the ones you need.

一份用 Wangsu CDNPro 加速 AWS S3 资源的实操手册，覆盖落地所需的三块配置：TLS 证书、S3 源站、签名 URL 访问控制。三份文档各自独立，按需阅读即可。

---

## English

| Document | Scope |
| --- | --- |
| [SSL Certificate Upload](docs/en/certificate-upload.md) | Upload a self-owned TLS certificate and bind it to the accelerated hostname |
| [AWS S3 Origin](docs/en/s3-origin.md) | Configure an AWS S3 bucket as a CDNPro origin with edge-side SigV4 |
| [CDN URL Presigned](docs/en/cdn-url-presigned.md) | Time-limited, path-bound URL signature validation via Edge Logic |

## 中文

| 文档 | 适用场景 |
| --- | --- |
| [证书上传](docs/cn/%E8%AF%81%E4%B9%A6%E4%B8%8A%E4%BC%A0.md) | 把自有 SSL/TLS 证书托管到网宿，并绑定到加速域名 |
| [AWS S3 回源](docs/cn/S3%E5%9B%9E%E6%BA%90.md) | 把 AWS S3 桶配置为 CDNPro 源站，由边缘节点完成 SigV4 鉴权 |
| [CDN URL Presigned](docs/cn/CDN-URL-Presigned.md) | 通过 Edge Logic 实现限时 / 防盗链的预签名 URL 校验 |

---

## Conventions

- Replace placeholders like `files.example.com`, `my-bucket`, and `xxx.qtlcdn.com` with the values for your environment.
- Edge Logic uses Wangsu's `eval_func` directive. The syntax looks like nginx, but the runtime is **not** nginx — don't assume stock nginx directives or modules are available.
- Inject credentials (AWS Secret Key, signing secret, etc.) through the console's built-in Secrets store; never hard-code them in a Property.
- Roll out every change through the two-stage flow: deploy to **Staging**, validate, then promote to **Production**.

文中占位符（`files.example.com` / `my-bucket` / `xxx.qtlcdn.com`）按实际环境替换；Edge Logic 使用 `eval_func`（语法形似 nginx，但运行时不是 nginx，不能假设标准 nginx 指令/模块可用）；凭证一律走控制台保密信息（Secrets），禁止硬编码到 Property；变更走 Staging → 验证 → Production 两阶段发布。
