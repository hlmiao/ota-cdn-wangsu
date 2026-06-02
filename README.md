# Wangsu CDNPro Handbook / 网宿 CDNPro 接入手册

A practical handbook covering the three core configurations needed to onboard an S3-backed acceleration on Wangsu CDNPro. Each document is independent.

围绕一次 S3 加速接入所需的三类核心配置的实操手册，每份文档独立可用。

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
| [证书上传](docs/cn/证书上传.md) | 把自有 SSL/TLS 证书托管到网宿，并绑定到加速域名 |
| [AWS S3 回源](docs/cn/S3回源.md) | 把 AWS S3 桶配置为 CDNPro 源站，由边缘节点完成 SigV4 鉴权 |
| [CDN URL Presigned](docs/cn/CDN-URL-Presigned.md) | 通过 Edge Logic 实现限时 / 防盗链的预签名 URL 校验 |

---

## Conventions

- Placeholders such as `files.example.com`, `my-bucket`, `xxx.qtlcdn.com` should be replaced with real values.
- Edge Logic uses Wangsu's `eval_func` directive (standard tier); the syntax resembles nginx but is **not** nginx — do not reuse nginx modules.
- Credentials (AWS Secret Key, signing secret, etc.) should be injected via the console's **Secrets / Vault** rather than hard-coded.
- All changes follow **Staging → Production** two-stage deployment.

文中占位符（`files.example.com` / `my-bucket` / `xxx.qtlcdn.com`）按实际环境替换；Edge Logic 使用 `eval_func`（语法形似 nginx 但不是 nginx）；凭证一律走保密信息（Vault）；变更走 Staging → Production 两阶段。
