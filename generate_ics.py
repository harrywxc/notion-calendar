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

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

TIMEZONE = "Asia/Shanghai"
tz = pytz.timezone(TIMEZONE)


def parse_notion_date(date_value: dict) -> Optional[datetime]:
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
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return dt.astimezone(pytz.UTC)


async def fetch_notion_events() -> List[dict]:
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
    props = page.get("properties", {})
    title = ""
    for name in ["Name", "Title", "标题", "名称", "事件", "Event"]:
        if name in props:
            title_prop = props[name]
            if title_prop.get("type") == "title" and title_prop["title"]:
                title = "".join([t.get("plain_text", "") for t in title_prop["title"]])
                break
    if not title:
        title = page.get("id", "未命名事件")[:8]
    event_start = None
    event_end = None
    for name in ["Date", "日期", "日期范围", "Time", "时间"]:
        if name in props:
            date_prop = props[name]
            if date_prop.get("type") == "date":
                date_value = date_prop.get("date")
                if date_value:
                    event_start = parse_notion_date({"start": date_value.get("start")})
                    if date_value.get("end"):
                        event_end = parse_notion_date({"start": date_value.get("end")})
                    if event_start:
                        break
    description = ""
    for name in ["Description", "描述", "Notes", "备注"]:
        if name in props:
            desc_prop = props[name]
            if desc_prop.get("type") == "rich_text":
                description = "".join([t.get("plain_text", "") for t in desc_prop.get("rich_text", [])])
                break
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
        "start": event_start,
        "end": event_end,
        "description": description,
        "location": location,
        "url": page.get("url", "")
    }


def create_timezone() -> Timezone:
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
    calendar = Calendar()
    calendar.add('prodid', '-//Notion Calendar Sync//MX//')
    calendar.add('version', '2.0')
    calendar.add('calscale', 'GREGORIAN')
    calendar.add('method', 'PUBLISH')
    calendar.add('x-wr-calname', 'Notion 日程')
    calendar.add('x-wr-timezone', TIMEZONE)
    calendar.add_component(create_timezone())
    for event in events:
        if not event.get("start"):
            continue
        vevent = Event()
        vevent.add('uid', event["uid"])
        vevent.add('summary', event["title"])
        vevent.add('dtstart', notion_datetime_to_ics_datetime(event["start"]))
        if event.get("end"):
            end_time = event["end"]
        else:
            end_time = event["start"] + timedelta(hours=1)
        vevent.add('dtend', notion_datetime_to_ics_datetime(end_time))
        if event.get("description"):
            vevent.add('description', event["description"])
        if event.get("location"):
            vevent.add('location', event["location"])
        now = datetime.now(pytz.UTC)
        vevent.add('created', now)
        vevent.add('dtstamp', now)
        calendar.add_component(vevent)
    return calendar.to_ical().decode('utf-8')


async def main():
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        print("错误：缺少 NOTION_TOKEN 或 NOTION_DATABASE_ID 环境变量")
        return
    pages = await fetch_notion_events()
    events = []
    for page in pages:
        event = extract_event_info(page)
        if event:
            events.append(event)
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
