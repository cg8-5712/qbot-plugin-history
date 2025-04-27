"""
Author: cg8-5712
Date: 2025-04-20
Version: 1.0.0
License: GPL-3.0
LastEditTime: 2025-04-20 16:30:00
Title: History Service
Description: Service class for fetching and processing historical events.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Dict
import aiohttp
from lxml import etree
from pathlib import Path
from openai import OpenAI
from zhenxun.services.log import logger
from zhenxun.configs.config import Config, BotConfig
from zhenxun.configs.path_config import PLUGIN_DATA_PATH


@dataclass
class HistoryEvent:
    """历史事件数据模型"""
    date: str
    content: str
    is_highlight: bool = False

    @staticmethod
    def format_event(content: str) -> str:
        """格式化事件文本"""
        return content.replace(" [ ", "").replace(" 年 ] ", "年")


class HistoryService:
    """历史事件服务"""
    _api_key = BotConfig.api_key
    _base_url = "https://api.shubiaobiao.cn/v1"
    _client = OpenAI(api_key=_api_key, base_url=_base_url)
    _data_dir = Path(PLUGIN_DATA_PATH) / "history"

    @classmethod
    def _maintain_cache(cls) -> None:
        """维护缓存文件，只保留最近指定天数的内容"""
        try:
            cache_time = Config.get_config("history", "CACHE_TIME", 7)
            # 如果缓存时间为0，表示永久保存
            if cache_time == 0:
                return

            if not cls._data_dir.exists():
                return

            current_time = datetime.now()
            for month_dir in cls._data_dir.iterdir():
                if not month_dir.is_dir():
                    continue

                for cache_file in month_dir.iterdir():
                    try:
                        # 从文件名解析日期（格式：dd.txt）
                        day = int(cache_file.stem)
                        file_date = datetime(
                            current_time.year,
                            int(month_dir.name),
                            day
                        )

                        # 计算日期差
                        days_diff = (current_time - file_date).days
                        if days_diff > cache_time:
                            cache_file.unlink()
                            logger.info(
                                "清理过期缓存文件",
                                "历史上的今天",
                                target=str(cache_file)
                            )
                    except ValueError:
                        continue
        except Exception as e:
            logger.error(
                "维护缓存失败",
                "历史上的今天",
                e=e
            )

    @classmethod
    async def get_events(cls) -> Tuple[List[HistoryEvent], List[HistoryEvent]]:
        """获取历史事件"""
        # 维护缓存文件
        cls._maintain_cache()

        cache_path = cls._get_cache_path()
        if cache_path.exists():
            logger.info("从缓存读取历史事件", "历史上的今天")
            return cls._read_from_cache(cache_path)
        # 后续代码保持不变...

        logger.info("开始从网页获取历史事件", "历史上的今天")
        events = await cls._fetch_from_web()

        if not events:
            logger.warning("未获取到任何历史事件", "历史上的今天")
            return [], []

        highlight_events = []
        other_events = []
        logger.info("开始验证历史事件关联性", "历史上的今天")
        for event in events:
            try:
                if await cls.verify_event(event):
                    event.is_highlight = True
                    highlight_events.append(event)
                else:
                    other_events.append(event)
            except Exception as e:
                logger.error(
                    "验证事件失败",
                    "历史上的今天",
                    target=event.content,
                    e=e
                )

        try:
            cls._save_to_cache(cache_path, highlight_events, other_events)
            logger.info(
                "历史事件已保存到缓存",
                "历史上的今天",
                target={"高亮事件": len(highlight_events), "其他事件": len(other_events)}
            )
        except Exception as e:
            logger.error(
                "保存缓存失败",
                "历史上的今天",
                target=str(cache_path),
                e=e
            )

        return highlight_events, other_events

    @staticmethod
    def _get_cache_path() -> Path:
        """获取缓存文件路径"""
        today = datetime.now()
        month_dir = Path("../data/history") / today.strftime("%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        return month_dir / f"{today.strftime('%d')}.txt"

    @classmethod
    async def _fetch_from_web(cls) -> List[HistoryEvent]:
        """从网页获取历史事件"""
        today = datetime.now()
        url = f"https://jintian.txcx.com/today-{today.strftime('%m')}-{today.strftime('%d')}.html"

        logger.info(f"正在请求网页", "历史上的今天", target=url)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        logger.error(
                            "网页请求失败",
                            "历史上的今天",
                            target={"url": url, "status": response.status}
                        )
                        return []
                    html_content = await response.text()
            except aiohttp.ClientError as e:
                logger.error(
                    "网络请求异常",
                    "历史上的今天",
                    target=url,
                    e=e
                )
                return []

        events = []
        try:
            parser = etree.HTMLParser()
            tree = etree.fromstring(html_content, parser)

            # 使用完整的XPath选择器
            contexts = tree.xpath("//a[@class='ml20' and @target='_blank']")

            for context in contexts:
                text = context.text
                if text and len(text.strip()) > 0:
                    logger.debug(
                        "解析历史事件",
                        "历史上的今天",
                        target=text.strip()
                    )
                    events.append(HistoryEvent(
                        date=today.strftime("%m-%d"),
                        content=HistoryEvent.format_event(text.strip())
                    ))

            if not events:  # 如果没有解析到事件
                logger.warning(
                    "未找到历史事件",
                    "历史上的今天",
                    target={"内容长度": len(html_content)}
                )
                # 输出页面结构以便调试
                logger.debug(
                    "页面结构",
                    "历史上的今天",
                    target=etree.tostring(tree, encoding='unicode', pretty_print=True)[:500]
                )
        except Exception as e:
            logger.error(
                "解析HTML失败",
                "历史上的今天",
                e=e
            )
            return []

        return events

    @classmethod
    def _read_from_cache(cls, cache_path: Path) -> Tuple[List[HistoryEvent], List[HistoryEvent]]:
        """从缓存读取事件"""
        highlight_events = []
        other_events = []
        today = datetime.now()

        try:
            content = cache_path.read_text(encoding='utf-8')
            mode = None

            for line in content.split('\n'):
                if line.strip():
                    if line.startswith('====高亮事件===='):
                        mode = 'highlight'
                    elif line.startswith('====其他事件===='):
                        mode = 'other'
                    elif mode == 'highlight' and line.startswith('[H]'):
                        highlight_events.append(HistoryEvent(
                            date=today.strftime("%m-%d"),
                            content=line[3:],
                            is_highlight=True
                        ))
                    elif mode == 'other' and line.startswith('[N]'):
                        other_events.append(HistoryEvent(
                            date=today.strftime("%m-%d"),
                            content=line[3:],
                            is_highlight=False
                        ))
            logger.info(
                "读取缓存完成",
                "历史上的今天",
                target={"高亮事件": len(highlight_events), "其他事件": len(other_events)}
            )
        except Exception as e:
            logger.error(
                "读取缓存失败",
                "历史上的今天",
                target=str(cache_path),
                e=e
            )
            return [], []

        return highlight_events, other_events

    @classmethod
    def _save_to_cache(cls, cache_path: Path, highlight_events: List[HistoryEvent],
                       other_events: List[HistoryEvent]) -> None:
        """保存到缓存"""
        content = "====高亮事件====\n"
        content += "\n".join(f"[H]{event.content}" for event in highlight_events)
        content += "\n====其他事件====\n"
        content += "\n".join(f"[N]{event.content}" for event in other_events)
        cache_path.write_text(content, encoding='utf-8')

    @classmethod
    async def verify_event(cls, event: HistoryEvent) -> bool:
        """验证事件是否相关"""
        try:
            completion = cls._client.chat.completions.create(
                model="gpt-3.5-turbo",
                stream=False,
                messages=[{
                    "role": "user",
                    "content": f"请判断内容是否与航空/民航/计算机领域有关，"
                              f"有关回复1，无关回复0。无需其他内容{event.content}"
                }]
            )
            return completion.choices[0].message.content == "1"
        except Exception as e:
            logger.error(
                "验证事件相关性失败",
                "历史上的今天",
                target=event.content,
                e=e
            )
            return False

    @staticmethod
    def format_text_output(highlight_events: List[HistoryEvent],
                          other_events: List[HistoryEvent]) -> str:
        """格式化文本输出"""
        output = "历史上的今天 - 重点事件：\n"
        output += "\n".join(event.content for event in highlight_events)
        output += "\n\n" + "*" * 20 + "\n\n其他事件：\n"
        output += "\n".join(event.content for event in other_events)
        return output.rstrip()

    @staticmethod
    def prepare_template_data(highlight_events: List[HistoryEvent],
                            other_events: List[HistoryEvent]) -> Dict:
        """准备模板数据"""
        return {
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "highlight_events": [{"content": e.content} for e in highlight_events],
            "other_events": [{"content": e.content} for e in other_events]
        }

    @staticmethod
    def get_subscribe_groups() -> List[int]:
        """获取订阅群组列表"""
        try:
            subscribe_groups = Config.get_config("history", "SUBSCRIBE_GROUPS", [])
            logger.info(
                "获取订阅群组列表成功",
                "历史上的今天",
                target={"群组数": len(subscribe_groups)}
            )
            return subscribe_groups
        except Exception as e:
            logger.error(
                "获取订阅群组列表失败",
                "历史上的今天",
                e=e
            )
            return []
