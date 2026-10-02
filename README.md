# 贴吧回贴批量删除工具

批量删除你在百度贴吧发过的所有「回贴」。连接一个**你已经登录的 Edge 浏览器**，自动重复执行删除，让你从几百上千条手工「… → 删除 → 确定」里解脱出来。

> ⚠️ 仅限删除**你自己账号**的内容，请勿用于删除他人内容或任何违规用途。

---

## 解决了什么问题

百度贴吧没有「一键清空回贴」的入口。想清掉以前发过的大量回贴，只能逐条点开「…」→「删除」→「确定」，几百上千条会点到怀疑人生。

本工具接管这段重复劳动：**账号密码始终只由你自己在浏览器里输入**，代码里不出现、不落盘任何登录凭据（BDUSS / STOKEN / Cookie 一律不碰）。删除对象也锁定为你自己的回贴，不涉及他人内容。

---

## 使用方法

整个流程七步走完，照着做即可。需要 `Python >= 3.10` 和一个 Edge 浏览器（Win 自带）。

### 第 0 步：安装 uv

`uv` 是 Python 包管理器，负责隔离环境、拉依赖、跑脚本。装一次即可：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

装完关掉当前终端重开，使环境变量生效。

### 第 1 步：安装依赖

在项目目录下执行：

```powershell
uv sync
```

它会按 `pyproject.toml` 建好虚拟环境并装好 `selenium`。

### 第 2 步：准备 Edge 驱动

脚本通过 Selenium 驱动 Edge。Selenium 4 内置 Selenium Manager，**首次运行会自动下载匹配版本的 `msedgedriver`，一般无需手动装**。只有自动下载失败时才需要手动装：

1. 打开 Edge，地址栏输入 `edge://version/`，记下「Microsoft Edge」后面的版本号（如 `120.0.2210.91`）。
2. 到官方下载页选对应的版本和平台（Windows x64）：
   <https://developer.microsoft.com/microsoft-edge/tools/webdriver/>
3. 下载解压得到 `msedgedriver.exe`，**放到项目目录**（或加进系统 `PATH`）。Selenium 会优先用它。

### 第 3 步：启动调试版 Edge 并登录

启动一个「带调试端口」的 Edge，然后在弹出的窗口里打开 `tieba.baidu.com` 登录，**保持窗口开着**。

