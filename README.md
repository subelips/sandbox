# sandbox — Kaggle + Hermes Agent + Pinggy + Termius (iOS)

Sandbox cá nhân chạy **Hermes Agent** trên Kaggle, SSH vào từ **Termius trên iPhone**
qua tunnel TCP cố định của **Pinggy Pro**, bật/tắt bằng **một** GitHub Action duy nhất,
thông báo qua **Telegram bot** (bot chỉ gửi, không nhận lệnh).

```
 iPhone (Termius)                    Kaggle Kernel (batch)              GitHub
 ────────────────                    ─────────────────────              ──────
  ssh root@                ┌────────► sshd :22 ◄──┐
  sandboxx.a.pinggy.link   │        │              │  pinggy TCP -R0:127.0.0.1:22
  -p 19326 ────────────────┘        │           tunnel.sh (tự reconnect)
        │                           │
        │                      hermes  (/usr/local/bin/hermes)
        │                           │
        └── tunnel ──► pinggy.io ◄──┘
                                    │
   Telegram  ◄──── READY / STOPPED ─┘        state.json ◄── workflow_dispatch on|off
   (chỉ nhận)                                 config ◄── dataset `sandbox-secrets`
```

## 1. Thành phần

| Thứ | Ở đâu | Ghi chú |
|---|---|---|
| Repo điều khiển | `subelips/sandbox` (public) | đúng **1** workflow |
| Kernel sandbox | `maithanhtu/hermes-sandbox` | notebook sinh từ `scripts/sync_kernel.py` |
| Dataset agent | `maithanhtu/hermes-agent-pkg` (private) | `hermes-agent-full.pkg` — bản cài đầy đủ |
| Dataset secrets | `maithanhtu/sandbox-secrets` (**private**) | plaintext, đúng định dạng gốc |

`.pkg` là **tar + zstd** của `/root/.hermes` và `/root/.local`, do chính
`install.sh` chính thức dựng ra **trên đúng image Kaggle** (cùng Ubuntu 24.04,
cùng Python 3.13), nên boot chỉ việc bung ra — không cài lại, không tải mạng.

Nội dung `.pkg`: 2.84 GB / 94.044 file — `hermes-agent` (git checkout đầy đủ),
`tools/` (Chromium 1208, cua-driver 0.21.0, node), `installs/`, `skills/`.
**Không bỏ phần nào**, kể cả browser và computer-use.

## 2. Cài lần đầu

1. **GitHub secret duy nhất:** `KAGGLE_API_TOKEN`
   (`Settings → Secrets and variables → Actions → New repository secret`).
   Đây là chỗ duy nhất GitHub giữ bí mật, vì Action buộc phải xác thực với Kaggle
   trước khi làm gì. Mọi bí mật khác (Pinggy, Telegram, SSH password, PAT, config)
   **đọc từ dataset `sandbox-secrets`** lúc chạy — không nằm trong GitHub.
2. Bật Actions (`Actions → I understand my workflows, go ahead`).
3. Chạy workflow **sandbox** với `action = on`.

Không có SSH key ở bất kỳ đâu. sshd chỉ bật **password auth**.

## 3. Dùng hằng ngày

`Actions → sandbox → Run workflow`

| action | việc xảy ra | thời gian đo được |
|---|---|---|
| `on` | `state.json` → `on`, đẩy kernel lên Kaggle | SSH sống sau **~60–75s** |
| `off` | `state.json` → `off`, kernel tự đọc cờ và thoát | workflow xong sau **~31s** |
| `status` | chỉ báo trạng thái | ~15s |

Chỉ có **một** file workflow: `.github/workflows/sandbox.yml`. Không tách on/off.

## 4. Termius (iOS)

| Trường | Giá trị |
|---|---|
| Host | `sandboxx.a.pinggy.link` |
| Port | `19326` |
| Username | `root` |
| Auth | **Password** — `ssh.password` trong `sandbox-secrets/secrets.json` |

Host key được giữ trong `.pkg` nên chỉ phải *Accept* một lần.

## 5. Boot làm gì (số đo thật từ log của kernel)

| bước | lần đầu | lần sau (mount đã ấm) |
|---|---|---|
| Kaggle cấp máy + mount dataset | ~60–90s (phía Kaggle) | ~60–90s |
| `zstd -dc .pkg \| tar -x` | 27,7s | **15,0s** |
| `hermes --version` | 7,5s | 6,3s |
| config.yaml từ dataset | ~0,1s | ~0,1s |
| sshd + kiểm tra banner | 3,5s | 3,1s |
| tunnel + kiểm tra end-to-end | 0,4s | 6,1s |
| **READY** | **42s** | **32s** |

