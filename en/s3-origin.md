# AWS S3 Origin

> Path: CDNPro Console → **Properties** → create or edit a Property

Configure an AWS S3 bucket as a CDNPro origin. S3 is **not** a separate "origin type" — use a regular HTTPS origin and enable **Authentication = AWS S3** in the advanced configuration; the edge nodes perform the SigV4 signing.

---

## 1. Prerequisites

| Item | Notes |
| --- | --- |
| S3 bucket name | e.g. `my-bucket` |
| Bucket region | e.g. `us-east-1` |
| Bucket access hostname | `my-bucket.s3.us-east-1.amazonaws.com` |
| Access Key ID | IAM access key |
| Secret Access Key | Stored in **Secrets / Vault** |
| Accelerated hostname | Certificate already uploaded |
| Edge hostname | `xxx.qtlcdn.com`, created via **Edge Hostnames** |

---

## 2. Steps

### 2.1 Create the Edge Hostname

**Edge Hostnames** → **Create** → select the TLS certificate → produces `xxx.qtlcdn.com`.

### 2.2 Store the Secret in Vault

**Configuration** → **Secrets / Vault** → **Add Secret**:

- **Name**: e.g. `s3-my-bucket-sk`
- **Type**: `Secret String`
- **Value**: the Secret Access Key

### 2.3 Create the Property

1. **Hostname**: the accelerated hostname; select the edge hostname and the uploaded certificate.
2. **Origin**:
   - **Origin Type**: `HTTPS`
   - **Origin Hostname**: `my-bucket.s3.us-east-1.amazonaws.com`
   - **Origin Port**: `443`
3. **Host Header**: must be set to the bucket access hostname `my-bucket.s3.us-east-1.amazonaws.com`. Otherwise S3 returns `Bucket not found`.
4. **Advanced Configuration → Origin Authentication**:
   - **Authentication Type**: `AWS S3`
   - **Region**: the bucket's region
   - **Access Key ID**: the AK
   - **Secret Access Key**: select the Vault entry from §2.2

### 2.4 Deploy

Submit, then **Deploy to Staging** → verify → **Deploy to Production**.

Point the accelerated hostname's DNS to `xxx.qtlcdn.com` via CNAME.
