#!/usr/bin/env python3
"""
从 Notion 数据库生成 ICS 文件
"""

import os
from datetime import datetime, timedelta
from typing import Optional, List
import pytz

from notion_client import AsyncClient
from icalendar import Calendar, Event, Timezone, TimezoneStandard

# 从环境变量读取配置
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

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

        client = AsyncClient(auth=NOTION_TOKEN)

        results = []
        has_more = True
        start_cursor = None

        while has_more:
            response = await client.databases.query(
                database_id=NOTION_DATABASE_ID,
                start_cursor=start_cursor,
                page_size=100
            )
            results.extend(response.get("results", []))
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

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
            vevent.add('location', event["location"])

        # 添加创建时间和更新时间
        now = datetime.now(pytz.UTC)
        vevent.add('created', now)
        vevent.add('dtstamp', now)

        calendar.add_component(vevent)

    return calendar.to_ical().decode('utf-8')


async def main():
    """主函数"""
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        print("错误：缺少 NOTION_TOKEN 或 NOTION_DATABASE_ID 环境变量")
        return

    pages = await fetch_notion_events()

    events = []
    for page in pages:
        event = extract_event_info(page)
        if event:
            events.append(event)

    # 过滤时间范围：过去2周到未来2周
    now = datetime.now(tz)
    start_date = now - timedelta(weeks=2)
    end_date = now + timedelta(weeks=2)

    filtered_events = []
    for event in events:
        if event.get("start"):
            event_start = event["start"]
            if start_date <= event_start <= end_date:
                filtered_events.append(event)

    ics_content = generate_ics_content(filtered_events)

    output_file = "calendar.ics"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(ics_content)

    print(f"[{datetime.now()}] 已生成 {output_file}，包含 {len(filtered_events)} 个事件（范围：过去2周到未来2周，总计{len(events)}条）")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
