#!/usr/bin/env python3
"""
从 Notion 数据库生成 ICS 文件
"""

import os
from datetime import datetime, timedelta
from typing import Optional, List
import pytz
import httpx

from icalendar import Calendar, Event, Timezone, TimezoneStandard

# 从环境变量读取配置
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

# Notion API 配置
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# 时区配置
TIMEZONE = "Asia/Shanghai"
tz = pytz.timezone(TIMEZONE)


def parse_notion_date(date_value: dict) -> Optional[datetime]:
    """解析 Notion 日期字段"""
    if not date_value:
        return None

    date_str = date_value.get("start")
    if not date_str:
        return None

    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.astimezone(pytz.UTC).astimezone(tz)
    except:
        return None


def notion_datetime_to_ics_datetime(dt: datetime) -> datetime:
    """转换时区为 UTC（ICS 标准）"""
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return dt.astimezone(pytz.UTC)


async def fetch_notion_events() -> List[dict]:
    """从 Notion 数据库获取日程"""
    try:
        print(f"[{datetime.now()}] 正在获取 Notion 数据...")

        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json"
        }

        results = []
        has_more = True
        start_cursor = None

        async with httpx.AsyncClient() as client:
            while has_more:
                payload = {"page_size": 100}
                if start_cursor:
                    payload["start_cursor"] = start_cursor

                response = await client.post(
                    f"{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}/query",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                results.extend(data.get("results", []))
                has_more = data.get("has_more", False)
                start_cursor = data.get("next_cursor")

        print(f"[{datetime.now()}] 获取到 {len(results)} 条日程")
        return results

    except Exception as e:
        print(f"[{datetime.now()}] 获取 Notion 数据失败: {e}")
        return []


def extract_event_info(page: dict) -> Optional[dict]:
    """从 Notion 页面提取事件信息"""
    props = page.get("properties", {})

    # 获取标题
    title = ""
    for name in ["Name", "Title", "标题", "名称", "名称", "事件", "Event"]:
        if name in props:
            title_prop = props[name]
            if title_prop.get("type") == "title" and title_prop["title"]:
                title = "".join([t.get("plain_text", "") for t in title_prop["title"]])
                break

    if not title:
        title = page.get("id", "未命名事件")[:8]

    # 获取日期
    event_date = None
    for name in ["Date", "日期", "日期范围", "Time", "时间"]:
        if name in props:
            date_prop = props[name]
            if date_prop.get("type") == "date":
                event_date = parse_notion_date(date_prop.get("date"))
                if event_date:
                    break

    # 获取描述
    description = ""
    for name in ["Description", "描述", "Notes", "备注"]:
        if name in props:
            desc_prop = props[name]
            if desc_prop.get("type") == "rich_text":
                description = "".join([t.get("plain_text", "") for t in desc_prop.get("rich_text", [])])
                break

    # 获取地点
    location = ""
    for name in ["Location", "地点", "Where"]:
        if name in props:
            loc_prop = props[name]
            if loc_prop.get("type") == "rich_text":
                location = "".join([t.get("plain_text", "") for t in loc_prop.get("rich_text", [])])
                break

    return {
        "uid": f"{page['id']}@notion-calendar",
        "title": title,
        "start": event_date,
        "description": description,
        "location": location,
        "url": page.get("url", "")
    }


def create_timezone() -> Timezone:
    """创建 ICS 时区信息"""
    tz_component = Timezone()
    tz_component.add('TZID', TIMEZONE)

    tz_standard = TimezoneStandard()
    tz_standard.add('DTSTART', datetime(1970, 1, 1))
    tz_standard.add('TZOFFSETTO', timedelta(hours=8))
    tz_standard.add('TZOFFSETFROM', timedelta(hours=8))
    tz_standard.add('TZNAME', 'CST')

    tz_component.add_component(tz_standard)
    return tz_component


def generate_ics_content(events: List[dict]) -> str:
    """生成 ICS 格式内容"""
    calendar = Calendar()
    calendar.add('prodid', '-//Notion Calendar Sync//MX//')
    calendar.add('version', '2.0')
    calendar.add('calscale', 'GREGORIAN')
    calendar.add('method', 'PUBLISH')
    calendar.add('x-wr-calname', 'Notion 日程')
    calendar.add('x-wr-timezone', TIMEZONE)

    # 添加时区
    calendar.add_component(create_timezone())

    for event in events:
        if not event.get("start"):
            continue

        vevent = Event()
        vevent.add('uid', event["uid"])
        vevent.add('summary', event["title"])
        vevent.add('dtstart', notion_datetime_to_ics_datetime(event["start"]))

        # 默认持续1小时
        end_time = event["start"] + timedelta(hours=1)
        vevent.add('dtend', notion_datetime_to_ics_datetime(end_time))

        if event.get("description"):
            vevent.add('description', event["description"])
        if event.get("location"):
            vevent.add('locat
