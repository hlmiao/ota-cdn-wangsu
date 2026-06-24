#!/usr/bin/env python3
"""
网宿 CDN Pro 预签名 URL 生成器（OTA 固件下载）

与官方 Edge Logic 配置完全匹配。Edge Logic 侧的校验逻辑（节选）：

    location ~ ^/(\\d+)/([a-f0-9]+)/([fd])(/.+)$ {
        set $token_t $1;          # 过期时间戳(绝对, epoch 秒)
        set $token_sign $2;       # MD5 十六进制签名
        set $mode $3;             # f=文件级 d=目录级
        set $real_path $4;        # 真实路径
        ...
        set $file_str "<SECRET>${real_path}${token_t}";   # 文件级签名串
        set $dir_str  "<SECRET>${parent_dir}${token_t}";  # 目录级签名串
        eval_func $x MD5 ...; eval_func $y HEX_ENCODE ...; # MD5 -> hex
        # COMPARE_INT(token_t, now) 为负 => 过期 => 403
        rewrite ... $real_path break;
        origin_pass myorigin;     # 回源 S3
    }

URL 格式:
    https://<域名>/<token_t>/<sign>/<mode><real_path>
    例: https://ota.example.com/1750681800/2f1a.../f/firmware/v1.2.3/app.bin

签名算法:
    文件级(f): sign = hex(md5(SECRET + real_path + token_t))
    目录级(d): sign = hex(md5(SECRET + parent_dir + token_t))
               parent_dir = real_path 到最后一个 '/' 为止（含 '/'）

要点:
    1) SECRET 必须与 Edge Logic 脚本里的密钥逐字符一致。
    2) token_t 是【绝对过期时间戳】= 当前时间 + ttl。
    3) 服务器与发链端时间需 NTP 同步，否则边界误判。
"""
import argparse
import hashlib
import time

# 演练用示例密钥，与官方 demo 一致；上生产前务必替换，并改为从环境变量/密管读取
DEFAULT_SECRET = "REPLACE_WITH_YOUR_SIGNING_SECRET"


def _md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def parent_dir(real_path: str) -> str:
    """取父目录，到最后一个 '/' 为止（含 '/'）。等价 Edge Logic 的 ^(.*/)[^/]+$"""
    idx = real_path.rfind("/")
    if idx < 0:
        return real_path
    return real_path[: idx + 1]


def sign_url(base_url: str, real_path: str, ttl: int = 1800,
             mode: str = "f", secret: str = DEFAULT_SECRET,
             now: int | None = None) -> str:
    """
    base_url : 如 https://ota.example.com（结尾不带 /）
    real_path: 必须以 / 开头，如 /firmware/v1.2.3/app.bin
    ttl      : 有效期(秒)，OTA 大文件建议留足下载时间
    mode     : 'f' 文件级(仅此文件) | 'd' 目录级(放行该目录下所有文件)
    """
    if not real_path.startswith("/"):
        raise ValueError("real_path 必须以 / 开头")
    if mode not in ("f", "d"):
        raise ValueError("mode 只能是 'f' 或 'd'")

    base_ts = int(now if now is not None else time.time())
    token_t = base_ts + ttl  # 绝对过期时间戳

    if mode == "f":
        sign_str = f"{secret}{real_path}{token_t}"
    else:
        sign_str = f"{secret}{parent_dir(real_path)}{token_t}"

    sign = _md5_hex(sign_str)
    return f"{base_url.rstrip('/')}/{token_t}/{sign}/{mode}{real_path}"


def main() -> None:
    p = argparse.ArgumentParser(description="网宿 CDN Pro 预签名 URL 生成器")
    p.add_argument("base_url", help="加速域名基址，如 https://ota.example.com")
    p.add_argument("real_path", help="真实路径，以 / 开头，如 /firmware/v1.2.3/app.bin")
    p.add_argument("--ttl", type=int, default=1800, help="有效期(秒)，默认 1800")
    p.add_argument("--mode", choices=["f", "d"], default="f",
                   help="f=文件级(默认) d=目录级")
    p.add_argument("--secret", default=DEFAULT_SECRET, help="签名密钥(默认用演练密钥)")
    args = p.parse_args()

    url = sign_url(args.base_url, args.real_path, ttl=args.ttl,
                   mode=args.mode, secret=args.secret)
    print(url)


if __name__ == "__main__":
    main()