**执行：PowerShell 直接粘贴一条命令**

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_edge_profile"
```

> **`msedge.exe` 的路径怎么填**：上面的完整路径就是 Edge 的安装位置。绝大多数 64 位 Windows 是 `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`；如果你的 Edge 装在别处（例如没有 `(x86)`，变成 `C:\Program Files\Microsoft\Edge\Application\msedge.exe`），把它换成你机器上的真实路径即可。最省事的确认办法：资源管理器里找到 `msedge.exe` 所在文件夹，复制它的完整路径替换进去。
>
> 命令里另外两个参数**别动**：`--remote-debugging-port=9222` 是调试端口（要和代码里的 `DEBUG_ADDRESS` 一致），`--user-data-dir=...` 是独立配置目录（不影响你日常浏览器）。

> 这一步开的是「远程调试端口」，脚本稍后通过它附着到这个已登录的窗口，所以登录态是现成的，代码不需要碰你的密码。

### 第 4 步：拿到你的贴吧主页 URL

1. 在刚登录的 Edge 里点自己的**头像**进入个人主页；
2. 复制**地址栏的完整网址**。形如：

```
https://tieba.baidu.com/home/main?id=填写你的贴吧ID&fr=personalize_page
```

其中 `id=` 后面那一串就是你的贴吧 ID，复制整条网址即可。

### 第 5 步：把 URL 填进代码

打开 `fast_mode.py`，找到顶部这一行：

```python
TIEBA_URL = "填写你的贴吧主页URL"
```

把引号里的占位符**整段替换**成第 4 步复制的网址。改完形如：

```python
TIEBA_URL = "https://tieba.baidu.com/home/main?id=你的那串ID&fr=personalize_page"
```

> 用 `main.py`（UI 版）时同样改它顶部的那一行，位置和写法完全一致。

### 第 6 步：先数一下还有多少条（不删除）

```powershell
uv run fast_mode.py --list-only
```

终端会打印回贴总数。核对无误再进入下一步。

### 第 7 步：开始删除

**先试删 3 条**，确认能删再放手：

```powershell
uv run fast_mode.py --limit 3
```

确认没问题后，**连续删除**（删完或命中风控才停）：

```powershell
uv run fast_mode.py
```

启动后程序会要求输入 `YES` 确认，输入后回车才开始。

**手动停止**：在项目目录放一个空文件 `stop.txt`，程序检测到后会在当轮结束退出；或直接按 `Ctrl+C`。

---

## 项目介绍

本项目提供两种实现，解决同一个问题：

| | `fast_mode.py`（接口加速版）★ | `main.py`（UI 自动化版） |
|---|---|---|
| 原理 | 浏览器内直接调贴吧接口 | 模拟点击页面按钮 |
| 单条耗时 | 约 2~4 秒 | 约 10~15 秒 |
| 依赖 | 接口签名（接口变更需改密钥） | 页面 DOM（改版需重抓定位） |
| 定位 | **主力，推荐** | 兜底、求稳 |

一般直接上接口加速版；`main.py` 作为接口签名失效时的兜底保留。

### 接口加速版（fast_mode.py）

核心思路：不操作页面 DOM，而是在**登录态的浏览器内部**用 `fetch` 直接调贴吧接口。浏览器自动携带 Cookie，因此全程无需手动搬运登录态，也从源头杜绝了凭据泄露。

**用到的接口**

| 接口 | 用途 |
|---|---|
| `/c/u/feed/myThread` | 翻页拉取「我的回贴」列表 |
| `/c/c/bawu/delpost_pc` | 删除一条回贴 |
| `/c/s/pc/sync` | 获取 `tbs`（CSRF token） |

**数据流与字段映射**

1. `myThread` 返回每条回贴的三个关键字段：
   - `post_info.id` → 回贴 ID
   - `thread_info.tid` → 帖子 ID
   - `thread_info.fid` → 吧 ID
2. 删除时映射到 `delpost_pc`：`post_info.id → pid`、`thread_info.tid → z`、`thread_info.fid → fid`，再带上 `tbs` 和 `sign`。
3. 响应 `error_code: "0"` 即删除成功。

列表接口负责「给原料」，删除接口拿这些原料「干活」，两者是一套。

**签名（sign）**

`myThread` 和 `delpost_pc` 都要求带 `sign` 签名。算法：

```
sign = md5( join_sorted("k=v") + SIGN_SECRET )
```

即：所有参数按 key 升序拼成 `k=v` 串（无分隔符，跳过 `sign`/`sig`/`None`），末尾追加密钥，再做 MD5（小写）。密钥为贴吧 PC 端通用常量（`SIGN_SECRET`，见代码顶部），已用真实请求逐字节验证通过。

**连续模式与风控**

不带 `--limit` 时进入**连续模式**：每轮拉取当前最前面的约 20 条、逐条删除，删完自动重新拉（删除后列表前移，重拉即拿到新的「最前面」），直到以下任一条件自动停止：

1. **删完** → 打印 `没有回帖了，全部删完`；
2. **命中风控** → 打印 `⚠️ 检测到「操作频繁/风控」，已自动停止`，并提示等待时间；
3. **检测到 `stop.txt`** → 随时手动停。

删除接口返回里出现「频繁 / 太快 / 限制 / 风控 / 稍后」等关键词即判定为风控。因为始终删的是「最前面的回贴」，中断后再跑会自然接着剩下的继续，无需记录进度。

**为什么快**

UI 版的时间几乎全耗在「找元素 → 等元素出现 → 点按钮 → 等页面渲染」上；接口版把这一整层 DOM 交互都绕过了，只剩**网络往返 + 人为加的随机延时**（随机延时是为风控留的缓冲，不是白等）。

### UI 自动化版（main.py）

在页面上模拟点击删除，走「删第一条 → 刷新 → 继续」的循环，含自动滚动预加载、二次刷新兜底。速度慢，但**不依赖接口签名**——接口版因签名失效跑不动时用它兜底。

---

## 原理与配置

**调试版 Edge 的原理**：脚本通过 Edge 的远程调试端口（默认 9222）附着到「你已经登录的窗口」。`start_edge.bat` 里的两个参数缺一不可：

- `--remote-debugging-port=9222`：开调试端口，与代码里的 `DEBUG_ADDRESS` 一致；
- `--user-data-dir=C:\selenium_edge_profile`：独立配置目录（新版 Edge 禁止在默认目录开调试；独立目录也不影响你日常的浏览器）。

**配置项**（`fast_mode.py` 顶部）：

| 变量 | 说明 |
|---|---|
| `TIEBA_URL` | 你的贴吧主页地址（**必改**） |
| `DEBUG_ADDRESS` | Edge 调试端口，默认 `127.0.0.1:9222` |
| `BATCH_SIZE` | 连续模式每轮拉取条数，默认 20 |
| `DELETE_WAIT` | 删除后随机等待秒数，默认 `(2, 4)`；太小易触发风控 |
| `NORMAL_WAIT` | 翻页随机等待秒数 |
| `SIGN_SECRET` | 接口签名密钥，接口失效时重点排查这里 |
| `RATE_LIMIT_KEYWORDS` | 风控判定关键词列表 |

---

## 常见问题

**驱动报错 `SessionNotCreatedException`？**
Edge 版本与驱动不匹配。按第 2 步手动下载对应版本的 `msedgedriver.exe` 放到项目目录再试。

**删到一半自己停了？**
大概率命中风控。看终端是否出现「操作频繁/风控」提示，等一段时间（几十分钟到几小时）再跑。也可以把 `DELETE_WAIT` 调大（如 `(4, 8)`）降低频率。

**`--list-only` 显示 0 条 / 报错？**
先核对第 5 步的 `TIEBA_URL` 填对了没；接口签名可能已更新，优先检查代码顶部的 `SIGN_SECRET` 与签名算法。

**想用 UI 版？**
按第 5 步把 `main.py` 顶部的 `TIEBA_URL` 也填上，然后 `uv run main.py` 即可，其余步骤相同。

---

## 免责声明

本工具仅用于删除你自己账号的内容。请遵守百度贴吧用户协议及相关法律法规。批量操作可能触发平台风控，请适度使用、放慢节奏。由此产生的一切后果由使用者自行承担。
