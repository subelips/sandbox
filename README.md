# sandbox — Kaggle + Hermes Agent + Pinggy + Termius (iOS)

Sandbox cá nhân chạy **Hermes Agent** trên Kaggle, SSH vào từ **Termius trên iPhone**
qua tunnel TCP cố định của **Pinggy Pro**, bật/tắt bằng **một** GitHub Action duy nhất,
thông báo qua **Telegram bot** (bot chỉ gửi, không nhận lệnh).

```
 iPhone (Termius)                    Kaggle Kernel (batch)              GitHub
 ────────────────                    ─────────────────────              ──────
  ssh root@                ┌────────► sshd :22 ◄──┐
  sandboxx.a.pinggy.link   │        │              │  pinggy TCP -R0:localhost:22
  -p 19326 ────────────────┘        │           tunnel.sh
        │                           │
        │                      hermes  (/root/.local/bin/hermes)
        │                           │
        └── tunnel ──► pinggy.io ◄──┘
                                    │
   Telegram  ◄──── READY / STOPPED ─┘        state.json ◄── workflow_dispatch on|off
   (chỉ nhận)                                 backup (mã hoá) ──► branch `state`
```

## 1. Thành phần

| Thứ | Ở đâu | Ghi chú |
|---|---|---|
| Repo điều khiển | `subelips/sandbox` (public) | 1 workflow duy nhất |
| Kernel sandbox | `maithanhtu/hermes-sandbox` | notebook sinh từ `scripts/sync_kernel.py` |
| Dataset agent | `maithanhtu/hermes-agent-pkg` (private) | `hermes-agent-full.pkg` — bản cài đầy đủ |
| Dataset secrets | `maithanhtu/sandbox-secrets` (**private**) | plaintext, đúng định dạng gốc |

`.pkg` là **tar + zstd** của `/root/.hermes` và `/root/.local` do chính
`install.sh` chính thức tạo ra **trên đúng image Kaggle**. Boot chỉ việc `tar -x`,
không cài lại, không tải mạng, không build.

## 2. Cài lần đầu

1. **GitHub secret duy nhất cần có:** `KAGGLE_API_TOKEN`
   (`Settings → Secrets and variables → Actions → New repository secret`).
   Đây là chỗ duy nhất GitHub giữ bí mật, vì Action phải xác thực với Kaggle trước
   khi làm bất cứ việc gì. Mọi bí mật khác (Pinggy, Telegram, SSH password, PAT,
   backup key) **đều đọc từ dataset `sandbox-secrets`**, không nằm trong GitHub.
2. Bật Actions cho repo (`Actions → I understand my workflows, go ahead`).
3. Chạy workflow **sandbox** với `action = on`.

Không cần SSH key ở bất kỳ đâu. sshd dùng **password auth**.

## 3. Dùng hằng ngày

`Actions → sandbox → Run workflow`

| action | việc xảy ra |
|---|---|
| `on` | `state.json` → `on`, đẩy kernel lên Kaggle, chờ READY |
| `off` | `state.json` → `off`; kernel đang chạy tự đọc cờ và thoát |
| `status` | chỉ báo trạng thái, không đổi gì |

Chỉ có **một** file workflow: `.github/workflows/sandbox.yml`. Không tách on/off.

## 4. Termius (iOS)

| Trường | Giá trị |
|---|---|
| Host | `sandboxx.a.pinggy.link` |
| Port | `19326` |
| Username | `root` |
| Auth | **Password** (xem `ssh.password` trong `sandbox-secrets/secrets.json`) |

Lần đầu bấm *Accept host key*; host key được giữ trong `.pkg` nên các lần sau không
hiện lại cảnh báo.

## 5. Boot làm những gì (có timing trong log)

| bước | thời gian điển hình |
|---|---|
| Kaggle cấp máy + mount dataset | ~60–120s (phía Kaggle, không can thiệp được) |
| `tar -x` `.pkg` | 8–15s |
| restore state mã hoá từ branch `state` | 1–3s |
| ghi `.env`, bật sshd | 2s |
| tunnel + kiểm tra end-to-end (đọc banner SSH qua host công khai) | 5–15s |
| **tổng từ lúc kernel bắt đầu chạy** | **~20–35s** |

## 6. Bảo mật

- `sandbox-secrets` là **private** và **không mã hoá** — đúng yêu cầu, và đó là lý do
  nó bắt buộc phải private. Nếu đổi sang public, coi như mất toàn bộ token.
- Dữ liệu lưu trữ lâu dài (memory, skills, sessions, config, state.db) được
  **mã hoá AES-256-CBC (PBKDF2, 200k vòng)** trước khi đẩy lên branch `state`.
  Chỉ giữ **một** bản ghi đè, không tạo lịch sử commit phình to.
- `state.json` nằm trên `main` và là công khai — nó chỉ chứa `mode`/`seq`, không có bí mật.
- Không dùng SSH key, không dùng GitHub secret cho bí mật của sandbox.

## 7. Giới hạn thật — đọc trước khi dùng

1. **Kaggle không có API bật notebook tương tác.** API công khai chỉ có
   `kernels push` (chạy batch). Vì vậy "sandbox" ở đây là **một kernel batch chạy dài**,
   không phải notebook tương tác. Bạn vẫn SSH vào bình thường, nhưng phiên không
   sống mãi.
2. **Kaggle không có API tắt kernel.** Không có endpoint `cancel`. Vì vậy `off`
   hoạt động bằng **cờ điều khiển**: kernel đọc `state.json` mỗi 25s và tự `break`.
   Độ trễ tắt thực tế ~25–60s, không tức thời.
3. **Giới hạn 12 giờ mỗi lần chạy (CPU).** Hết 12h Kaggle kill kernel. Workflow
   không tự bật lại — muốn sandbox sống tiếp thì chạy `on` lần nữa.
4. **Điều khoản Kaggle.** Kaggle không cho dùng notebook làm server/VPS thường trú.
   Dùng như vậy có rủi ro khoá tài khoản. Đây là lựa chọn của bạn, không phải tính
   năng được Kaggle hỗ trợ.
5. **Chưa có API key LLM.** `secrets.json → llm` đang rỗng. Thêm
   `{"provider": "...", "model": "...", "api_key": "...", "env_var": "..."}` rồi chạy
   `on` lại, hoặc SSH vào và chạy `hermes setup` một lần (cấu hình được giữ trong
   backup mã hoá).

## 8. Vận hành

```bash
# sinh lại notebook từ script (đừng sửa kernel/sandbox.ipynb bằng tay)
python3 scripts/sync_kernel.py

# build lại .pkg từ installer chính thức và cập nhật dataset
KAGGLE_API_TOKEN=... python3 scripts/build_datasets.py

# đổi trạng thái ngay trên máy, không qua Actions
python3 scripts/state.py set off && git commit -am "off" && git push
```

Log trong sandbox: `/root/.hermes/logs/tunnel.log`, `/kaggle/working/*.log`.
