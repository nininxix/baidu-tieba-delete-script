# -*- coding: utf-8 -*-

"""
百度贴吧自动删除回帖工具 · 接口加速版（实验性）

和 main.py 一样，连接你已经登录的 Edge 浏览器。区别是：不再点页面的 DOM，
而是在浏览器内部用 fetch 直接调用贴吧的接口拿列表、执行删除。

优点：
1. 快：一次请求拿一页回帖，删除也是单次请求，不用滚动 / 刷新 / 点按钮。
2. 安全：cookies 由浏览器自动带上，代码里绝不出现、绝不落盘任何 Cookie 或密钥。

重要提醒：
1. 贴吧接口带 sign 签名参数。若列表返回空或报错，优先看 compute_sign() 函数
   （签名算法或密钥可能已更新）。
2. 接口直连比 UI 自动化更容易触发「操作频繁」。脚本已内置随机等待，
   请勿把等待调太小。你之前删到几百条后遇到「操作频繁」，就是节奏太快。
3. 建议先用 --list-only 只拉列表核对，确认无误再真正删除。

用法：
    uv run fast_mode.py --list-only   # 只列出回帖数量，不删除
    uv run fast_mode.py               # 连续删除，直到删完或命中风控自动停
    uv run fast_mode.py --limit 3     # 只删 3 条就停（试跑/分批）
"""

import os
import sys
import time
import random
import json
import hashlib
import traceback
from datetime import datetime
from urllib.parse import urlencode

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# ================= 配置 =================

# Edge 调试地址（和启动 Edge 的命令一致）
DEBUG_ADDRESS = "127.0.0.1:9222"

# ★★★ 必改：你的贴吧个人主页地址（和 main.py 里一样）★★★
# 获取方法：登录贴吧 -> 点自己头像进个人主页 -> 复制地址栏完整网址，整段替换掉下面引号里的占位符。
# 形如：https://tieba.baidu.com/home/main?id=填写你的贴吧ID&fr=personalize_page
TIEBA_URL = "填写你的贴吧主页URL"

# 列表接口 / 删除接口
FEED_API = "https://tieba.baidu.com/c/u/feed/myThread"
DELETE_API = "https://tieba.baidu.com/c/c/bawu/delpost_pc"

# 每页条数（贴吧默认 20，一般不用改）
PAGE_SIZE = 20

# 连续模式下，每轮先拉这么多条、删完再重新拉（一般不用改）
BATCH_SIZE = 20

# 删除后随机等待（秒）。接口版别太猛，太短容易「操作频繁」
DELETE_WAIT = (2.0, 4.0)
NORMAL_WAIT = (0.8, 1.6)

# 删除接口返回里命中这些关键词，就判定为「操作频繁/风控」并自动停止
RATE_LIMIT_KEYWORDS = ["频繁", "太快", "稍后", "稍候", "限制", "风控", "操作太", "系统繁忙", "请求过于"]

# 签名密钥（贴吧 PC 端 /c/ 接口通用，源自开源项目 MediaCrawler）。
# 若接口失效，大概率是这里变了，需要重新抓包核对。
SIGN_SECRET = "36770b1f34c9bbf2e7d1a99d2b82fa9e"

# ================= 工具 =================


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def sleep_random(a, b):
    time.sleep(random.uniform(a, b))


def check_stop():
    return os.path.exists("stop.txt")


def is_rate_limited(resp):
    """判断删除响应是否命中「操作频繁/风控」。"""
    if not resp:
        return False
    try:
        text = json.dumps(resp, ensure_ascii=False)
    except Exception:
        text = str(resp)
    return any(k in text for k in RATE_LIMIT_KEYWORDS)


def compute_sign(params):
    """按贴吧 PC 端接口规则计算 sign（MD5）。

    规则：参数按 key 升序，跳过 sign/sig 和 None，拼成 k=v 串（无分隔符），
    末尾追加密钥，再取 MD5（小写）。
    """
    base = "".join(
        f"{k}={params[k]}"
        for k in sorted(params.keys())
        if k not in {"sign", "sig"} and params[k] is not None
    )
    return hashlib.md5((base + SIGN_SECRET).encode("utf-8")).hexdigest()


# ================= 浏览器 =================


def create_driver():
    options = Options()
    options.add_experimental_option("debuggerAddress", DEBUG_ADDRESS)
    return webdriver.Edge(options=options)


