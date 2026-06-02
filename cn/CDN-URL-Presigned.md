# CDN URL Presigned（URL 预签名）

> 入口：CDNPro 控制台 → **Properties** → 选择 Property → **Edge Logic**

通过 Edge Logic 实现限时 + 路径绑定的 URL 预签名校验。网宿不提供官方 SDK，签发端由业务方自行实现，边缘端用 `eval_func` 指令完成校验。

---

## 1. URL 格式

```
https://files.example.com/{exp}/{sign}/{mode}/{real_path}
```

- `exp`：Unix 秒级过期时间戳
- `sign`：32 位十六进制签名
- `mode`：`f` 文件级 / `d` 目录级
- `real_path`：真实回源路径

---

## 2. 签名算法

记 `SECRET` 为业务方与 CDN 共享的密钥，`exp` 为过期时间戳：

- **文件级**：`sign = HEX( MD5( SECRET + real_path + exp ) )`
- **目录级**：`parent = real_path 去掉最后一段`；`sign = HEX( MD5( SECRET + parent + exp ) )`

---

## 3. Edge Logic 校验脚本

```nginx
location ~ ^/(\d+)/([a-f0-9]+)/([fd])(/.+)$ {
    set $token_t    $1;
    set $token_sign $2;
    set $mode       $3;
    set $real_path  $4;

    # 提取父目录
    set $parent_dir $real_path;
    if ($real_path ~ "^(.*/)[^/]+$") {
        set $parent_dir $1;
    }

    # 文件级签名
    set $file_str "__SECRET__${real_path}${token_t}";
    eval_func $file_md5_bin MD5        $file_str;
    eval_func $file_sign    HEX_ENCODE $file_md5_bin;

    # 目录级签名
    set $dir_str  "__SECRET__${parent_dir}${token_t}";
    eval_func $dir_md5_bin  MD5        $dir_str;
    eval_func $dir_sign     HEX_ENCODE $dir_md5_bin;

    # 按 mode 比对
    set $check_f "f${file_sign}";
    set $check_d "d${dir_sign}";
    set $expect  "${mode}${token_sign}";
    set $auth "0";
    if ($check_f = $expect) { set $auth "1"; }
    if ($check_d = $expect) { set $auth "1"; }
    if ($auth = "0") { return 403; }

    # 过期校验
    if ($msec ~ "^(\d+)") { set $now $1; }
    eval_func $cmp COMPARE_INT $token_t $now;
    if ($cmp ~ "^-") { return 403; }

    # 去掉签名前缀回源
    rewrite ^/\d+/[a-f0-9]+/[fd](/.+)$ $1 break;
    origin_pass myorigin;
}

location / {
    return 403;
}
```

`eval_func` 函数族：`MD5` / `SHA256` / `HMAC` / `HMAC_HEXKEY` / `HEX_ENCODE` / `BASE64_ENCODE` / `URL_ENCODE` / `COMPARE_INT` / `CALC_INT` / `ENCRYPT_AES_256_CBC` / `RSA_SIGN` / `SUBSTR`。
