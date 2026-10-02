# -*- coding: utf-8 -*-

"""
百度贴吧自动删除回帖工具 v3

优化点：
1. 删除第一条策略
2. 自动刷新恢复
3. 刷新后主动滚动加载更多回复
4. 尽量保持每轮 10~20 条
5. 二次刷新兜底，防止反复刷新
"""

import os
import time
import random
import traceback
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# ========================== 配置 ==========================

# Edge 调试地址（端口要和启动 Edge 的命令一致）
DEBUG_ADDRESS = "127.0.0.1:9222"

# ★★★ 必改：你的贴吧个人主页地址 ★★★
# 获取方法：登录贴吧 -> 点自己头像进个人主页 -> 复制地址栏完整网址，整段替换掉下面这个占位符。
# 形如：https://tieba.baidu.com/home/main?id=填写你的贴吧ID&fr=personalize_page
TIEBA_URL = "填写你的贴吧主页URL"

# 最大删除数量（删够就自动停）
MAX_DELETE_COUNT = 500

# 希望一次攒多少条再开始删（少于它才继续滚动加载）
MIN_BATCH_SIZE = 10

# 预加载最多滚动几轮
MAX_LOAD_ROUND = 5

# 连续检测到几次空页面就触发刷新
EMPTY_LIMIT = 2

# 删除后等待（秒）
DELETE_WAIT = (4, 7)

# 普通随机等待（秒）
NORMAL_WAIT = (2, 5)

# 回复列表定位（贴吧改版失效时，按 README 重新抓）
REPLY_LIST_XPATH = (
    "/html/body/div[1]/div[2]/div/div/div[3]/div[1]/div[2]/div/div/div"
)

# ========================== 工具 ==========================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def sleep_random(a, b):
    time.sleep(random.uniform(a, b))


def check_stop():
    return os.path.exists("stop.txt")


# ========================== 浏览器 ==========================

def create_driver():
    options = Options()
    options.add_experimental_option("debuggerAddress", DEBUG_ADDRESS)
    return webdriver.Edge(options=options)


# ========================== 获取回复 ==========================

def get_replies(driver):
    try:
        replies = driver.find_elements(By.XPATH, REPLY_LIST_XPATH)
        log(f"当前加载回复:{len(replies)}")
        return replies
    except Exception:
        traceback.print_exc()
        return []


# ========================== 点击回帖 ==========================

def open_reply(driver, wait):
    try:
        tab = wait.until(EC.element_to_be_clickable((By.ID, "tab-reply")))
        driver.execute_script("arguments[0].click();", tab)
        log("进入回帖")
        time.sleep(5)
        return True
    except Exception:
        traceback.print_exc()
        return False


# ========================== 滚动加载 ==========================

def scroll_to_load_more(driver):
    """向下滚动，尽量触发列表懒加载（同时滚窗口和回复列表容器）。"""
    driver.execute_script(
        f"""
        window.scrollTo(0, document.body.scrollHeight);
        var list = document.evaluate(
            "{REPLY_LIST_XPATH}", document, null,
            XPathResult.FIRST_ORDERED_NODE_TYPE, null
        ).singleNodeValue;
        if (list) {{
            var el = list;
            for (var i = 0; i < 6 && el; i++) {{
                if (el.scrollHeight > el.clientHeight) {{
                    el.scrollTop = el.scrollHeight;
                }}
                el = el.parentElement;
            }}
        }}
        """
    )


# ========================== 预加载 ==========================

def preload_replies(driver):
    """刷新后主动滚动加载，尽量攒够 MIN_BATCH_SIZE 条。返回最终条数。"""
    log("开始预加载回复")
    for i in range(MAX_LOAD_ROUND):
        replies = get_replies(driver)
        if len(replies) >= MIN_BATCH_SIZE:
            log(f"达到目标数量:{len(replies)}")
            return len(replies)
        log(f"第{i + 1}次滚动加载（当前{len(replies)}条）")
        scroll_to_load_more(driver)
        sleep_random(3, 5)
    total = len(get_replies(driver))
    log(f"预加载结束，共{total}条")
    return total


# ========================== 删除第一条 ==========================

def delete_first(driver, wait):
    try:
        replies = get_replies(driver)
        if not replies:
            return False

        item = replies[0]

        more = item.find_element(By.CSS_SELECTOR, ".thread-setting")
        ActionChains(driver).move_to_element(more).perform()
        sleep_random(1, 2)
        driver.execute_script("arguments[0].click();", more)
        log("打开菜单")

        delete_btn = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//div[contains(@class,'setting-popover')]"
                    "//div[contains(@class,'text') and text()='删除']"
                )
            )
        )
        driver.execute_script("arguments[0].click();", delete_btn)
        log("删除")
        sleep_random(2, 3)

        confirm = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//div[contains(@class,'center') and text()='确定']"
                )
            )
        )
        driver.execute_script("arguments[0].click();", confirm)
        log("确认")
        sleep_random(*DELETE_WAIT)
        return True

    except Exception:
        log("删除失败")
        traceback.print_exc()
        try:
            os.makedirs("screenshots", exist_ok=True)
            filename = (
                "screenshots/error_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".png"
            )
            driver.save_screenshot(filename)
            log(f"保存截图:{filename}")
        except Exception:
            pass
        return False


# ========================== 主程序 ==========================

def main():
    print(
        """
========================
贴吧删除工具 v3
输入 YES 开始
========================
"""
    )
    if input("> ") != "YES":
        return

    driver = create_driver()
    wait = WebDriverWait(driver, 15)
    log("连接成功")

    driver.get(TIEBA_URL)
    time.sleep(5)
    open_reply(driver, wait)

    delete_count = 0
    empty_count = 0

    while True:
        if check_stop():
            log("检测到 stop.txt，退出")
            break

        if delete_count >= MAX_DELETE_COUNT:
            log("达到最大删除数量")
            break

        result = delete_first(driver, wait)
        if result:
            delete_count += 1
            empty_count = 0
            log(f"累计删除:{delete_count}")
            continue

        replies = get_replies(driver)
        if len(replies) == 0:
            empty_count += 1
            log(f"空页面:{empty_count}")
        else:
            empty_count = 0

        # ================= 关键优化 =================
        if empty_count >= EMPTY_LIMIT:
            log("当前缓存不足，刷新重新加载")

            # 第一次刷新
            driver.refresh()
            time.sleep(8)
            open_reply(driver, wait)
            loaded = preload_replies(driver)

            # 二次刷新兜底：首批太少再刷一次
            if loaded < MIN_BATCH_SIZE:
                log(f"首批仅{loaded}条，二次刷新再试")
                driver.refresh()
                time.sleep(8)
                open_reply(driver, wait)
                preload_replies(driver)

            empty_count = 0

        sleep_random(*NORMAL_WAIT)

    log(f"完成，总删除:{delete_count}")


if __name__ == "__main__":
    main()
