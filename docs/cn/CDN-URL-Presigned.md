# CDN URL Presigned（URL 预签名）

> 来源：
> - Wangsu Documentation → CDN Pro → 边缘逻辑（Edge Logic）→ 支持的指令（最后更新 2025-12-17，本文聚焦 `eval_func` 章节）
> - 预签名 URL 校验脚本示例（客户提供）

CDN Pro 通过边缘逻辑（Edge Logic）的 `eval_func` 指令完成 URL 预签名校验：业务方按约定算法签发带签名的 URL，CDN Pro 边缘节点用相同密钥重新计算并比对，校验通过才允许回源 / 命中缓存。

---

## 目录

- [1. URL 格式与示例](#1-url-格式与示例)
- [2. 预签名校验脚本（示例）](#2-预签名校验脚本示例)
- [3. eval_func 指令参考（来自官方文档）](#3-eval_func-指令参考来自官方文档)
  - [3.1 语法与位置](#31-语法与位置)
  - [3.2 支持的函数表](#32-支持的函数表)
  - [3.3 官方示例](#33-官方示例)

---

## 1. URL 格式与示例

```
https://files.example.com/{exp}/{sign}/{mode}/{real_path}
```

| 段位 | 含义 |
| --- | --- |
| `exp` | Unix 秒级过期时间戳 |
| `sign` | 32 位十六进制签名 |
| `mode` | `f` 表示文件级签名，`d` 表示目录级签名 |
| `real_path` | 真实回源路径 |

**签名算法**

记 `SECRET` 为业务方与 CDN 共享的密钥，`exp` 为过期时间戳：

- **文件级**：`sign = HEX( MD5( SECRET + real_path + exp ) )`
- **目录级**：`parent = real_path 去掉最后一段`；`sign = HEX( MD5( SECRET + parent + exp ) )`

---

## 2. 预签名校验脚本（示例）

下面是客户提供的边缘逻辑脚本，将其粘贴到 Property 的 **Edge Logic**，并将硬编码的 SECRET 替换为通过保密信息（Vault）注入：

```nginx
location ~ ^/(\d+)/([a-f0-9]+)/([fd])(/.+)$ {
    set $token_t $1;
    set $token_sign $2;
    set $mode $3;
    set $real_path $4;

    # 提取父目录
    set $parent_dir $real_path;
    if ($real_path ~ "^(.*/)[^/]+$") {
        set $parent_dir $1;
    }

    # 计算文件级签名
    set $file_str "abwewew2757f85c51d729379fbad544a9e4wewwe2323408c7a7bb7f223ce256ddswdf9${real_path}${token_t}";
    eval_func $file_md5_bin MD5 $file_str;
    eval_func $file_sign HEX_ENCODE $file_md5_bin;

    # 计算目录级签名
    set $dir_str "abwewew2757f85c51d729379fbad544a9e4wewwe2323408c7a7bb7f223ce256ddswdf9${parent_dir}${token_t}";
    eval_func $dir_md5_bin MD5 $dir_str;
    eval_func $dir_sign HEX_ENCODE $dir_md5_bin;

    # 按 mode 验证签名
    set $check_f "f${file_sign}";
    set $check_d "d${dir_sign}";
    set $expect "${mode}${token_sign}";
    set $auth "0";
    if ($check_f = $expect) { set $auth "1"; }
    if ($check_d = $expect) { set $auth "1"; }
    if ($auth = "0") { return 403; }

    # 验证过期时间
    if ($msec ~ "^(\d+)") {
        set $now $1;
    }
    eval_func $cmp COMPARE_INT $token_t $now;
    if ($cmp ~ "^-") { return 403; }

    # 去掉 token 前缀回源
    rewrite ^/\d+/[a-f0-9]+/[fd](/.+)$ $1 break;
    origin_pass myorigin;
}

location / {
    return 403;
}
```

脚本逻辑：

1. 用正则把 URL 拆成 `exp` / `sign` / `mode` / `real_path`。
2. 用 `eval_func MD5 + HEX_ENCODE` 同时计算文件级和目录级签名。
3. 根据请求里的 `mode` 决定与哪一组期望值比对，比对失败返回 403。
4. 用 `eval_func COMPARE_INT` 对比 `exp` 与当前时间 `$msec`，过期返回 403。
5. 校验通过后用 `rewrite` 去掉签名前缀，按 `real_path` 回源到 `myorigin`。
6. 其它未带签名的请求一律 `return 403`。

---

## 3. eval_func 指令参考（来自官方文档）

> 摘自《支持的指令》文档中的 `eval_func` 章节。

`eval_func` 标记为 **标准 / 全新特有** —— 对所有客户开放，且为 CDN Pro 自研的指令。

### 3.1 语法与位置

```
使用语法： eval_func $result {function name} {parameters};
默认设置： -
可用位置： server, location, if
```

该指令用于执行一些常见的编码、解码、哈希计算、HMAC、加解密和变量对比操作。CDN Pro 将其添加到了 **rewrite 模块** 中。

![eval_func 指令开篇](../../assets/presigned/pre-16.png)

### 3.2 支持的函数表

| 类型 | 函数名称 | 语法与说明 |
| --- | --- | --- |
| 计算哈希值 | **SHA256**, **MD5**, CRC32 | `eval_func $output SHA256 $input;`<br>**SHA256** 和 **MD5** 返回**二进制串**，CRC32 返回文本串 |
| BASE64 编解码 | BASE64_ENCODE, **BASE64_DECODE** | `eval_func $output BASE64_ENCODE $input;` |
| URL 编解码 | URL_ENCODE, URI_ESCAPE, ARG_ESCAPE, URL_DECODE | `eval_func $output URL_ENCODE $input;`<br>这三个 ENCODE 函数都使用百分号（`%`）对 `$input` 进行编码：<br>• **URL_ENCODE**：转义最多的特殊字符，包括 `/?=&`，适合编码 URL 里的目录或文件名。<br>• **ARG_ESCAPE**：转义的特殊字符要少一些，不转义 `/=`，适合编码查询串参数（如 `key=val`）。<br>• **URI_ESCAPE**：转义的特殊字符更少，但仍转义 `?`，适合编码不含查询串的整段 URL（如 nginx 变量 `$uri`）。 |
| HEX 编解码 | HEX_ENCODE, **HEX_DECODE**, **LITTLE_ENDIAN_BYTES** | `eval_func $output HEX_ENCODE $input;`<br>`eval_func $output LITTLE_ENDIAN_BYTES $int $len;`<br>**LITTLE_ENDIAN_BYTES** 把整数 `$int` 从字符串格式转换为长度为 `$len` 的字节串。例如 `eval_func $output LITTLE_ENDIAN_BYTES 260 3;` 会把 `$output` 赋值为长度为 3 的字节串：`0x04, 0x01, 0x00`。 |
| AES 加解密 | **ENCRYPT_AES_256_CBC**, **DECRYPT_AES_256_CBC** | `eval_func $output ENCRYPT_AES_256_CBC $key $iv $message;`<br>`$key` 和 `$iv` 都应为 32 字节的二进制串。 |
| 计算 HMAC | **HMAC**, **HMAC_HEXKEY** | `eval_func $output HMAC $key $message {dgst-alg};`<br>`eval_func $output HMAC_HEXKEY $hexkey $msg {dgst-alg};`<br>`{dgst-alg}` 可以是 `MD5`, `SHA1`, `SHA256` |
| RSA 签名 | **RSA_SIGN**, RSA_VERIFY | `eval_func $sig RSA_SIGN {dgst-alg} $msg $privkey;`<br>`eval_func $ok RSA_VERIFY {dgst-alg} $msg $sig $pubkey;`<br>`{dgst-alg}` 目前只支持 `SHA256`。 |
| 比较整数 | COMPARE_INT | `eval_func $output COMPARE_INT $data1 $data2;`<br>当 `$data1 > $data2` 时 `$output` 为 `"1"`，相等时为 `"0"`，小于时为 `"-1"`。 |
| 整数计算器 | CALC_INT | `eval_func $output CALC_INT "$integer + 1000";`<br>计算这个表达式并把结果赋给 `$output`。仅支持整数的 `+`、`-`、`*`、`/` 操作。非法的输入表达式会导致结果为 `"NAN"`。 |
| 整数绝对值 | ABS_INT | `eval_func $output ABS_INT $integer;`<br>`$output` 会被赋予 `$integer` 的绝对值。非法输入会导致结果为空。 |
| 字符串替换 | REPLACE | `eval_func $output REPLACE <old> <new> $input;` |
| 字符串修改 | TO_UPPER | `eval_func $output TO_UPPER $input;` 把输入字符串转成大写。 |
| 字符串修改 | TO_LOWER | `eval_func $output TO_LOWER $input;` 把输入字符串转成小写。 |
| 字符串修改 | SUBSTR | `eval_func $output SUBSTR <start> <length> $input;`<br>获取输入字符串的一个子串，长度为 `<length>`，起始位置为 `<start>`。`<start>` 可以是一个负数，就像 JavaScript 的 `substr()` 函数一样。 |
| 一日之内的时间 | DAY_PERIOD | `eval_func $out DAY_PERIOD 19:00+0800 12h CN-night;`<br>如果时间在 `19:00+0800` 之后的 12 小时内，则返回 `'CN-night'`。 |

> **注意：** 使用**加粗字体**标记的函数的输出值是一个可能无法打印的二进制字符串。因此你需要使用 `BASE64_ENCODE`、`URL_ENCODE` 或 `HEX_ENCODE` 将其转换为可打印格式。

![eval_func 函数表](../../assets/presigned/pre-17.png)

### 3.3 官方示例

```nginx
eval_func $secret_key SHA256 "mySecret123!";
eval_func $text HEX_ENCODE $secret_key;
# the value of $text should be
# "ad8fdcda140f607697ec80a8c38e86af19f4bb79ee7f7544abcfaadd827901af"

eval_func $aseout ENCRYPT_AES_256_CBC $secret_key $iv $message;
eval_func $hmacout HMAC $secret_key $message SHA256;
eval_func $hmacout1 HMAC_HEXKEY $text $message SHA256;
# $hmacout and $hmacout1 should be equal
```

`eval_func` 属于 nginx **rewrite 模块**。在 CDN Pro 对请求处理的早期阶段中，它将与同一模块中的其他指令一同被执行。

![eval_func 示例](../../assets/presigned/pre-18.png)
