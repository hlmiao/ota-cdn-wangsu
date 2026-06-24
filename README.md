# OTA 升级 CDN 迁移手册：AWS CloudFront → 网宿 CDN Pro

本手册记录将 OTA（固件升级）内容分发从 **AWS CloudFront（北京区域）** 迁移到 **网宿 CDN Pro（Wangsu / CDNetworks）** 的配置与测试步骤。

| # | 部分 | 状态 |
| --- | --- | --- |
| ① | [证书上传与验证](#一证书上传与验证) | ✅ 演练实测通过（HTTPS 握手 + 证书正确返回） |
| ② | [URL 签名（预签名 URL）](#二url-签名预签名-url) | ✅ 演练实测通过（合法 200 / 篡改 403 / Range 206） |
| ③ | [S3 桶回源](#三s3-桶回源) | ✅ 演练实测通过（私有桶 + SigV4，etag 一致 + 缓存 HIT） |
| ④ | [URL 签名日志导出](#四url-签名日志导出) | ⏸ 暂缓（客户已自建 gz→stdout 服务） |

## 官方文档引用

- 证书上传：https://en.wangsu.com/document/certificate/cert-upload-a-ssl-certificate?rsr=ws
- AWS S3 桶加速回源：https://en.wangsu.com/document/cdnpro/awss3bucketacceleration
- Edge Logic 支持的指令（预签名 URL）：https://en.wangsu.com/document/cdnpro/supportedirectives
- 实时日志（日志导出）：https://en.wangsu.com/document/cdnpro/realtimelogging?rsr=ws

> 文中 `<尖括号>` 为占位符，请替换为你的实际值。配套脚本见 [`scripts/`](scripts)。

---

## 迁移前置确认

| 项 | 说明 | 取值 |
| --- | --- | --- |
| S3 桶区域 | AWS 中国区 **北京 cn-north-1**（光环新网），桶名 `ota-firmware-bucket` | ✅ 已定 |
| 是否境内出流量 | **已实测**：网宿大陆节点对未备案域名的 HTTP 请求返回 **451**（平台合规拦截，先于 Edge Logic）。`.work` 不可备案，功能测试已改用备案域名 `ota-test.example.com.cn` | ✅ 已解决 |
| 原 CloudFront 签名 | Signed URL（RSA）还是 Signed Cookie | `<待填>` |
| 设备端能力 | 是否校验完整证书链 / 是否证书 pinning / 是否 Range 续传 | `<待填>` |

**迁移策略**：先用测试域名 + 测试 bucket 前缀跑通，CloudFront 与网宿 **并行运行**，验证通过后再切流量。

### 准备：建立测试加速域名

演练实际用了**两个域名**（踩坑后确定的分工）：

| 用途 | 域名 | 说明 |
| --- | --- | --- |
| 证书 / HTTPS 握手验证（①） | `ota-test.example.work` | `.work` 新 gTLD，**大陆无法 ICP 备案**。但 TLS 握手层不受备案限制，证书绑定/握手已在此域名实测通过 |
| 签名 / 回源等 HTTP 层测试（②③） | `ota-test.example.com.cn` | **已 ICP 备案**。大陆节点对未备案域名的 HTTP 请求返回 451，功能测试必须用备案域名 |

1. 网宿 CDN Pro 控制台新建加速项目（Property），加速域名填上表域名，服务类型选 **大文件下载 / 点播下载** 类。
2. 域名 CNAME 指向网宿分配的边缘调度域名（演练用 `--resolve` 可不依赖 DNS）。
3. CDN Pro 提供 **演练（Staging）** 与 **生产** 两套环境，先在演练验证再部署生产。

> 🔑 **关键实测结论：大陆节点强制备案**。网宿大陆边缘节点对**未备案域名**的 HTTP 请求直接返回 `HTTP 451` + `link: ...; rel="blocked-by"`（平台合规层拦截，发生在 Edge Logic 之前，**不是** 你签名规则的 403）。这与 CloudFront 北京区不同，是迁移必须处理的前置条件——**生产域名必须完成 ICP 备案 + 网宿 CDN 接入备案**。

---

## 网宿 CDN Pro 控制台配置全流程（端到端操作步骤）

> 按**实操顺序**串起来的「点哪、填什么」清单；每步字段细节见对应的 ①②③ 详解。演练就是按这个顺序跑通的。

**Step 0　新建加速项目（Property）**
- 控制台 → 新建 Property（加速项目），服务类型选「大文件下载 / 点播下载」类。
- CDN Pro 配置**带版本**：首个版本（v1）可直接编辑；**一旦部署就锁定**，后续改动要克隆新版本（见 Step 5）。

**Step 1　配置 Hostname（加速域名）**
- 在 Property 配置里把加速域名加进 **Hostname**：演练备案域名 `ota-test.example.com.cn`。
- ⚠️ 大陆节点强制备案：未备案域名的 HTTP 请求会被平台 451 拦截（见「准备」）。

**Step 2　添加 S3 源站（Origin）**　→ 详见 [三、S3 桶回源](#三s3-桶回源)
- 新建源站，**Origin Name = `aws_origin`**（必须与 Edge Logic 里 `origin_pass aws_origin` 一致）。
- 主机名 = 桶域名 `ota-firmware-bucket.s3.cn-north-1.amazonaws.com.cn`。
- **Host 请求头 = 同一个桶域名**（不填会 `NoSuchBucket`）。
- 回源 HTTPS + SNI。
- 回源鉴权：**AWS S3（SigV4）**，地区 `cn-north-1`，Access Key 明文填；**Secret Key 先在 Secrets 建一条（值只填 SK）再引用**。

**Step 3　配置 Edge Logic（签名校验 + 回源）**　→ 详见 [二、URL 签名](#二url-签名预签名-url)
- 把 [`edge_logic.conf`](edge_logic.conf) 全文粘进 Edge Logic（签名校验 location + 裸路径 `return 403`）。
- 把 `<SECRET>` 换成签名密钥（须与发链端 `scripts/sign_url.py` 逐字符一致）。
- ⚠️ 用了 `eval_func`（advanced 指令），账号需开通，否则部署失败。
- 若用向导生成基线，要**整体替换**掉扩展名缓存模板（见 ② 的「从向导基线改造」）。

**Step 4　配置并关联证书**　→ 详见 [一、证书上传与验证](#一证书上传与验证)
- 演练推荐：证书页用 **Automatically generate a self-signed certificate**（CN/SAN = 加速域名，RSA 2048）。
- **关键：回到 Property，在 `TLS Certificate` 字段把证书显式选进去**（不是纯 SAN 自动匹配；不选会回落网宿默认证书）。

**Step 5　部署到 Staging（演练）**
- 部署当前版本到 **Staging**。
- ⚠️ 之后任何改动（补证书 / 改 Host 头 / 加鉴权…）都要：**克隆新版本 → 在新版本改 → 再部署**（已部署版本不可变）。

**Step 6　演练验证（演练节点 IP + `--resolve`）**
- 演练节点 IP 取自控制台 **Staging IP 列表**（不是 dig）。下发有 propagation 延迟，首次超时/失败多等 1-2 分钟。
- 验证顺序：
  1. **证书 / 握手**：`curl -vIk --resolve <域名>:443:<演练IP> https://<域名>/<对象>` → 看 `subject=CN=<域名>`
  2. **裸路径拒绝**：直接访问真实路径 → 期望 `403`（备案过了合规层 + 签名逻辑生效）
  3. **签名三件套**：合法 200 / 篡改 403 / Range 206（用 `scripts/sign_url.py` 发链）
  4. **缓存**：同链接再请求 → `x-cache-status: HIT`

**Step 7　上生产**
- 演练通过后把版本部署到 **生产**；换可信证书、替换正式签名密钥、轮换回源 AccessKey。
- 最后改 DNS 把加速域名 CNAME 切到网宿（见「切换流量」）。

---

## 一、证书上传与验证

**目标**：在加速域名上配置 HTTPS，证书链完整、设备端可信任。本节用**自签证书**先跑通"上传 → 绑定 → 验证"流程（演练用），生产请换成可信证书（见末尾）。

### 1. 生成演练用自签证书

使用 [`scripts/gen_self_signed_cert.sh`](scripts/gen_self_signed_cert.sh)（mini-CA 模式：自建根 CA 签发服务器证书，产出 证书/CA/私钥 三件套，贴合上传表单）：

```bash
./scripts/gen_self_signed_cert.sh ota-test.example.work
```

产物在 `certs/`：

| 文件 | 上传字段 |
| --- | --- |
| `server.crt` | 证书文件（Certificate）|
| `ca.crt` | CA 文件（CA）|
| `server.key` | 私钥文件（Private Key）|
| `fullchain.crt` | 完整链（备用）|

> ⚠️ 自签证书不被 OTA 设备/浏览器信任，**仅用于跑通流程，禁止上生产**。

### 2. 上传前本地自检

```bash
# 证书与私钥必须配对：两行 md5 必须一致
openssl x509 -noout -modulus -in certs/server.crt | openssl md5
openssl rsa  -noout -modulus -in certs/server.key | openssl md5

# 查看有效期、SAN 是否含 OTA 域名
openssl x509 -in certs/server.crt -noout -subject -dates -ext subjectAltName
```

### 3. 上传证书（控制台）

参照官方文档，CDN Pro 控制台「证书管理 → SSL 证书 → 我的证书 → 上传证书」：

1. **密钥算法**：国际标准选 `Certificate - International Standard`（RSA/ECC，需传 证书 + CA + 私钥）；国密选 `SM2`。
2. **上传方式**：
   - 文件导入：支持 `.pem / .key / .crt / .cer / .der / .pfx / .jks`
   - 粘贴内容：仅支持 PEM 编码，分别粘贴 证书内容 / 私钥内容 / CA 内容
3. **证书解析**：系统自动解析并显示授权域名（CN/SAN）、序列号、颁发者、有效期、加密算法等，核对无误。
4. 点击 **提交**。

### 4. 关联域名（关键，上传不会自动绑定）

> 官方上传文档明确：上传只完成分发部署，**不会自动关联域名**。

1. 在加速项目 / TLS 配置页，选择刚上传的证书绑定到加速域名。
2. 开启 TLS 1.2 / 1.3，按需开启强制 HTTPS 跳转、HSTS。
3. 先部署到 **演练环境** 验证，再部署 **生产**。

### 5. 部署后验证

```bash
# 演练环境：用 --resolve 指到演练节点 IP（IP 取自控制台 Staging IP 列表，任选一个）
curl -vIk https://ota-test.example.work/<测试对象> --resolve ota-test.example.work:443:<演练节点IP>

# 查看返回的证书链是否完整
openssl s_client -connect ota-test.example.work:443 -servername ota-test.example.work -showcerts </dev/null
```

> 判读：**看 `subject` 行**——返回 `CN=<你的域名>` 即证书绑定生效；若是 `CN=default.chinanetcenter.com` 则是网宿默认证书（证书没绑上，见下「演练实测记录」）。自签证书演练用 `-k` 跳过信任校验，`verify` 报 `self signed certificate ... continuing anyway` 属正常；生产可信证书去掉 `-k`，不应出现 `unable to get local issuer`。HTTP 状态码取决于备案与签名（未备案域名会 451）。

### 演练实测记录与坑（重要）

在控制台实际跑通证书绑定时，踩了几个 CloudFront 没有的坑，记录如下：

**1. 证书必须在 `TLS Certificate` 字段显式关联（不是纯 SAN 自动匹配）**
上传 / 生成证书只是入库，节点不会自动用。必须在 Property 配置的 **`TLS Certificate`** 字段里**手动把证书选进去**，该 hostname 才会用它。没选时，节点对该 SNI 回落网宿**默认证书** `CN=default.chinanetcenter.com`（DigiCert 签发的真证书，所以 `curl` 显示 `SSL certificate verify ok`——**这是陷阱**，要看 `subject` 是不是你的域名，别被 `verify ok` 骗了）。

**2. 已部署的版本不可变 → 必须克隆新版本**
版本一旦部署就被锁定（immutable，保证可追溯 / 回滚）。要改配置（如补选证书）不能直接改已部署版本，须 **克隆 v1 → 得到 v2 → 在 v2 里关联证书 → 部署 v2**。

**3. 用平台「自动生成自签证书」更省事（演练推荐）**
网宿证书页的 **Automatically generate a self-signed certificate** 可按 hostname 自动生成自签证书并便于绑定，省去手动生成 / 上传 / SAN 匹配。字段填法：
- **Public Key Algorithm**：`RSA 2048`（嵌入式 OTA 设备兼容性最好；ECDSA 部分老栈不支持）
- **Common Name**：加速域名
- **SAN**：同加速域名（客户端只校验 SAN，必须一字不差，别加 `www.`、别用泛域名）

**4. 节点下发有 propagation 延迟**
部署成功后到节点真正生效有几十秒~几分钟延迟。实测**首次 curl 超时、隔一会儿再试才返回正确证书**，属正常，别误判为失败。

**5. 演练节点 IP 从控制台 Staging IP 列表取**
不是 `dig staging.qtlgslb.com`（该名不存在，返回 NXDOMAIN）。演练节点 IP 在控制台 Staging IP 列表里，任选一个用于 `--resolve`（实测用过 `203.0.113.10`、`203.0.113.11`）。

**6. 成功 vs 失败长相对照**

| | 失败（证书没绑定） | 成功（证书已生效） |
| --- | --- | --- |
| `subject` | `CN=default.chinanetcenter.com` | `CN=<你的域名>` |
| `issuer` | `DigiCert ...`（真 CA） | 你的自签 / 平台自签 |
| verify | `verify ok`（被默认真证书骗） | `self signed certificate ... continuing anyway`（正常） |
| HTTP | 连接 reset / 默认页 | 备案域名返回状态码；未备案域名返回 451 |

**7. HTTP 451 = 大陆节点备案拦截**
证书绑定成功后，未备案域名的 HTTP 请求返回 `451` + `rel="blocked-by"`（指向 CDN360）。这是平台合规层拦截，**不是** Edge Logic 的 403。解决：功能测试改用备案域名 `ota-test.example.com.cn`（见「准备」）。

### OTA 设备特别注意

- 嵌入式设备根证书库小且不常更新，必须确认：①中间证书链完整下发；②设备信任库含根 CA，或已做证书 pinning。
- 做了 pinning 时，换证书需同步更新固件白名单。
- **务必在真实设备上验证**。

### 生产证书来源（三选一）

- **A** 沿用现有可信证书（需有私钥；ACM 证书无法导出私钥）
- **B** 找 CA 重新签发（可用 `scripts/gen_self_signed_cert.sh` 思路生成私钥 + CSR 提交 CA）
- **C** CDN Pro 的 **Let's Encrypt 自动签发与续期**

### 验证清单

- [x] cert/key md5 一致
- [x] 上传 / 生成成功且解析信息正确
- [x] 已在 `TLS Certificate` 字段关联到加速域名（克隆新版本部署）
- [x] 演练环境 curl 返回正确证书（`subject=CN=<域名>`，非默认证书）
- [ ] （生产）真实设备信任链验证通过
- [ ] （生产）域名完成 ICP 备案 + 网宿 CDN 接入备案

---

## 二、URL 签名（预签名 URL）

**目标**：仅授权请求可下载固件。CDN Pro 通过 **Edge Logic** 实现预签名 URL，使用 `eval_func MD5 + HEX_ENCODE` 计算签名、`COMPARE_INT` 校验过期。**OTA 后端发链代码需替换为本节算法**（不再是 CloudFront 的 RSA 签名）。

> ⚠️ **本节及第三部分的功能测试必须在备案域名 `ota-test.example.com.cn` 上进行**——大陆节点对未备案域名的 HTTP 请求直接 451，请求到不了 Edge Logic，签名/回源都测不了。下文命令里的域名请替换为该备案域名。

### URL 格式

```
https://<域名>/<token_t>/<sign>/<mode><real_path>
                过期时间戳  MD5签名  f或d   真实路径
```

- `mode=f` 文件级：仅放行该文件
- `mode=d` 目录级：放行该目录下所有文件（适合按 OTA 版本目录授权）

### 签名算法

```
文件级(f): sign = hex( md5( SECRET + real_path  + token_t ) )
目录级(d): sign = hex( md5( SECRET + parent_dir + token_t ) )
parent_dir = real_path 到最后一个 '/' 为止（含 '/'）
token_t    = 绝对过期时间戳 = 当前时间 + ttl
```

### 1. Edge Logic 配置（边缘侧校验）

```nginx
location ~ ^/(\d+)/([a-f0-9]+)/([fd])(/.+)$ {
    set $token_t $1;
    set $token_sign $2;
    set $mode $3;
    set $real_path $4;

    # 提取父目录
    set $parent_dir $real_path;
    if ($real_path ~ "^(.*/)[^/]+$") { set $parent_dir $1; }

    # 文件级签名
    set $file_str "<SECRET>${real_path}${token_t}";
    eval_func $file_md5_bin MD5 $file_str;
    eval_func $file_sign HEX_ENCODE $file_md5_bin;

    # 目录级签名
    set $dir_str "<SECRET>${parent_dir}${token_t}";
    eval_func $dir_md5_bin MD5 $dir_str;
    eval_func $dir_sign HEX_ENCODE $dir_md5_bin;

    # 按 mode 校验
    set $check_f "f${file_sign}";
    set $check_d "d${dir_sign}";
    set $expect "${mode}${token_sign}";
    set $auth "0";
    if ($check_f = $expect) { set $auth "1"; }
    if ($check_d = $expect) { set $auth "1"; }
    if ($auth = "0") { return 403; }

    # 校验过期
    if ($msec ~ "^(\d+)") { set $now $1; }
    eval_func $cmp COMPARE_INT $token_t $now;
    if ($cmp ~ "^-") { return 403; }

    # 固件缓存（边缘命中后大规模下载不回源）
    proxy_cache_valid 200 206 24h;

    # 去掉 token 前缀回源
    rewrite ^/\d+/[a-f0-9]+/[fd](/.+)$ $1 break;
    origin_pass aws_origin;          # 见第三部分 S3 回源
}

location / { return 403; }
```

> ⚠️ 把 `<SECRET>` 换成你的真实密钥（演练可用脚本里的默认密钥）。`eval_func` 属 advanced 指令，需确认账号已开通。

> 📋 **可直接复制的完整版**：[`edge_logic.conf`](edge_logic.conf)（英文注释、演练密钥已填好，可直接粘贴进 CDN Pro Edge Logic）。上生产前替换密钥，并与发链端 `scripts/sign_url.py` 同步。

> **从向导基线改造**：Edge Logic Wizard 选「website acceleration」基线后，会生成按 .php/.mp3/.html/.js 等扩展名分桶缓存的 `location` 和一个 `location / { origin_pass aws_origin; }`。OTA 场景要**整体替换**为上面这套——删掉扩展名 location（OTA 只发固件用不上），并把 `location /` 改成 `return 403`（否则没签名的裸路径也能回源下载固件，是安全漏洞）。正则 location 优先级高于 `location /`，带 token 的请求进鉴权块、裸路径被 403。

> ⚠️ **缓存键的坑（生产必处理）**：默认缓存键含完整 URL，而签名链里的 `token_t`/`sign` 每次发链都变 → 同一固件每次都是新 key → 边缘命中不了、每次回源（回源压力 + S3 流量费）。**演练阶段可忽略**；生产要把缓存键改为「去掉 token 前缀的 `$real_path`」，让同一固件的不同签名链共享缓存。CDN Pro 具体指令（大概率 `proxy_cache_key` 指向 `$real_path`）**待向网宿确认**。

### 2. 后端发链（[`scripts/sign_url.py`](scripts/sign_url.py)）

```bash
# 文件级，有效期 1800s
python3 scripts/sign_url.py https://ota-test.example.work /firmware/v1.2.3/app.bin --ttl 1800

# 目录级
python3 scripts/sign_url.py https://ota-test.example.work /firmware/v1.2.3/app.bin --mode d
```

也可作为模块在后端调用：

```python
from scripts.sign_url import sign_url
url = sign_url("https://ota-test.example.com", "/firmware/v1.2.3/app.bin", ttl=1800, secret="<你的密钥>")
```

### 3. 测试用例

| 用例 | 期望 |
| --- | --- |
| 合法签名 | `200` |
| 篡改 sign 或 path | `403` |
| 过期（token_t 取过去时间） | `403` |
| 目录级签名访问同目录其他文件 | `200` |
| Range/断点续传 + 签名 | `206`（OTA 必测） |

```bash
URL=$(python3 scripts/sign_url.py https://ota-test.example.work /firmware/v1.2.3/app.bin)
curl -I "$URL"                                   # 合法 -> 200
curl -I "${URL}x"                                # 篡改 -> 403
curl -I -H "Range: bytes=0-1023" "$URL"          # 续传 -> 206
```

### 对齐要点（错一处即全 403）

1. 后端 `SECRET + 路径 + token_t` 的拼接顺序与 Edge Logic 的 `$file_str` / `$dir_str` 逐字符一致。
2. `token_t` 是绝对过期时间戳（不是时长）。
3. 发链端与边缘节点 **时间需 NTP 同步**。

### 验证清单

- [x] `eval_func` 等 advanced 指令已开通（签名校验生效即说明可用）
- [x] 合法 200、篡改 403（实测通过）
- [ ] 目录级签名生效（`--mode d`，待补测）
- [x] Range 续传鉴权正常（206 + 缓存 HIT）
- [ ] 过期签名 403（待补测：token_t 取过去时间）
- [ ] 密钥安全存放（发链 SECRET 当前为演练明文，上生产改为环境变量/密管读取）

---

## 三、S3 桶回源

**目标**：网宿节点回源拉取 S3 对象。OTA 固件建议直接用**私有桶 + SigV4 回源鉴权**，避免 S3 直链绕过 CDN。

### 1. 添加 S3 源站（控制台）

加速项目「源站 → 添加」：

- **源站名称**：`aws_origin`（与 Edge Logic 里 `origin_pass aws_origin` 对应）
- **主机名/IP**：S3 桶访问域名 `ota-firmware-bucket.s3.cn-north-1.amazonaws.com.cn`，点「验证」测连通
- **Host 请求头**（高级配置）：填 **同样的桶域名** `ota-firmware-bucket.s3.cn-north-1.amazonaws.com.cn`
  - ⚠️ 缺省会默认带加速域名，导致 S3 返回 `Bucket not found`
- **回源协议**：HTTPS，开启回源 SNI

### 2. Edge Logic 引用源站

将第二部分鉴权 `location` 末尾的 `origin_pass aws_origin;` 指向该源站；默认缓存模板里各路径的源站也设为 `aws_origin`。

### 3. 私有桶 + SigV4 回源鉴权

1. AWS S3 控制台把桶设为私有（勾选 Block all public access）。
2. 准备：AWS 区域、Access Key、Secret Key。
3. CDN Pro 源站「高级配置 → 回源鉴权」：
   - 认证：选 `AWS S3`
   - 地区：填 **`cn-north-1`**（桶在北京区，**务必与桶实际区域一致**，否则会被 S3 301 重定向）
   - Access Key：填 AWS Access Key ID
   - Secret Key：存入「保密信息」后引用（不要明文）
4. 部署演练环境验证。

> ⚠️ **区域坑（已实测）**：本地 `awscn` profile 默认区域是 `cn-northwest-1`（宁夏），而桶在 `cn-north-1`（北京）。区域不匹配时 S3 返回 `301 PermanentRedirect`。CDN Pro 回源鉴权「地区」务必选 `cn-north-1`，端点用 `.s3.cn-north-1.amazonaws.com.cn`。

### S3 侧演练验证记录（已通过）

> 账号 `123456789012`（aws-cn 分区），桶 `ota-firmware-bucket`（cn-north-1，私有，SSE-AES256）。
> 已上传测试对象 `firmware/v1.2.3/app.bin`（2 MB），用 AWS 预签名 URL 验证（不暴露桶）：

| 验证项 | 结果 |
| --- | --- |
| 完整 GET | `200`，Content-Length 2097152，ETag `2710c7a8…` |
| Range `0-1023` | `206 Partial Content`，Content-Range 正确（OTA 续传 OK）|
| 下载完整性 | 下载 md5 与本地一致 |
| 桶私有性 | 直连需签名，私有生效 |

> 复现命令（需 `--region cn-north-1`，否则 301）：
> ```bash
> URL=$(aws s3 presign s3://ota-firmware-bucket/firmware/v1.2.3/app.bin --expires-in 600 --region cn-north-1 --profile awscn)
> curl -s -o /dev/null -D - "$URL" | head            # 200
> curl -s -o /dev/null -D - -H "Range: bytes=0-1023" "$URL" | head   # 206
> ```

> ⏭ **下一步只能在网宿控制台侧测**：CDN Pro → S3 的回源拉取（CLI 测不了）。S3 侧已就绪，私有桶正好对应 SigV4 方案。

### 4. 测试（CDN Pro 侧）

```bash
# 首次请求回源拉取（带签名 URL，演练节点）
URL=$(python3 scripts/sign_url.py https://ota-test.example.work /firmware/v1.2.3/app.bin)
curl -I "$URL" --resolve ota-test.example.work:443:<演练节点IP>
```

关注响应头：
- `x-cache-status: MISS`（首次）→ 再次请求 `HIT`
- `accept-ranges: bytes`、`content-length` 正常
- 大文件 Range 回源 `206` 正常
- **S3 直链被拦截**（私有桶已生效）

> ⚠️ 调整现网 bucket policy 前，确认不影响仍在运行的 CloudFront；先在测试前缀验证。

### 演练实测记录（已通过）

在备案域名 `ota-test.example.com.cn` 上跑通了完整链路（签名 → 回源 → 缓存），踩的坑记录如下：

**1. Host 请求头必须设成桶域名（否则 NoSuchBucket）**
CDN Pro 回源默认把**加速域名**当 Host 发给 S3，S3 按 Host 认桶 → 找不到 → 返回 `404 NoSuchBucket`（`<BucketName>` 显示的就是加速域名）。必须在源站 `aws_origin` 高级配置里把 **Host 请求头**填成桶域名 `ota-firmware-bucket.s3.cn-north-1.amazonaws.com.cn`。

**2. 回源鉴权：SK 进 Secrets，AccessKey 明文填（否则 AccessDenied/403）**
回源鉴权空着 → 匿名访问私有桶 → `403 AccessDenied`。配置方式：
- 先在 **Secrets / 保密信息**新建一条（如 `s3-origin-secret`），值**只填 Secret Access Key**；
- 源站回源鉴权选 **AWS S3**，**地区 `cn-north-1`**，Access Key 填明文 `AKIA...`，Secret Key **引用**那条 Secret。

**3. 鉴权/Secret 部署后有 propagation 延迟**
刚部署完测可能仍 `403`（节点还没拿到新鉴权），等 1-2 分钟、用**新生成的签名 URL**再测就 200。

**实测结果**（备案域名 + 演练节点）：

| 用例 | 结果 |
| --- | --- |
| 合法签名 GET | `200`，`content-length: 2097152`，etag `2710c7a8…`（与 S3 侧一致）|
| 篡改签名 | `403`（Edge Logic 拦截，返回 html、无 `x-amz` 头）|
| Range `0-1023` | `206`，`content-range: bytes 0-1023/2097152` |
| 同链接再请求 | `x-cache-status: HIT`（边缘缓存生效，Range 也命中，不回源）|

> 区分 403 来源：带 `x-amz-request-id` / `application/xml` 是 **S3 回源鉴权**问题（看 XML `<Code>`：`SignatureDoesNotMatch`=SK/地区错，`AccessDenied`=权限/key 错）；返回 html、无 `x-amz` 是 **Edge Logic** 拦的（签名错或过期）。

### 验证清单

- [x] S3 侧对象可取（GET 200 / Range 206 / 完整性 OK）
- [x] 桶私有性确认
- [x] CDN Pro 源站连通性验证通过
- [x] Host 请求头已设为桶域名
- [x] 私有桶 + SigV4 回源成功（地区 = cn-north-1，SK 存 Secrets）
- [x] 缓存 MISS→HIT 正常
- [x] 大文件 / Range 回源正常（206 + 命中缓存）
- [ ] S3 直链被拦截（私有桶已生效，待补充直链 403 验证）
- [ ] 未影响现网 CloudFront

---

## 四、URL 签名日志导出

> ⏸ 本部分暂缓。现状：客户已自建服务，从 S3 读取网宿日志 gz 包 → 解压 → 打印到 stdout。

待恢复时需向网宿确认：
1. gz 日志**如何投递到 S3**（离线日志转储 / 实时日志中转 / 主动用下载 API 拉取）
2. 日志**字段 schema / 变量清单**（分隔符、是否 JSON、字段顺序），供解压服务解析
3. 日志 URL 字段含**完整签名路径前缀**、**状态码**（审计 403）
4. 投递时延、保留周期、是否付费高级功能

---

## 切换流量（阿里云云解析 DNS）

> 演练 + 生产都验证通过后，最后一步才改 DNS。`example.work` 托管在阿里云云解析 DNS。

1. 阿里云控制台 → **云解析 DNS** → 域名列表 → `example.work` → **解析设置** → 添加记录：
   - 记录类型：`CNAME`
   - 主机记录：`ota-test`（只填子域名前缀）
   - 记录值：网宿给的边缘调度域名，如 `xxxx.qtlcdn.com`
   - TTL：10 分钟
2. 验证解析生效并用真实域名复测（生产用可信证书，去掉 `-k`）：
   ```bash
   dig ota-test.example.work +short        # 应解析到 xxxx.qtlcdn.com → 网宿节点
   curl -I https://ota-test.example.work/<带签名对象>
   ```

> ⚠️ 若网宿在添加加速域名时要求**域名归属验证**，按其给的 TXT/CNAME 值在阿里云云解析另加一条验证记录（与业务 CNAME 不同）。
> ⚠️ **大陆境内分发强制 ICP 备案 + 网宿 CDN 接入备案**（实测未备案域名 HTTP 451）。`.work` 不可备案，功能测试已改用备案域名 `ota-test.example.com.cn`；该域名 DNS 由其权威服务管理，CNAME 在对应 DNS 平台配置（不一定是阿里云云解析）。

---

## 附录 A：仓库结构

```
ota-wangsu/
├── README.md                       # 本手册
├── scripts/
│   ├── gen_self_signed_cert.sh     # 生成演练自签证书（mini-CA）
│   └── sign_url.py                 # 预签名 URL 生成器（匹配 Edge Logic）
├── certs/                          # 生成的演练证书（私钥已被 .gitignore 排除）
└── *.pdf                           # 网宿官方参考文档
```

## 附录 B：总进度清单

- [ ] 前置信息确认
- [ ] 测试加速域名建立
- [x] ① 证书上传与验证（演练实测通过）
- [x] ② URL 签名（演练实测通过：合法 200 / 篡改 403 / Range 206）
- [x] ③ S3 桶回源（演练实测通过：SigV4 + etag 一致 + 缓存 HIT）
- [ ] ④ 日志导出（暂缓）
- [ ] 全部验证通过，切换现网流量