Bước "kiểm tra end-to-end" là thật: kernel tự mở TCP tới `sandboxx.a.pinggy.link:19326`
và đọc banner SSH trả về. Nếu không thấy banner, boot **thất bại ngay** chứ không
treo im lặng — và báo Telegram.

## 6. Bảo mật

- `sandbox-secrets` **private** và **không mã hoá** — đúng yêu cầu, và đó là lý do
  nó buộc phải private. Đổi sang public = mất toàn bộ token.
- **Cấu hình nằm trong dataset**, không nằm trong sandbox: mỗi boot đều copy
  `hermes-config.yaml` từ dataset đè lên `~/.hermes/config.yaml` (129 kB, bản đầy đủ
  do installer sinh ra). Không lần boot nào phải `hermes setup` lại.
  Sửa cấu hình thì sửa file trong dataset, hoặc SSH vào rồi chạy `hermes-save-config`.
- `state.json` trên `main` là công khai — chỉ chứa `mode`/`seq`, không có bí mật.
- Không SSH key, không GitHub secret cho bí mật của sandbox, **không backup, không branch phụ**.

## 7. Giới hạn thật — đọc trước khi dùng

1. **Kaggle không có API bật notebook tương tác.** API công khai chỉ có
   `kernels push` (chạy batch). Vì vậy "sandbox" ở đây là **một kernel batch chạy dài**.
   SSH vào bình thường, nhưng phiên không sống mãi.
2. **Kaggle không có API tắt kernel.** Không có endpoint `cancel`. Nên `off` chạy bằng
   **cờ điều khiển**: kernel đọc `state.json` mỗi 15s và tự thoát. Độ trễ ~15–30s.
3. **Giới hạn 12 giờ mỗi lần chạy (CPU).** Hết 12h Kaggle kill. Workflow không tự bật lại.
4. **Điều khoản Kaggle.** Kaggle không cho dùng notebook làm server thường trú; dùng
   như vậy có rủi ro khoá tài khoản. Đây là lựa chọn của bạn, không phải tính năng
   được Kaggle hỗ trợ.
5. **Chưa có API key LLM.** `secrets.json → llm` đang rỗng. Thêm
   `{"provider": "...", "model": "...", "api_key": "...", "env_var": "..."}` rồi chạy
   `on` lại, hoặc thêm `llm` vào dataset rồi chạy `hermes-save-config` sau khi `hermes setup`.

## 8. Vận hành & sửa lỗi

```bash
# trong sandbox: lưu cấu hình đang chạy ngược lại dataset (boot sau giữ nguyên)
hermes-save-config

# sinh lại notebook từ script (đừng sửa kernel/sandbox.ipynb bằng tay)
python3 scripts/sync_kernel.py

# build lại .pkg từ installer chính thức rồi cập nhật dataset
KAGGLE_API_TOKEN=... python3 scripts/build_datasets.py

# đổi trạng thái ngay trên máy, không qua Actions
python3 scripts/state.py set off && git commit -am "off" && git push
```

| triệu chứng | nguyên nhân | xử lý |
|---|---|---|
| Termius "Connection reset" | kernel chưa READY, hoặc tunnel chưa lên | chờ tin Telegram READY |
| Boot fail: *public endpoint not answering* | cổng `19326` đang bị một phiên Pinggy khác giữ | đóng phiên cũ, chỉ 1 tunnel cùng lúc |
| Boot fail: *sshd not answering* | image đổi cấu trúc sshd | xem `/root/.hermes/logs/sshd.log` |
| `off` xong mà kernel vẫn chạy | `state.json` không đọc được | log kernel in `api state read failed` |
| Sửa config mà boot sau mất | sửa trong sandbox rồi quên lưu | chạy `hermes-save-config` |
| Log kernel | `kaggle kernels logs maithanhtu/hermes-sandbox` | |

**Bài học đã trả giá:** `raw.githubusercontent.com` nằm sau CDN, đã trả về bản
`state.json` **cũ 5 phút** trong lúc test. Vì vậy kernel đọc trạng thái qua
`api.github.com` (có PAT), raw chỉ là fallback.