def find_tieba_window(driver):
    """在已打开的窗口里找一个 tieba.baidu.com 的标签页并切换过去。"""
    try:
        for handle in driver.window_handles:
            try:
                driver.switch_to.window(handle)
                if "tieba.baidu.com" in driver.current_url:
                    log(f"已切到 tieba 标签页: {driver.current_url[:60]}")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def setup_page(driver):
    """确保落在 tieba 页面上。

    优先复用你已经在调试版 Edge 里打开的 tieba 标签（不重新 driver.get 导航，
    避免导航中途把窗口/标签搞丢）。实在没有才导航过去。
    """
    log(f"当前窗口数: {len(driver.window_handles)}")
    if find_tieba_window(driver):
        time.sleep(2)
        return True
    try:
        log("未找到现成 tieba 标签，尝试导航")
        driver.get(TIEBA_URL)
        time.sleep(5)
        driver.switch_to.window(driver.window_handles[-1])
        return True
    except Exception:
        traceback.print_exc()
        return False


def get_tbs(driver):
    """获取 tbs（CSRF token，删除接口要用）。

    先从当前页面读（PageData.tbs / window.tbs），读不到就调贴吧 sync 接口拿。
    """
    try:
        tbs = driver.execute_script(
            "var pd = window.PageData || {};"
            "return pd.tbs || (pd.user && pd.user.tbs) || window.tbs || '';"
        )
        if tbs:
            return tbs
    except Exception:
        pass

    # 页面里读不到，调 sync 接口
    params = {"subapp_type": "pc", "_client_type": "20"}
    params["sign"] = compute_sign(params)
    url = "https://tieba.baidu.com/c/s/pc/sync?" + urlencode(params)
    try:
        data = fetch_json(driver, url)
        tbs = (((data or {}).get("data") or {}).get("anti") or {}).get("tbs", "")
        if tbs:
            log("已从 sync 接口获取 tbs")
        return tbs
    except Exception as e:
        log(f"获取 tbs 失败: {e}")
        return ""


def extract_portrait(url):
    """从主页 URL 里取 id= 参数，那个就是你的 portrait（列表接口需要传）。"""
    if "id=" in url:
        part = url.split("id=", 1)[1]
        return part.split("&", 1)[0]
    return ""


def fetch_json(driver, url):
    """在浏览器内部 fetch 一个接口，返回解析后的 JSON dict。

    fetch 在页面上下文里执行，cookies 自动带上，无需手动处理登录态。
    """
    js = (
        "var url = arguments[0];"
        "var cb = arguments[arguments.length - 1];"
        "fetch(url, {credentials:'include'})"
        ".then(function(r){return r.text();})"
        ".then(function(t){cb(t);})"
        ".catch(function(e){cb('__ERR__' + e);});"
    )
    raw = driver.execute_async_script(js, url)
    if raw is None:
        raise RuntimeError("fetch 无返回")
    if isinstance(raw, str) and raw.startswith("__ERR__"):
        raise RuntimeError(raw)
    try:
        return json.loads(raw)
    except Exception:
        log(f"非 JSON 返回：{raw[:200]}")
        return None


# ================= 接口 =================


def fetch_replies(driver, pn, portrait):
    """拉取第 pn 页「我的回贴」列表。"""
    params = {
        "_client_type": "20",
        "pn": str(pn),
        "portrait": portrait,
        "rn": str(PAGE_SIZE),
        "subapp_type": "pc",
        "type": "2",
        "un": "",
    }
    params["sign"] = compute_sign(params)
    url = FEED_API + "?" + urlencode(params)
    return fetch_json(driver, url)


def delete_reply(driver, fid, tid, pid, tbs):
    """删除一条回贴。

    fid = 吧 id（thread_info.fid）
    tid = 帖子 id（thread_info.tid，即接口里的 z）
    pid = 回贴 id（post_info.id，即接口里的 pid）
    """
    params = {
        "_client_type": "20",
        "bawu_del_reason_info": "",
        "fid": str(fid),
        "owner_uid": "0",
        "pid": str(pid),
        "reason": "",
        "subapp_type": "pc",
        "tbs": tbs,
        "z": str(tid),
    }
    params["sign"] = compute_sign(params)
    url = DELETE_API + "?" + urlencode(params)
    return fetch_json(driver, url)


