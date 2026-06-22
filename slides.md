---
marp: true
theme: default
paginate: true
style: |
  @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;700;800;900&display=swap');

  :root {
    --navy: #0d2d6e;
    --blue: #1565c0;
    --light: #e3f2fd;
    --white: #ffffff;
  }

  section {
    font-family: 'Be Vietnam Pro', 'Segoe UI', Arial, sans-serif;
    background: #f5f8ff;
    color: #1a1a2e;
    padding: 48px 56px 40px 56px;
    overflow: hidden;
    position: relative;
  }

  /* Blue geometric shapes on right (3 angled bars) */
  section::before {
    content: '';
    position: absolute;
    right: -40px;
    top: 0;
    width: 340px;
    height: 110%;
    background:
      linear-gradient(160deg,
        transparent 0%, transparent 18%,
        #1565c0 18%, #1565c0 34%,
        transparent 34%, transparent 40%,
        #90caf9 40%, #90caf9 58%,
        transparent 58%, transparent 64%,
        #0d2d6e 64%, #0d2d6e 82%,
        transparent 82%
      );
    opacity: 0.25;
    z-index: 0;
  }

  /* Bottom blue bar */
  section::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 7px;
    background: linear-gradient(90deg, #0d2d6e, #1565c0, #42a5f5);
    z-index: 10;
  }

  /* UIT logo text — override per slide not needed, always show */
  section > *:first-child::before {
    display: none;
  }

  h1 {
    color: var(--navy);
    font-size: 40px;
    font-weight: 900;
    margin: 0 0 18px 0;
    line-height: 1.2;
    position: relative;
    z-index: 1;
  }

  h2 {
    color: var(--navy);
    font-size: 30px;
    font-weight: 800;
    margin: 0 0 16px 0;
    position: relative;
    z-index: 1;
  }

  h3 {
    color: var(--blue);
    font-size: 20px;
    font-weight: 700;
    margin: 10px 0 6px 0;
    position: relative;
    z-index: 1;
  }

  p, li, table, pre, code {
    position: relative;
    z-index: 1;
  }

  ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  /* Dark navy content box  */
  .box {
    background: var(--navy);
    color: white;
    padding: 22px 30px;
    border-radius: 14px;
    max-width: 62%;
    position: relative;
    z-index: 1;
  }

  .box li {
    font-size: 21px;
    font-weight: 600;
    padding: 8px 0;
    display: flex;
    align-items: center;
    gap: 14px;
    border-bottom: 1px solid rgba(255,255,255,0.12);
  }
  .box li:last-child { border-bottom: none; }
  .box li::before {
    content: '✓';
    min-width: 28px;
    height: 28px;
    background: white;
    color: var(--navy);
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 900;
    font-size: 15px;
    flex-shrink: 0;
  }

  /* Two-column */
  .cols {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
    position: relative;
    z-index: 1;
    margin-top: 8px;
  }
  .cols-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
    position: relative;
    z-index: 1;
  }

  /* Card component */
  .card {
    background: white;
    border: 2px solid #bbdefb;
    border-left: 5px solid var(--blue);
    border-radius: 10px;
    padding: 16px 18px;
    font-size: 15px;
  }
  .card strong { color: var(--navy); display: block; margin-bottom: 6px; font-size: 17px; }

  /* Image placeholder */
  .img {
    background: #e3f2fd;
    border: 2px dashed var(--blue);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--blue);
    font-size: 15px;
    font-style: italic;
    min-height: 160px;
    text-align: center;
    position: relative;
    z-index: 1;
  }

  /* Highlight pill */
  .pill {
    display: inline-block;
    background: var(--navy);
    color: white;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 14px;
    font-weight: 600;
    margin: 2px 3px;
  }

  /* Fact row */
  .fact {
    background: white;
    border-left: 5px solid var(--blue);
    padding: 10px 16px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
    font-size: 17px;
    position: relative;
    z-index: 1;
  }
  .fact strong { color: var(--navy); }

  /* Result metric */
  .metric {
    background: var(--navy);
    color: white;
    border-radius: 12px;
    padding: 18px 16px;
    text-align: center;
  }
  .metric .num { font-size: 36px; font-weight: 900; color: #90caf9; }
  .metric .label { font-size: 14px; margin-top: 4px; opacity: 0.9; }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 15px;
    z-index: 1;
    position: relative;
  }
  th { background: var(--navy); color: white; padding: 8px 12px; font-weight: 700; }
  td { padding: 7px 12px; border-bottom: 1px solid #e0e0e0; }
  tr:nth-child(even) td { background: #f0f7ff; }

  pre {
    background: #0d1b3e;
    color: #e3f2fd;
    padding: 14px 18px;
    border-radius: 8px;
    font-size: 13px;
    z-index: 1;
    position: relative;
  }
  code { background: #e3f2fd; color: #0d2d6e; padding: 2px 7px; border-radius: 4px; font-size: 14px; }

  /* Page number */
  section[data-marpit-pagination]::after {
    content: attr(data-marpit-pagination) ' / ' attr(data-marpit-pagination-total);
    position: absolute;
    bottom: 14px;
    right: 20px;
    font-size: 13px;
    color: #888;
    z-index: 20;
    background: none;
    height: auto;
    width: auto;
  }

  /* Title slide override */
  section.title-slide {
    background: linear-gradient(135deg, #0d2d6e 0%, #1565c0 60%, #42a5f5 100%);
    color: white;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  section.title-slide::before { display: none; }
  section.title-slide h1 { color: white; font-size: 38px; }
  section.title-slide h2 { color: #bbdefb; font-size: 22px; font-weight: 400; border: none; }
  section.title-slide p { color: #e3f2fd; position: relative; z-index: 1; }

  /* Section divider slide */
  section.divider {
    background: var(--navy);
    color: white;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  section.divider::before { display: none; }
  section.divider h1 { color: white; font-size: 52px; }
  section.divider p { color: #90caf9; font-size: 20px; position: relative; z-index: 1; }
---

<!-- ===================== SLIDE 1: BÌA ===================== -->
<!-- _class: title-slide -->
<!-- _paginate: false -->

<div style="position:absolute;top:20px;right:24px;text-align:right;z-index:10">
<span style="font-size:11px;color:#bbdefb;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM<br>Trường ĐH Công nghệ Thông tin — UIT</span>
</div>

# AI-Powered DevOps Automation Platform

## Tự động hóa CI/CD và SRE bằng AI với MCP Server

<br>

<div style="background:rgba(255,255,255,0.15);padding:20px 28px;border-radius:12px;max-width:600px;z-index:1;position:relative">

**Sinh viên:** Võ Trung Kiên

**Môn học:** Thực hành DevOps / Vận hành hệ thống

**Công nghệ:** Python · MCP · Jenkins · Kubernetes · Ollama · Prometheus

</div>

---

<!-- ===================== SLIDE 2: NỘI DUNG ===================== -->
<!-- _paginate: false -->

<div style="position:absolute;top:20px;right:24px;text-align:right;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

# Nội dung

<div class="box">

- Giới thiệu chung
- Công nghệ sử dụng
- Triển khai hệ thống
- Kết quả đạt được

</div>

---

<!-- ===================== SLIDE 3: GIỚI THIỆU — VẤN ĐỀ ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Giới thiệu — Bài toán thực tế

<div class="cols">
<div>

<div class="fact"><strong>❌ Pipeline thất bại</strong> → kỹ sư phải đọc hàng nghìn dòng log thủ công</div>
<div class="fact"><strong>❌ Incident xảy ra</strong> → cần 15–30 phút để xác định nguyên nhân</div>
<div class="fact"><strong>❌ Deploy thủ công</strong> → rủi ro human error, không kiểm tra tài nguyên trước</div>
<div class="fact"><strong>❌ Alert Prometheus</strong> → quá nhiều, khó phân loại ưu tiên xử lý</div>

<br>

<div style="background:#0d2d6e;color:white;padding:14px 18px;border-radius:10px;font-size:17px;font-weight:600;z-index:1;position:relative">
💡 Giải pháp: Để <strong style="color:#90caf9">AI Agent</strong> tự đọc log, điều tra nguyên nhân và thực hiện remediation thay con người
</div>

</div>
<div>

<div class="img" style="min-height:280px">📸 Chèn ảnh: Jenkins Stage View với nhiều build đỏ liên tiếp (screenshot thực tế)</div>

</div>
</div>

---

<!-- ===================== SLIDE 4: MỤC TIÊU ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Những gì đã xây dựng

<div class="cols">
<div>

<div class="box" style="max-width:100%">

- MCP Server với **14 DevOps tools**
- AI Agent với **vòng lặp ReAct** tự động
- **2 Jenkins pipeline** CI/CD hoàn chỉnh
- **Smart CD Approval** — AI gatekeeper
- **Tự động điều tra** lỗi Jenkins & K8s
- Toàn bộ infra bằng **Terraform + Ansible**
- Deploy lên **K3s** (Kubernetes nhẹ)

</div>

</div>
<div>

<div style="font-size:15px;color:#555;margin-bottom:10px;z-index:1;position:relative">Hai ứng dụng trong hệ thống:</div>

<div class="card">
<strong>🔷 MCP Server (mcp-server-app)</strong>
Chính là hệ thống AI DevOps — được quản lý bởi pipeline của chính nó
</div>
<br>
<div class="card">
<strong>🌤️ Weather App (meteo-hist)</strong>
Ứng dụng Streamlit — mục tiêu deploy để demo toàn bộ luồng CI/CD + AI Gatekeeper
</div>

</div>
</div>

---

<!-- ===================== SLIDE 5: CÔNG NGHỆ ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Công nghệ sử dụng

<div class="cols-3" style="margin-top:12px">

<div class="card">
<strong>🤖 AI & LLM</strong>
• Ollama — Qwen 2.5 14B (local)<br>
• LangChain OllamaLLM<br>
• ReAct prompting pattern<br>
• MCP Protocol (Anthropic)
</div>

<div class="card">
<strong>⚙️ CI/CD & Container</strong>
• Jenkins (Groovy pipeline)<br>
• Docker + Docker Hub<br>
• Trivy (CVE scanning)<br>
• SonarQube + Checkov
</div>

<div class="card">
<strong>☸️ Orchestration</strong>
• K3s (lightweight K8s)<br>
• kubectl over SSH tunnel<br>
• Prometheus + AlertManager<br>
• Ngrok (webhook tunnel)
</div>

<div class="card">
<strong>🐍 Backend</strong>
• Python 3.11<br>
• FastMCP (MCP server)<br>
• FastAPI + Uvicorn<br>
• prompt_toolkit (CLI)
</div>

<div class="card">
<strong>🏗️ IaC</strong>
• Terraform (Azure infra)<br>
• Ansible (VM config)<br>
• Azure VM Standard_D2s_v3<br>
• K8s YAML manifests
</div>

<div class="card">
<strong>📣 Notification</strong>
• Discord Webhook<br>
• Jenkins build webhook<br>
• Prometheus AlertManager<br>
• Ngrok auto-register
</div>

</div>

---

<!-- ===================== SLIDE 6: KIẾN TRÚC ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Kiến trúc hệ thống

<div class="cols">
<div>

<pre style="font-size:12px;line-height:1.6">
TRIGGERS
  Jenkins Webhook | Prometheus | CLI
          │
          ▼
    agent.py  (FastAPI :5000)
    ┌──────────────────────────┐
    │ Ollama Qwen 2.5 14B      │
    │  THOUGHT → ACTION        │
    │        → OBSERVATION     │
    └──────────────────────────┘
          │ MCP Protocol
          ▼
    main.py  (FastMCP — 14 tools)
    Jenkins │ K8s │ Files │ Metrics
          │
          ▼  HTTP / SSH Tunnel
    Azure VM  20.89.52.40
    Jenkins :8080 | K3s | Prometheus
          │
          ▼
    Discord  (Final Answer report)
</pre>

</div>
<div>

<div class="img" style="min-height:300px">📸 Chèn ảnh: Sơ đồ kiến trúc đẹp (vẽ bằng draw.io hoặc Excalidraw)</div>

</div>
</div>

---

<!-- ===================== SLIDE 7: MCP SERVER ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## MCP Server — Bộ 14 DevOps Tools

<div class="cols">
<div>

| Nhóm | Tool | Tác dụng |
|------|------|----------|
| **Jenkins** | `get_build_overview` | Xem trạng thái các stages |
| | `get_jenkins_logs` | Lấy log từng stage (3 lớp) |
| | `trigger_jenkins_and_wait` | Kích hoạt build và chờ kết quả |
| **K8s** | `check_system_health` | Liệt kê pods + trạng thái |
| | `restart_pod` | Force restart pod |
| | `scale_deployment` | Scale replicas (1–5) |
| | `rollback` | Quay về phiên bản trước |
| | `get_app_logs` | Lấy logs pod thực tế |
| **Code** | `search_in_file` | Grep với context lines |
| | `read_project_file` | Đọc source code có số dòng |
| **Infra** | `fetch_metrics` | CPU% + RAM% từ Prometheus |
| | `get_terraform_plan` | Chạy terraform plan |

</div>
<div>

<div class="img" style="min-height:160px;margin-bottom:14px">📸 Chèn ảnh: Terminal hiển thị Claude Desktop / chatbot đang gọi một MCP tool</div>

<div class="card">
<strong>Thiết kế 3-layer cho Jenkins logs</strong>
1. wfapi node-log API (chính xác nhất)<br>
2. Regex từ console text (fallback)<br>
3. Raw console (last resort)<br>
→ Luôn cắt từ <strong>ĐẦU</strong> để giữ error message
</div>

</div>
</div>

---

<!-- ===================== SLIDE 8: AI AGENT REACT ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## AI Agent — Vòng lặp ReAct

<div class="cols">
<div>

<pre style="font-size:13px;line-height:1.7">
SYSTEM PROMPT
(vai trò + tools + playbook điều tra)
            │
┌───── Lặp đến max_steps ──────┐
│                               │
│  THOUGHT: Lý luận ≤ 4 câu    │
│      ↓                        │
│  ACTION: Tên tool cần gọi     │
│      ↓                        │
│  ACTION INPUT: {"key": val}   │
│      ↓                        │
│  OBSERVATION: kết quả tool    │
│  (tối đa 6000 ký tự)          │
└───────────────────────────────┘
            │
    "Final Answer: ..."
            │
    Discord Notification
</pre>

</div>
<div>

<div style="z-index:1;position:relative">

**5 chế độ hoạt động:**

<div class="fact"><strong>run_investigation()</strong> → Jenkins FAILURE webhook</div>
<div class="fact"><strong>run_metrics_investigation()</strong> → Prometheus FIRING</div>
<div class="fact"><strong>run_success_report()</strong> → Jenkins SUCCESS</div>
<div class="fact"><strong>run_smart_cd_approval()</strong> → PENDING_APPROVAL</div>
<div class="fact"><strong>run_chatbot()</strong> → CLI user input</div>

<br>

<div style="background:#0d2d6e;color:white;padding:12px 16px;border-radius:8px;font-size:15px">
🔒 <strong>llm_lock</strong> — ngăn nhiều AI task chạy đồng thời<br>
🧠 Model: <strong>Qwen 2.5 14B</strong> tự điều chỉnh context window theo RAM
</div>

</div>

</div>
</div>

---

<!-- ===================== SLIDE 9: PIPELINE 1 ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## CI/CD Pipeline — mcp-server-pipeline

<div class="cols">
<div>

```
Checkout & Metadata
  └─ IMAGE_TAG = {Build#}-{GitSHA}
         ↓
Unit Test  (pytest)
         ↓
Security Analysis  [song song]
  ├─ SonarQube  (code quality)
  └─ Checkov    (IaC security)
         ↓
Build & Push Docker
  └─ kienvo2110/mcp-server-app:{tag}
         ↓
Deploy to K3s  (namespace: staging)
  └─ kubectl apply + rollout --timeout=120s
         │
   [FAIL] → auto rollback undo
   [PASS] → AI gửi health report → Discord
```

</div>
<div>

<div class="img" style="min-height:260px">📸 Chèn ảnh: Jenkins Stage View của mcp-server-pipeline (build thành công, tất cả xanh)</div>

<div class="card" style="margin-top:14px">
<strong>Image tagging strategy</strong>
<code>{BUILD_NUMBER}-{GIT_SHA}</code> → mỗi build traceable về đúng commit, dễ rollback chính xác
</div>

</div>
</div>

---

<!-- ===================== SLIDE 10: PIPELINE 2 + SMART CD ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## CI/CD Pipeline — weather-app + AI Gatekeeper

<div class="cols">
<div>

```
Checkout Code
      ↓
Build Docker Image
  └─ trgqn/meteo-hist:latest
      ↓
Security Scan  (Trivy)
  └─ --severity CRITICAL --exit-code 1
  └─ Fail build nếu có CVE nghiêm trọng
      ↓
Push to Docker Hub
      ↓
★ Smart CD Approval (AI Gatekeeper) ★
  ├─ Gửi webhook PENDING_APPROVAL
  ├─ AI đọc K8s YAML + kiểm tra cluster
  ├─ Gửi báo cáo rủi ro → Discord
  └─ Pipeline PAUSE chờ human click OK
      ↓ (Approved)
Deploy to K3s
```

</div>
<div>

<div class="img" style="min-height:170px;margin-bottom:12px">📸 Chèn ảnh: Jenkins stage view weather-app-pipeline (các ô đỏ ở Security Scan)</div>

<div style="background:#0d2d6e;color:white;padding:14px 18px;border-radius:10px;font-size:15px;z-index:1;position:relative">
⭐ <strong>Điểm độc đáo:</strong> AI là <em>cố vấn rủi ro</em> — phân tích manifest K8s, kiểm tra tài nguyên cluster, gửi báo cáo cho người trước khi deploy. Human vẫn là người quyết định cuối.
</div>

</div>
</div>

---

<!-- ===================== SLIDE 11: SMART CD DETAIL ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Smart CD Approval — Luồng thực tế

<div class="cols">
<div>

**Jenkins gửi:**
```json
{
  "job_name": "weather-app-pipeline",
  "status": "PENDING_APPROVAL",
  "k8s": "weather-app/k8s"
}
```

**AI thực hiện:**
<div class="fact">① <strong>list_directory</strong>("weather-app/k8s") → tìm file YAML</div>
<div class="fact">② <strong>read_project_file</strong>("deployment.yaml") → đọc manifest</div>
<div class="fact">③ <strong>check_system_health</strong>("default") → trạng thái pods</div>
<div class="fact">④ <strong>fetch_metrics</strong>() → CPU 23%, RAM 61%</div>

</div>
<div>

**Báo cáo gửi về Discord:**

<div style="background:#2c2f33;color:#dcddde;padding:14px 18px;border-radius:10px;font-size:14px;z-index:1;position:relative;font-family:monospace">
✅ <strong style="color:#43b581">APPROVE với điều kiện:</strong><br><br>
• imagePullPolicy: Always → sẽ pull latest<br>
• CPU 23%, RAM 61% → đủ tài nguyên<br>
• Pod đang Running → rollout restart an toàn<br><br>
⚠️ <strong style="color:#faa61a">Khuyến nghị:</strong><br>
Pin image tag thay vì :latest để dễ rollback
</div>

<br>

<div class="img" style="min-height:80px">📸 Chèn ảnh: Discord message thực tế với báo cáo AI</div>

</div>
</div>

---

<!-- ===================== SLIDE 12: TỰ ĐỘNG ĐIỀU TRA LỖI ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Tự động Điều tra Lỗi — Build #68 thực tế

<div class="cols">
<div>

**Trigger:**

```json
POST /webhook
{
  "job_name": "weather-app-pipeline",
  "build_number": "68",
  "status": "FAILURE"
}
```

**ReAct loop thực thi:**

<div class="fact">① <code>get_build_overview()</code> → Stage "Security Scan (Trivy)": FAILED</div>
<div class="fact">② <code>get_jenkins_logs("Security Scan")</code> → tìm thấy CVE CRITICAL</div>
<div class="fact">③ <code>search_in_file("Dockerfile", "python")</code> → base image</div>
<div class="fact">④ <code>read_project_file("Dockerfile")</code> → xác nhận dòng FROM</div>

</div>
<div>

<div class="img" style="min-height:150px;margin-bottom:12px">📸 Chèn ảnh: Build #68 trên Jenkins — stage Trivy đỏ, thời gian 3m 26s</div>

<div style="background:#2c2f33;color:#dcddde;padding:12px 16px;border-radius:10px;font-size:13px;z-index:1;position:relative;font-family:monospace">
❌ <strong style="color:#f04747">Root cause: CVE trong base image</strong><br><br>
libexpat1 2.4.7 → CVE-2023-52425<br>
CVSS 9.8 — Remote Code Execution<br><br>
✅ <strong style="color:#43b581">Fix:</strong> Cập nhật Dockerfile:<br>
FROM python:3.12-slim<br>
→ thêm RUN apt-get upgrade -y<br><br>
⏱ Thời gian điều tra: ~90 giây
</div>

</div>
</div>

---

<!-- ===================== SLIDE 13: INFRASTRUCTURE AS CODE ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Infrastructure as Code — Toàn bộ tự động hóa

<div class="cols">
<div>

**Terraform** — Provisioning Azure

```hcl
# terraform-jenkins/main.tf
resource "azurerm_linux_virtual_machine" {
  name  = "Jenkins-DevOps-VM"
  size  = "Standard_D2s_v3"
  # 2 vCPU, 8GB RAM — Japan East

  # Firewall: SSH + Jenkins :8080
  # chỉ từ CIDR được whitelist
}
```
→ `terraform apply` = toàn bộ Azure infra

**Ansible** — Configuration Management

```yaml
# ansible/playbook.yml
tasks:
  - Install Docker
  - Start SonarQube  (:9000)
  - Install K3s  (lightweight K8s)
  - Set kubeconfig permissions
```
→ `ansible-playbook` = VM sẵn sàng hoàn toàn

</div>
<div>

<div class="img" style="min-height:160px;margin-bottom:12px">📸 Chèn ảnh: Azure Portal — VM đang chạy, hoặc terminal terraform apply thành công</div>

<div class="box" style="max-width:100%;font-size:16px">

- Toàn bộ infra **reproducible** — destroy và rebuild trong < 10 phút
- **Không config thủ công** trên VM — mọi thứ qua Ansible
- K3s chạy trên cùng VM với Jenkins — tiết kiệm chi phí

</div>

</div>
</div>

---

<!-- ===================== SLIDE 14: KẾT QUẢ ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Kết quả đạt được

<div class="cols-3" style="margin-bottom:16px">

<div class="metric">
<div class="num">14</div>
<div class="label">DevOps tools<br>trong MCP Server</div>
</div>

<div class="metric">
<div class="num">5</div>
<div class="label">Chế độ AI Agent<br>(webhook + CLI)</div>
</div>

<div class="metric">
<div class="num">~90s</div>
<div class="label">Thời gian điều tra<br>lỗi CI/CD tự động</div>
</div>

</div>

<div class="cols">
<div>

<div class="box" style="max-width:100%;font-size:16px">

- ✓ AI **tự động điều tra** lỗi Jenkins, gửi báo cáo Discord
- ✓ **Smart CD Approval** hoạt động end-to-end
- ✓ **Tự động rollback** khi deploy thất bại
- ✓ Prometheus webhook → AI xử lý infrastructure alert
- ✓ **CLI Chatbot** hỏi đáp về hệ thống real-time
- ✓ Toàn bộ infra được IaC hoá (Terraform + Ansible)

</div>

</div>
<div>

<div class="img" style="min-height:180px">📸 Chèn ảnh: Tổng hợp — Jenkins xanh + Discord báo cáo AI + K8s pods running</div>

</div>
</div>

---

<!-- ===================== SLIDE 15: KẾT QUẢ CHI TIẾT ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Kết quả đạt được — So sánh trước & sau

<div class="cols">
<div>

| Tình huống | Thủ công | **Với AI Agent** |
|------------|----------|-----------------|
| Build Jenkins lỗi | 15–30 phút đọc log | **~90 giây** |
| Alert CPU/RAM cao | 10–20 phút điều tra | **~2 phút** |
| Review K8s trước deploy | Không làm hoặc bỏ qua | **Tự động — có báo cáo** |
| Rollback khi crash | Gõ lệnh thủ công | **Tự động trong pipeline** |
| Hỏi trạng thái hệ thống | SSH vào server kiểm tra | **Hỏi chatbot bằng tiếng Việt** |

<br>

<div class="box" style="max-width:100%;font-size:15px">

- ✓ Điều tra đúng nguyên nhân lỗi **Trivy CVE** qua nhiều build liên tiếp
- ✓ Smart CD Approval **hoạt động end-to-end** — webhook → AI → Discord → human decision
- ✓ Chatbot CLI trả lời câu hỏi về **cả 2 namespace** K8s chính xác
- ✓ Ngrok **tự đăng ký** vào AlertManager K3s mỗi lần khởi động

</div>

</div>
<div>

<div class="img" style="min-height:200px;margin-bottom:12px">📸 Chèn ảnh: Discord hiển thị Final Answer của AI — root cause + hướng fix rõ ràng</div>

<div class="img" style="min-height:120px">📸 Chèn ảnh: Terminal CLI chatbot đang trả lời câu hỏi về pod health</div>

</div>
</div>

---

<!-- ===================== SLIDE 16: HƯỚNG PHÁT TRIỂN ===================== -->
<div style="position:absolute;top:20px;right:24px;z-index:10;font-size:11px;color:#1565c0;font-weight:700">ĐẠI HỌC QUỐC GIA TP.HCM | UIT</div>

## Hướng phát triển & Khắc phục

<div class="cols">
<div>

### Hạn chế hiện tại cần khắc phục

<div class="card" style="margin-bottom:10px">
<strong>⚠️ requirements.txt thiếu dependencies</strong>
fastapi, uvicorn, langchain-ollama, pyngrok... chưa được liệt kê → <em>pip install -r requirements.txt</em> sẽ thiếu gói khi deploy mới
</div>

<div class="card" style="margin-bottom:10px">
<strong>⚠️ Webhook không có xác thực</strong>
<em>/webhook</em> và <em>/prometheus-webhook</em> không require token → bất kỳ ai biết URL ngrok có thể trigger AI
</div>

<div class="card" style="margin-bottom:10px">
<strong>⚠️ Container startup hack</strong>
K8s dùng <em>python main.py & sleep loop</em> → nếu MCP server crash, container không tự restart
</div>

<div class="card">
<strong>⚠️ agent.py quá lớn (1016 dòng)</strong>
Trộn lẫn FastAPI, CLI, AI logic, Discord, signal handler → khó test và maintain
</div>

</div>
<div>

### Roadmap phát triển

<div class="fact" style="margin-bottom:8px"><strong>Ngắn hạn</strong> — Bổ sung JWT auth cho webhook endpoints, fix requirements.txt đầy đủ</div>

<div class="fact" style="margin-bottom:8px"><strong>Ngắn hạn</strong> — Tách agent.py thành modules: <em>webhook.py / chatbot.py / investigator.py</em></div>

<div class="fact" style="margin-bottom:8px"><strong>Trung hạn</strong> — Lưu lịch sử điều tra vào Vector DB → AI học từ các incident cũ</div>

<div class="fact" style="margin-bottom:8px"><strong>Trung hạn</strong> — Thêm Helm chart thay raw YAML, hỗ trợ multi-replica MCP server</div>

<div class="fact"><strong>Dài hạn</strong> — Nâng cấp lên Claude API / GPT-4 để tăng độ chính xác điều tra; thêm khả năng AI tự apply code fix lên GitHub</div>

</div>
</div>

---

<!-- ===================== SLIDE 17: Q&A ===================== -->
<!-- _class: divider -->
<!-- _paginate: false -->

# Hỏi & Đáp

Cảm ơn thầy/cô và các bạn đã theo dõi!

<br>

<div style="background:rgba(255,255,255,0.12);padding:18px 24px;border-radius:12px;font-size:17px;max-width:620px;position:relative;z-index:1">

**Một số câu hỏi thường gặp:**

• Tại sao dùng MCP thay vì gọi thẳng Jenkins API từ AI?

• Tại sao dùng Ollama/Qwen thay vì GPT-4 hay Claude API?

• AI có thể thực hiện hành động nguy hiểm không?

• Độ chính xác của AI khi điều tra lỗi ra sao?

</div>
