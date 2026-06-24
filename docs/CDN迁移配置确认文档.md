# OTA CDN 迁移配置确认文档（CloudFront → 网宿 CDN Pro）

> 用途：与**客户**及**网宿**对齐已实施的配置，并确认待办事项。
> 当前状态：演练环境（Staging）已验证证书、URL 签名、S3 回源三部分；日志导出暂缓。
> 文档版本：v1　|　日期：2026-06-24

---

## 1. 背景与目标

- 将 OTA 固件升级内容分发从 **AWS CloudFront（北京区域）** 迁移到 **网宿 CDN Pro**。
- CloudFront 与网宿**并行运行**，演练 + 生产验证通过后再切流量。
- 本次演练已在网宿 CDN Pro 演练环境（Staging）跑通**证书、URL 签名、S3 回源**全链路。

## 2. 整体架构

```
OTA 设备
   │  HTTPS + 预签名 URL（带签名+过期时间戳）
   ▼
网宿 CDN Pro 边缘节点
   │  ① 证书终止（HTTPS）
   │  ② Edge Logic 校验签名/过期（合法放行，非法/过期/裸路径 403）
   │  ③ 边缘缓存命中则直接返回（不回源）
   │  未命中 → 去 token 前缀 → SigV4 回源
   ▼
AWS S3（北京 cn-north-1，私有桶）
```

- 后端**发链服务**负责生成带签名的下载 URL（替换原 CloudFront 的签名方式）。

---

## 3. 已实施并验证的配置（演练）

### 3.1 域名与证书（第一部分）

| 项 | 取值 / 说明 |
| --- | --- |
| 演练加速域名 | `ota-test.example.com.cn`（已 ICP 备案，主域名 `example.com.cn`）|
| 证书（演练） | 平台自动生成的**自签证书**（CN/SAN = 加速域名，RSA 2048）|
| 证书绑定方式 | 在 Property 的 **TLS Certificate** 字段**显式关联**（非纯 SAN 自动匹配）|
| 备案要求 | **大陆节点强制 ICP 备案 + 网宿 CDN 接入备案**；未备案域名 HTTP 请求被平台返回 `451` |

> 实测：演练节点返回的证书 `subject=CN=ota-test.example.com.cn`，HTTPS 握手成功。

### 3.2 URL 签名 / 预签名 URL（第二部分）

| 项 | 取值 / 说明 |
| --- | --- |
| URL 格式 | `https://<域名>/<token_t>/<sign>/<mode><real_path>` |
| `token_t` | 绝对过期时间戳（epoch 秒）= 当前时间 + TTL |
| `sign` | MD5 十六进制签名 |
| `mode` | `f` 文件级 / `d` 目录级 |
| 文件级签名 | `sign = hex(md5(SECRET + real_path + token_t))` |
| 目录级签名 | `sign = hex(md5(SECRET + parent_dir + token_t))` |
| 边缘校验 | Edge Logic 用 `eval_func MD5 + HEX_ENCODE` 计算签名、`COMPARE_INT` 校验过期；**裸路径 `return 403`**（仅签名访问）|
| 发链端 | 后端服务按同一算法生成（密钥两端逐字符一致）|

> 注：`eval_func` 为 advanced 指令；演练账号可用。**演练签名密钥为占位明文，生产需替换并改为密管读取。**

### 3.3 S3 桶回源（第三部分）

| 项 | 取值 / 说明 |
| --- | --- |
| S3 桶 | `ota-firmware-bucket`，区域 **cn-north-1（北京）**，aws-cn 分区，账号 123456789012 |
| 桶访问性 | **私有桶**（Block all public access），SSE-AES256 |
| 源站名（CDN Pro）| `aws_origin`（与 Edge Logic `origin_pass aws_origin` 对应）|
| 源站主机名 | `ota-firmware-bucket.s3.cn-north-1.amazonaws.com.cn` |
| **Host 请求头** | 必须填**桶域名**（同上），否则 S3 返回 `404 NoSuchBucket` |
| 回源协议 | HTTPS + 回源 SNI |
| 回源鉴权 | **AWS S3（SigV4）**，地区 **cn-north-1** |
| 鉴权凭证 | IAM 用户 `cdn-origin-readonly`（最小权限 `s3:GetObject` on `arn:aws-cn:s3:::ota-firmware-bucket/*`）；**SK 存入 CDN Pro Secrets**，AccessKey 明文填 |
| 边缘缓存 | `proxy_cache_valid 200 206 24h` |

---

## 4. 演练验证结果（已通过）

> 验证方式：`curl --resolve` 指向演练节点 IP（来自控制台 Staging IP 列表），自签证书用 `-k`。

