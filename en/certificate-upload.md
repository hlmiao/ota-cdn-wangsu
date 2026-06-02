# SSL Certificate Upload

> Path: CDNPro Console → **Certificate Management** → **SSL Certificates** → **My Certificates**

Upload the customer's SSL/TLS certificate to the Wangsu certificate store and associate it with the accelerated domain.

---

## 1. Prerequisites

| Item | Notes |
| --- | --- |
| Certificate file | `.pem` / `.crt` / `.cer` / `.der` / `.pfx` / `.jks` |
| Private key | Must match the certificate. Not required separately when using `.pfx` / `.jks` that already contains the key |
| Private key password | Required only if the key is encrypted, or `.pfx` / `.jks` is password-protected |
| Accelerated hostname | Must be present in the certificate's SAN |

---

## 2. Upload Steps

1. Open **My Certificates** and click **Add Certificate**.
2. Fill in **Certificate Name**.
3. Choose **Key Algorithm**:
   - **International Standard**: RSA / ECC
   - **SM2** (Chinese national standard)
4. Upload the **Certificate** and **Private Key**; provide the **Private Key Password** if applicable.
5. Under **Associate Domain**, select the accelerated hostname(s) to bind this certificate to.
6. Submit.
