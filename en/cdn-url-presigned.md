# CDN URL Presigned

> Path: CDNPro Console → **Properties** → select a Property → **Edge Logic**

Implement time-limited, path-bound URL signature validation using Edge Logic. Wangsu does not provide an official SDK — the signing side is implemented by the customer; the edge side validates with the `eval_func` directive.

---

## 1. URL Format

```
https://files.example.com/{exp}/{sign}/{mode}/{real_path}
```

- `exp`: Unix epoch expiration timestamp (seconds)
- `sign`: 32-character hex signature
- `mode`: `f` (file-level) or `d` (directory-level)
- `real_path`: actual origin path

---

## 2. Signing Algorithm

Let `SECRET` be the shared key between the signing side and the CDN, and `exp` the expiration timestamp:

- **File-level**: `sign = HEX( MD5( SECRET + real_path + exp ) )`
- **Directory-level**: `parent = real_path` with the last segment stripped; `sign = HEX( MD5( SECRET + parent + exp ) )`

---

## 3. Edge Logic Validation Script

```nginx
location ~ ^/(\d+)/([a-f0-9]+)/([fd])(/.+)$ {
    set $token_t    $1;
    set $token_sign $2;
    set $mode       $3;
    set $real_path  $4;

    # Extract the parent directory
    set $parent_dir $real_path;
    if ($real_path ~ "^(.*/)[^/]+$") {
        set $parent_dir $1;
    }

    # File-level signature
    set $file_str "__SECRET__${real_path}${token_t}";
    eval_func $file_md5_bin MD5        $file_str;
    eval_func $file_sign    HEX_ENCODE $file_md5_bin;

    # Directory-level signature
    set $dir_str  "__SECRET__${parent_dir}${token_t}";
    eval_func $dir_md5_bin  MD5        $dir_str;
    eval_func $dir_sign     HEX_ENCODE $dir_md5_bin;

    # Compare against the requested mode
    set $check_f "f${file_sign}";
    set $check_d "d${dir_sign}";
    set $expect  "${mode}${token_sign}";
    set $auth "0";
    if ($check_f = $expect) { set $auth "1"; }
    if ($check_d = $expect) { set $auth "1"; }
    if ($auth = "0") { return 403; }

    # Expiration check
    if ($msec ~ "^(\d+)") { set $now $1; }
    eval_func $cmp COMPARE_INT $token_t $now;
    if ($cmp ~ "^-") { return 403; }

    # Strip the signature prefix and forward to origin
    rewrite ^/\d+/[a-f0-9]+/[fd](/.+)$ $1 break;
    origin_pass myorigin;
}

location / {
    return 403;
}
```

`eval_func` function family: `MD5` / `SHA256` / `HMAC` / `HMAC_HEXKEY` / `HEX_ENCODE` / `BASE64_ENCODE` / `URL_ENCODE` / `COMPARE_INT` / `CALC_INT` / `ENCRYPT_AES_256_CBC` / `RSA_SIGN` / `SUBSTR`.
