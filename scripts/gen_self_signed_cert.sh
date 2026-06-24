#!/usr/bin/env bash
#
# 生成演练用自签证书（mini-CA 模式）
# 产物可直接用于网宿 CDN Pro「上传证书」表单的三个字段：
#   - 证书文件 (Certificate)  -> server.crt
#   - CA 文件   (CA)           -> ca.crt
#   - 私钥文件  (Private Key)  -> server.key
#
# ⚠️ 仅用于跑通「上传 -> 绑定域名 -> 验证」流程的演练。
#    自签证书不被 OTA 设备/浏览器信任，禁止上生产。
#
# 用法:
#   ./gen_self_signed_cert.sh <域名>
#   例: ./gen_self_signed_cert.sh ota-test.example.com
#
set -euo pipefail

DOMAIN="${1:-ota-test.example.com}"
DAYS_CA=3650
DAYS_CERT=825   # 公共 CA 上限是 825 天，这里保持一致便于贴近真实

# 输出目录: 脚本所在仓库根的 certs/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/certs"
mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

echo "==> 生成根 CA (ca.key / ca.crt)"
openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS_CA" \
  -subj "/C=CN/O=OTA Dryrun Test CA/CN=OTA Dryrun Root CA" \
  -out ca.crt

echo "==> 生成服务器私钥 (server.key)"
openssl genrsa -out server.key 2048 2>/dev/null

echo "==> 生成服务器 CSR (含 SAN: $DOMAIN)"
openssl req -new -key server.key \
  -subj "/C=CN/O=OTA Dryrun Test/CN=$DOMAIN" \
  -out server.csr

cat > server.ext <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=@alt_names

[alt_names]
DNS.1=$DOMAIN
EOF

echo "==> 用根 CA 签发服务器证书 (server.crt)"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days "$DAYS_CERT" -sha256 -extfile server.ext -out server.crt 2>/dev/null

# 完整链（server + ca），部分场景需要
cat server.crt ca.crt > fullchain.crt

# 清理中间产物
rm -f server.csr server.ext ca.srl

echo ""
echo "==> 完成，产物在: $OUT_DIR"
echo "    server.crt    证书文件   -> 上传到「证书文件」字段"
echo "    ca.crt        CA 证书    -> 上传到「CA 文件」字段"
echo "    server.key    私钥文件   -> 上传到「私钥文件」字段"
echo "    fullchain.crt 完整链     -> 备用"
echo ""
echo "==> 校验证书与私钥是否配对 (两行 md5 必须一致):"
echo -n "    cert key md5: "; openssl x509 -noout -modulus -in server.crt | openssl md5
echo -n "    priv key md5: "; openssl rsa  -noout -modulus -in server.key | openssl md5
echo ""
echo "==> 证书摘要:"
openssl x509 -in server.crt -noout -subject -issuer -dates -ext subjectAltName
