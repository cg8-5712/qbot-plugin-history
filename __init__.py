"""
Author: cg8-5712
Date: 2025-04-20
Version: 1.0.0
License: GPL-3.0
LastEditTime: 2025-04-20 16:30:00
Title: Today in History Plugin
Description: This plugin shows historical events in aviation and computer fields.
"""

from nonebot import on_command
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from nonebot_plugin_htmlrender import template_to_pic
from nonebot_plugin_alconna import At, Text
from nonebot_plugin_apscheduler import scheduler

from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.configs.path_config import TEMPLATE_PATH
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils
from zhenxun.configs.config import Config
from zhenxun.services.log import logger
from .history import HistoryService

__plugin_meta__ = PluginMetadata(
    name="历史上的今天",
    description="展示航空和计算机领域的历史事件",
    usage="""
    指令:
        @机器人 历史上的今天/history/his: 以图片形式显示
        @机器人 历史上的今天/history/his --raw: 以文字形式显示
    自动推送:
        每天12:00自动推送至订阅群组
    """,
    extra=PluginExtraData(
        version="1.0.0",
        plugin_type=PluginType.NORMAL,
        configs=[
            RegisterConfig(
                module="history",
                key="CACHE_TIME",
                value=30,
                help="CACHE_TIME: 缓存保存时间（天） 默认7天 0为永久保存",
                default_value=7,
            ),
            RegisterConfig(
                module="history",
                key="SUBSCRIBE_GROUPS",
                value=[],
                help="SUBSCRIBE_GROUPS: 订阅推送的群组列表",
                default_value=[],
            ),
        ]).to_dict(),
)


Config.add_plugin_config(
    "history",         # 模块名
    "CACHE_TIME",     # 配置项名称
    7,                # 默认值
    help="缓存保存时间（天） 默认7天 0为永久保存",
    type=int
)

Config.add_plugin_config(
    "history",         # 模块名
    "SUBSCRIBE_GROUPS",# 配置项名称
    [],               # 默认值
    help="订阅推送的群组列表",
    type=list
)

HistoryCommand = on_command(
    "历史上的今天",
    rule=to_me(),
    priority=6,
    block=True,
    aliases={"history", "his"}
)

@HistoryCommand.handle()
async def handle_history(event: GroupMessageEvent, args=CommandArg()):
    """处理历史查询命令"""
    args = args.extract_plain_text().strip().split()
    show_raw = len(args) > 0 and args[0] == "--raw"

    logger.info(
        "开始获取历史事件",
        "历史上的今天",
        session=event,
        adapter="OneBot V11"
    )

    try:
        highlight_events, other_events = await HistoryService.get_events()

        if not highlight_events and not other_events:
            logger.warning(
                "未获取到任何历史事件",
                "历史上的今天",
                session=event,
                adapter="OneBot V11"
            )
            await MessageUtils.build_message([
                At(flag="user", target=str(event.user_id)),
                Text("获取历史数据失败，请稍后重试")
            ]).send(reply_to=True)
            return

        if show_raw:
            text_output = HistoryService.format_text_output(highlight_events, other_events)
            await MessageUtils.build_message([
                At(flag="user", target=str(event.user_id)),
                Text(text_output)
            ]).send(reply_to=True)
        else:
            template_data = HistoryService.prepare_template_data(
                highlight_events,
                other_events
            )
            # 参照 metar 插件修改路径处理
            image = await template_to_pic(
                template_path=str(
                    (TEMPLATE_PATH / "history").absolute()
                ),
                template_name="main.html",
                templates=template_data,
                pages={
                    "viewport": {"width": 800, "height": 600},
                    "base_url": f"file://{(TEMPLATE_PATH / 'history').absolute()}"
                },
                wait=2
            )
            await MessageUtils.build_message([
                At(flag="user", target=str(event.user_id)),
                image
            ]).send(reply_to=True)

        logger.info(
            "历史事件发送成功",
            "历史上的今天",
            session=event,
            adapter="OneBot V11",
            target={"高亮事件": len(highlight_events), "其他事件": len(other_events)}
        )

    except Exception as e:
        logger.error(
            "处理历史事件失败",
            "历史上的今天",
            session=event,
            adapter="OneBot V11",
            e=e
        )
        await MessageUtils.build_message([
            At(flag="user", target=str(event.user_id)),
            Text("处理失败，请稍后重试")
        ]).send(reply_to=True)

@scheduler.scheduled_job('cron', hour=12, minute=0)
async def daily_history_push():
    """每日定时推送"""
    logger.info("开始执行定时推送", "历史上的今天")

    try:
        highlight_events, other_events = await HistoryService.get_events()
        if highlight_events or other_events:
            template_data = HistoryService.prepare_template_data(
                highlight_events,
                other_events
            )
            print(template_data)
            print(type(template_data))
            # 同步修改定时推送的路径处理
            image = await template_to_pic(
                template_path=str(
                    (TEMPLATE_PATH / "history").absolute()
                ),
                template_name="main.html",
                templates=template_data,
                pages={
                    "viewport": {"width": 800, "height": 600},
                    "base_url": f"file://{(TEMPLATE_PATH / 'history').absolute()}"
                },
                wait=2
            )

            groups = HistoryService.get_subscribe_groups()
            for group in groups:
                await MessageUtils.build_message([
                    image
                ]).send_to_group(group)

            logger.info(
                "定时推送完成",
                "历史上的今天",
                target={"推送群组数": len(groups)}
            )
    except Exception as e:
        logger.error(
            "定时推送失败",
            "历史上的今天",
            e=e
        )