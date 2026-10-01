import requests
import time
import threading
import re
from bs4 import BeautifulSoup
import logging
import random
import sys
import os

# Windows 下检测粘贴是否结束
if sys.platform == 'win32':
    import msvcrt
    def has_pending_input():
        return msvcrt.kbhit()
else:
    def has_pending_input():
        return False

# 配置日志 - 自定义格式: 【2026-08-24 16:24】 | 消息
class CustomFormatter(logging.Formatter):
    def format(self, record):
        time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(record.created))
        return f"【{time_str}】 | {record.getMessage()}"

handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)


class CSDNArticleVisitor:
    def __init__(self):
        self.article_urls = []  # 文章URL列表
        self.lock = threading.Lock()  # 线程锁，用于安全地修改文章列表
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://blog.csdn.net/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        })
        self.visit_interval = 60  # 1分钟间隔启动新线程
        self.running = True

        # 多个User-Agent池，随机选择
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0'
        ]

    def parse_view_count(self, view_str):
        """
        将阅读量字符串转换为整数
        支持格式: '1.3w', '8.5k', '5678'
        """
        if not view_str or view_str == "未知":
            return 0

        view_str = str(view_str).lower().strip()

        # 处理 w (万) 单位
        if 'w' in view_str:
            num = float(view_str.replace('w', ''))
            return int(num * 10000)

        # 处理 k (千) 单位
        elif 'k' in view_str:
            num = float(view_str.replace('k', ''))
            return int(num * 1000)

        # 纯数字
        else:
            # 去除非数字字符
            num_str = re.sub(r'[^\d]', '', view_str)
            return int(num_str) if num_str else 0

    def input_article_list(self):
        """交互式输入文章链接列表"""
        urls_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'urls.txt')

        print("=" * 44)
        print("原地刷浏览量脚本（支持CSDN）")
        print("=" * 44)
        print("请逐行输入要的网址:")

        self.article_urls.clear()

        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                break

            line = line.strip()
            if not line:
                break

            if 'csdn.net' in line and line not in self.article_urls:
                self.article_urls.append(line)

            if not has_pending_input():
                break

        # 如果没输入，从 urls.txt 读取
        if not self.article_urls:
            if os.path.exists(urls_file):
                with open(urls_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and 'csdn.net' in line and line not in self.article_urls:
                            self.article_urls.append(line)
                if self.article_urls:
                    print("（从 urls.txt 读取）")
            if not self.article_urls:
                print("无有效链接，退出。")
                return False
        else:
            # 保存本次链接到 urls.txt
            with open(urls_file, 'w', encoding='utf-8') as f:
                for url in self.article_urls:
                    f.write(url + '\n')

        print("=" * 44)
        print(f"共 {len(self.article_urls)} 篇，间隔秒数（回车默认 60）：", end="")
        try:
            s = input().strip()
            self.visit_interval = int(s) if s else 60
        except (EOFError, KeyboardInterrupt, ValueError):
            self.visit_interval = 60

        print("=" * 44)
        return True

    def visit_article(self, url):
        """访问单篇文章"""
        try:
            # 随机选择User-Agent
            headers = self.session.headers.copy()
            headers['User-Agent'] = random.choice(self.user_agents)

            # 添加Referer，模拟从列表页点击进入
            headers['Referer'] = 'https://blog.csdn.net/'

            response = self.session.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            # 解析页面获取标题和阅读量
            soup = BeautifulSoup(response.text, 'html.parser')

            # 获取精确阅读量（从页面 JS 变量中提取）
            view_count = "未知"
            match = re.search(r'var\s+viewCountFormat\s*=\s*(\d+)', response.text)
            if match:
                view_count = int(match.group(1))
            else:
                # 备用方案：从 HTML 元素中解析
                view_elems = soup.find_all('span', class_='read-count') or \
                             soup.find_all('span', class_='view-count') or \
                             soup.find_all('span', class_='count')
                if view_elems:
                    for elem in view_elems:
                        text = elem.get_text().strip()
                        text = text.replace(' 阅读', '').replace('阅读', '').strip()
                        if re.match(r'^[\d.]+[kKwW]?$', text) or re.match(r'^\d+$', text):
                            view_count = self.parse_view_count(text)
                            break

            logger.info(f"{url} | 阅读量: {view_count}")

            return True
        except Exception as e:
            logger.error(f"访问文章失败 {url}: {e}")
            return False

    def remove_article(self, url):
        """从内存列表中移除指定链接"""
        try:
            # 从内存列表中移除
            with self.lock:
                if url in self.article_urls:
                    self.article_urls.remove(url)
                    logger.info(f"已从内存列表中移除: {url}")

        except Exception as e:
            logger.error(f"移除文章失败 {url}: {e}")

    def visit_articles_thread(self, thread_id):
        """线程访问文章列表"""
        if not self.article_urls:
            return

        for i, url in enumerate(self.article_urls):
            if not self.running:
                break

            self.visit_article(url)

            # 随机访问间隔，避免请求过于频繁被识别为机器人
            delay = random.uniform(1, 3.5)
            time.sleep(delay)

    def start_visit_scheduler(self):
        """启动访问调度器"""
        thread_counter = 0

        while self.running:
            try:
                if self.article_urls:
                    thread_counter += 1
                    # 创建新的访问线程
                    visit_thread = threading.Thread(
                        target=self.visit_articles_thread,
                        args=(thread_counter,),
                        daemon=True
                    )
                    visit_thread.start()
                else:
                    logger.warning("文章列表为空，程序退出")
                    break

                # 等待1分钟后启动下一个线程
                time.sleep(self.visit_interval)

            except Exception as e:
                logger.error(f"调度器出错: {e}")
                time.sleep(60)

    def run(self):
        """运行主程序"""
        # 交互式输入文章链接
        if not self.input_article_list():
            return

        # 启动访问调度器（主线程）
        try:
            self.start_visit_scheduler()
        except KeyboardInterrupt:
            self.running = False

    def stop(self):
        """停止程序"""
        self.running = False
        logger.info("程序已停止")


def main():
    """主函数"""
    visitor = CSDNArticleVisitor()

    try:
        visitor.run()
    except KeyboardInterrupt:
        logger.info("用户中断程序")
        visitor.stop()
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        visitor.stop()


if __name__ == "__main__":
    main()