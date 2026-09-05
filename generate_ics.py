#!/usr/bin/env python3
"""
从 Notion 数据库生成 ICS 文件（定向查询单个数据库）

改进（2026-09-06）：
- 按 NOTION_DATABASE_ID 精确查询数据库（原 /search 全工作区扫描会混入其他页面）
- 属性名可配置：NOTION_PROP_TITLE / NOTION_PROP_DATE / NOTION_PROP_DESC / NOTION_PROP_LOC
  （逗号分隔候选名，按顺序取第一个命中的属性；缺省值兼容中英文常用命名）
- 纯日期事件（无时间）输出为全天事件（VALUE=DATE）

用法: python generate_ics.py
环境变量: NOTION_TOKEN, NOTION_DATABASE_ID（必填）
可选: NOTION_PROP_TITLE / NOTION_PROP_DATE / NOTION_PROP_DESC / NOTION_PROP_LOC
"""

import os
from datetime import datetime, timedelta, date as date_cls
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

# 属性名可配置（逗号分隔候选，按序取第一个命中）
PROP_TITLE = [s.strip() for s in os.environ.get(
    "NOTION_PROP_TITLE", "Name,Title,标题,名称,事件,Event").split(",") if s.strip()]
PROP_DATE = [s.strip() for s in os.environ.get(
    "NOTION_PROP_DATE", "日期,Date,时间,Time,日期范围,Date range").split(",") if s.strip()]
PROP_DESC = [s.strip() for s in os.environ.get(
    "NOTION_PROP_DESC", "描述,Description,备注,Notes").split(",") if s.strip()]
PROP_LOC = [s.strip() for s in os.environ.get(
    "NOTION_PROP_LOC", "会议室,地点,Location,Where").split(",") if s.strip()]


def parse_notion_date(date_value: dict) -> tuple:
    """返回 (datetime 或 None, is_all_day: bool)。"""
    if not date_value:
        return None, False
    date_str = date_value.get("start")
    if not date_str:
        return None, False
    is_all_day = "T" not in date_str  # 纯日期 = 全天事件
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone(tz)
        else:
            dt = tz.localize(dt)
        return dt, is_all_day
    except Exception:
        return None, False


def notion_datetime_to_ics_datetime(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return dt.astimezone(pytz.UTC)


async def fetch_notion_events() -> List[dict]:
    """定向查询指定数据库（分页拉全量）。"""
    try:
        print(f"[{datetime.now()}] 正在查询数据库 {NOTION_DATABASE_ID} ...")
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


def _first_prop(props: dict, candidates: List[str]):
    for name in candidates:
        if name in props:
            return props[name]
    return None


def extract_event_info(page: dict) -> Optional[dict]:
    props = page.get("properties", {})

    # 标题（title 类型）
    title = ""
    title_prop = _first_prop(props, PROP_TITLE)
    if title_prop and title_prop.get("type") == "title" and title_prop["title"]:
        title = "".join([t.get("plain_text", "") for t in title_prop["title"]])
    if not title:
        title = page.get("id", "未命名事件")[:8]

    # 日期（date 类型；支持含 end 的范围）
    event_start, event_end = None, None
    is_all_day = False
    date_prop = _first_prop(props, PROP_DATE)
    if date_prop and date_prop.get("type") == "date" and date_prop.get("date"):
        date_value = date_prop["date"]
        event_start, is_all_day = parse_notion_date(date_value)
        if date_value.get("end"):
            end_dt, _ = parse_notion_date({"start": date_value.get("end")})
            event_end = end_dt

    # 描述（rich_text）
    description = ""
    desc_prop = _first_prop(props, PROP_DESC)
    if desc_prop and desc_prop.get("type") == "rich_text":
        description = "".join([t.get("plain_text", "") for t in desc_prop.get("rich_text", [])])

    # 地点（rich_text / select / multi_select 兼容）
    location = ""
    loc_prop = _first_prop(props, PROP_LOC)
    if loc_prop:
        lt = loc_prop.get("type")
        if lt == "rich_text":
            location = "".join([t.get("plain_text", "") for t in loc_prop.get("rich_text", [])])
        elif lt in ("select", "status") and loc_prop.get(lt):
            location = loc_prop[lt].get("name", "")
        elif lt == "multi_select":
            location = "、".join([o.get("name", "") for o in loc_prop.get("multi_select", [])])

    return {
        "uid": f"{page['id']}@notion-calendar",
        "title": title,
        "start": event_start,
        "end": event_end,
        "is_all_day": is_all_day,
        "description": description,
        "location": location,
        "url": page.get("url", ""),
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
        if event.get("is_all_day"):
            # 全天事件：VALUE=DATE，结束日不含（dtend = start + 1天）
            d0 = event["start"].date()
            d1 = d0 + timedelta(days=1)
            vevent.add('dtstart', d0)
            vevent.add('dtend', d1)
        else:
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
    print(f"[{datetime.now()}] 已生成 {output_file}，包含 {len(filtered_events)} 个事件"
          f"（范围：过去2周到未来2周，库内共{len(events)}条）")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