| 用例 | 结果 |
| --- | --- |
| HTTPS 握手 / 证书 | 返回证书 `CN=ota-test.example.com.cn`，握手成功 ✅ |
| 合法签名 GET | `200`，`content-length: 2097152`，`etag 2710c7a8…`（与 S3 侧一致）✅ |
| 篡改签名 | `403`（Edge Logic 拦截）✅ |
| Range `0-1023` | `206`，`content-range: bytes 0-1023/2097152` ✅ |
| 缓存命中 | 同链接再请求 `x-cache-status: HIT`（Range 也命中，不回源）✅ |

---

## 5. 待确认事项

### 5.1 需向【网宿】确认

| # | 事项 | 说明 / 影响 |
| --- | --- | --- |
| N1 | **advanced feature 正式开通** | `eval_func` 等 advanced 指令在**生产环境/正式账号**是否已开通，避免上线部署失败 |
| N2 | **缓存键（cache key）** | 签名 URL 的 `token_t`/`sign` 每次发链都变 → 默认缓存键含完整 URL → 同一固件每次回源、命中率低。需确认把缓存键设为**去 token 前缀的真实路径**的正确指令（预期 `proxy_cache_key` 指向 `$real_path`）|
| N3 | **演练 → 生产部署流程** | 生产环境部署步骤、生产节点 IP / CNAME 接入域名、生效时间 |
| N4 | **子域备案接入** | `ota-test.example.com.cn`（及未来生产子域）是否需在网宿侧单独做**接入备案** |
| N5 | **生产证书方案** | 是否支持 **Let's Encrypt 自动签发与续期**；或上传客户提供的可信证书的流程 |
| N6 | **版本管理机制** | 确认「已部署版本不可变、需克隆新版本」的标准操作（影响后续变更流程）|
| N7 | **日志导出（④，暂缓）** | gz 日志**如何投递到 S3**（离线转储 / 实时日志中转 / 下载 API）、**字段 schema / 变量清单**、投递时延与保留周期、是否付费高级功能 |

### 5.2 需向【客户】确认

| # | 事项 | 说明 / 影响 |
| --- | --- | --- |
| C1 | **原 CloudFront 签名方式** | 当前是 Signed URL（RSA）还是 Signed Cookie？→ 决定发链端改造范围（网宿用的是 MD5 签名，**发链代码需替换**）|
| C2 | **设备端能力** | ①是否校验完整证书链；②是否做证书 pinning（做了则换证书要同步固件白名单）；③是否 Range 断点续传 |
| C3 | **生产正式域名** | 正式加速域名是哪个？备案主体确认；DNS 在何处管理（CNAME 切换操作方）|
| C4 | **生产证书来源** | A 沿用现有可信证书（需私钥；ACM 证书无法导出私钥）/ B 找 CA 重签 / C 网宿 Let's Encrypt |
| C5 | **签名密钥管理** | 生产 SECRET 的生成、存放（密管/环境变量）、轮换策略；发链端与边缘同步更新机制 |
| C6 | **切流策略** | 灰度比例、时间窗口、回滚预案；CloudFront 与网宿并行期长度 |
| C7 | **回源凭证** | 是否沿用 IAM 用户 `cdn-origin-readonly` 最小权限策略；密钥轮换归属 |

---

## 6. 生产前必做项（安全 / 上线）

- [ ] **轮换回源 AccessKey**：演练所用 AccessKey 已在沟通过程中明文出现，上线前用 `aws iam create-access-key` 换新、删旧。
- [ ] **替换签名 SECRET**：将演练占位密钥替换为生产密钥，边缘配置与发链端**同时**更新，并改为从密管/环境变量读取。
- [ ] **替换为可信证书**：自签证书仅用于演练；生产换 CA 可信证书或 Let's Encrypt，设备端去除 `-k`、信任链校验通过。
- [ ] **缓存键优化**：按 N2 结论将缓存键指向真实路径，避免回源风暴与 S3 流量费。
- [ ] **补测项**：目录级签名（`--mode d`）、过期签名 403、S3 直链被拦截。
- [ ] **真实设备验证**：在真机上验证证书信任链与下载/续传。
- [ ] **不影响现网**：调整桶策略前确认不影响仍在运行的 CloudFront；先在测试前缀验证。

---

## 7. 附：演练环境信息（仅内部，勿外发凭证）

| 项 | 值 |
| --- | --- |
| 演练加速域名 | `ota-test.example.com.cn` |
| 演练节点 IP | `203.0.113.10` / `203.0.113.11`（取自控制台 Staging IP 列表）|
| S3 桶 / 区域 | `ota-firmware-bucket` / cn-north-1 |
| 测试对象 | `firmware/v1.2.3/app.bin`（2 MB，etag `2710c7a8…`）|
| 回源 IAM 用户 | `cdn-origin-readonly`（AccessKey/SK 详见配置，**待轮换**）|
| 签名密钥 | 演练占位密钥（详见 `edge_logic.conf` / `scripts/sign_url.py`，**待替换**）|

> 配套实施手册见仓库 `README.md`；Edge Logic 见 `edge_logic.conf`；发链脚本见 `scripts/sign_url.py`。