def collect_all(driver, portrait, max_items=None):
    """翻页收集回帖，返回 [(pid, tid, fid), ...]。

    max_items: 最多收集多少条（None=不限制，全部收完）。
    """
    items = []
    pn = 1
    while True:
        if check_stop():
            break
        if max_items is not None and len(items) >= max_items:
            break

        data = fetch_replies(driver, pn, portrait)
        if not data:
            log(f"第 {pn} 页无数据或解析失败，停止翻页")
            break

        err = data.get("error_code", 0)
        if err != 0:
            log(f"第 {pn} 页返回错误码 {err}，msg={data.get('error_msg') or data.get('error')}")
            break

        body = data.get("data") or {}
        lst = body.get("list") or []
        has_more = body.get("has_more", 0)
        log(f"第 {pn} 页：{len(lst)} 条（has_more={has_more}）")

        if not lst and has_more:
            log(f"第 {pn} 页空列表但 has_more={has_more}，判定为结束")
            break

        for item in lst:
            post = item.get("post_info") or {}
            thread = item.get("thread_info") or {}
            pid = post.get("id")
            tid = thread.get("tid")
            fid = thread.get("fid")
            if pid and tid and fid:
                items.append((pid, tid, fid))
                if max_items is not None and len(items) >= max_items:
                    break

        if not has_more:
            break
        pn += 1
        sleep_random(*NORMAL_WAIT)
    return items


# ================= 主程序 =================


def main():
    list_only = "--list-only" in sys.argv

    # --limit N：本次只删 N 条就停（试跑/分批用）。
    # 不带 --limit：连续删到底，直到删完或命中风控才停。
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[i + 1])
            except ValueError:
                limit = None

    print(
        """
========================
贴吧删除工具 · 接口加速版
输入 YES 开始
========================
"""
    )
    if input("> ") != "YES":
        return

    driver = create_driver()
    driver.set_script_timeout(20)
    log("连接成功")

    if not setup_page(driver):
        log("无法落到 tieba 页面，请确认调试版 Edge 里已打开并登录贴吧，然后重试")
        return

    portrait = extract_portrait(TIEBA_URL)
    if not portrait:
        log("警告：未能从 TIEBA_URL 解析出 portrait（id= 参数），列表接口可能失败")
    log(f"portrait={portrait or '未解析'}")

    tbs = get_tbs(driver)
    if not tbs:
        log("警告：未能从页面读取 tbs，删除接口可能失败")

    if list_only:
        items = collect_all(driver, portrait)
        log(f"共 {len(items)} 条回帖")
        log("list-only 模式：只列出，不删除，结束")
        return

    delete_count = 0
    while True:
        if check_stop():
            log("检测到 stop.txt，退出")
            break
        if limit is not None and delete_count >= limit:
            log(f"已达到本次上限 {limit} 条，停止")
            break

        # 拉一批（当前最前面的若干条）
        batch_limit = BATCH_SIZE if limit is None else min(BATCH_SIZE, limit - delete_count)
        batch = collect_all(driver, portrait, max_items=batch_limit)
        if not batch:
            log("没有回帖了，全部删完")
            break

        for pid, tid, fid in batch:
            if check_stop():
                log("检测到 stop.txt，退出")
                break
            if limit is not None and delete_count >= limit:
                break

            try:
                resp = delete_reply(driver, fid, tid, pid, tbs)
            except Exception:
                log(f"删除失败 pid={pid}（请求异常）")
                traceback.print_exc()
                sleep_random(*DELETE_WAIT)
                continue

            resp_dict = resp or {}
            err = resp_dict.get("error_code", resp_dict.get("no", -1))
            if str(err) in {"0", "None"}:
                delete_count += 1
                log(f"[{delete_count}] 已删除 pid={pid}")
            elif is_rate_limited(resp_dict):
                log("⚠️ 检测到「操作频繁/风控」，已自动停止。")
                log(f"    本次共删除 {delete_count} 条，请等待一段时间（几十分钟到几小时）后再运行。")
                return
            else:
                msg = resp_dict.get("error_msg") or resp_dict.get("error") or resp_dict.get("msg") or ""
                log(f"删除失败 pid={pid}，err={err} {msg}")

            sleep_random(*DELETE_WAIT)

    log(f"完成，总删除 {delete_count} 条")


if __name__ == "__main__":
    main()
