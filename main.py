import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional
from difflib import SequenceMatcher

import aiohttp

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp


@register("ai_news", "战狼阿米诺", "AI 新闻每日推送插件", "0.0.3")
class AINewsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running = True
        self._feeds_data = None
        self._load_feeds()

    def _load_feeds(self):
        """加载 feeds.json 配置"""
        feeds_path = os.path.join(os.path.dirname(__file__), "feeds.json")
        try:
            with open(feeds_path, "r", encoding="utf-8") as f:
                self._feeds_data = json.load(f)
            logger.info("AI News: feeds.json 加载成功")
        except Exception as e:
            logger.error(f"AI News: 加载 feeds.json 失败: {e}")
            self._feeds_data = {"feeds": {"aggregators": [], "labs": []}}

    async def initialize(self):
        """插件初始化，启动定时任务"""
        if self.config.get("enable_scheduled_push", True):
            self._scheduler_task = asyncio.create_task(self._scheduler())
            logger.info("AI News: 定时推送任务已启动")

    async def terminate(self):
        """插件卸载时停止定时任务"""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("AI News: 插件已停止")

    async def _scheduler(self):
        """定时任务调度器"""
        await asyncio.sleep(5)
        
        while self._running:
            try:
                push_hour = self.config.get("push_hour", 8)
                push_minute = self.config.get("push_minute", 0)
                
                now = datetime.now()
                target_time = now.replace(
                    hour=push_hour, minute=push_minute, second=0, microsecond=0
                )
                
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                wait_seconds = (target_time - now).total_seconds()
                logger.info(f"AI News: 下次推送时间 {target_time}, 等待 {wait_seconds:.0f} 秒")
                
                await asyncio.sleep(wait_seconds)
                
                if self._running:
                    await self._do_scheduled_push()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"AI News: 定时任务出错: {e}")
                await asyncio.sleep(60)

    async def _do_scheduled_push(self):
        """执行定时推送"""
        try:
            news_list = await self._fetch_all_news()
            if not news_list:
                logger.warning("AI News: 没有获取到新闻")
                return
            
            message_text = self._format_news_message(news_list)
            
            subscribers = self.config.get("subscribers", [])
            admin_qq = self.config.get("admin_qq", "")
            
            if admin_qq and admin_qq not in subscribers:
                subscribers = [admin_qq] + list(subscribers)
            
            for qq in subscribers:
                if qq:
                    umo = f"aiocqhttp:FriendMessage:{qq}"
                    try:
                        chain = MessageChain().message(message_text)
                        await self.context.send_message(umo, chain)
                        logger.info(f"AI News: 已推送给 {qq}")
                    except Exception as e:
                        logger.error(f"AI News: 推送给 {qq} 失败: {e}")
                        
        except Exception as e:
            logger.error(f"AI News: 定时推送执行失败: {e}")

    async def _fetch_all_news(self) -> list:
        """获取所有 RSS 源的新闻"""
        all_news = []
        feeds = []
        
        if self._feeds_data:
            feeds.extend(self._feeds_data.get("feeds", {}).get("aggregators", []))
            feeds.extend(self._feeds_data.get("feeds", {}).get("labs", []))
        
        feeds.sort(key=lambda x: x.get("priority", 99))
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60, connect=15)
        ) as session:
            tasks = [self._fetch_feed(session, feed) for feed in feeds]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"AI News: 获取 {feeds[i].get('name', 'Unknown')} 失败: {result}")
                elif result:
                    all_news.extend(result)
        
        hours_range = self.config.get("news_hours_range", 24)
        all_news = self._filter_by_time(all_news, hours_range)
        all_news = self._deduplicate(all_news)
        all_news = self._categorize(all_news)
        
        return all_news

    async def _fetch_feed(self, session: aiohttp.ClientSession, feed: dict) -> list:
        """获取单个 RSS 源"""
        url = feed.get("url", "")
        name = feed.get("name", "Unknown")
        
        if not url:
            return []
        
        try:
            async with session.get(url, ssl=False) as response:
                if response.status != 200:
                    logger.warning(f"AI News: {name} 返回状态码 {response.status}")
                    return []
                
                content = await response.text()
                return self._parse_rss(content, name, feed.get("priority", 99))
                
        except aiohttp.ClientError as e:
            logger.warning(f"AI News: 获取 {name} 网络错误: {type(e).__name__}: {e}")
            return []
        except asyncio.TimeoutError:
            logger.warning(f"AI News: 获取 {name} 超时")
            return []
        except Exception as e:
            logger.warning(f"AI News: 获取 {name} 出错: {type(e).__name__}: {e}")
            return []

    def _parse_rss(self, content: str, source_name: str, priority: int) -> list:
        """解析 RSS/Atom XML"""
        items = []
        
        try:
            content = self._clean_xml_namespaces(content)
            root = ET.fromstring(content)
            
            rss_items = root.findall(".//item")
            if rss_items:
                for item in rss_items:
                    news = self._parse_rss_item(item, source_name, priority)
                    if news:
                        items.append(news)
            
            atom_entries = root.findall(".//entry")
            for entry in atom_entries:
                news = self._parse_atom_entry(entry, source_name, priority)
                if news:
                    items.append(news)
                    
        except ET.ParseError as e:
            logger.warning(f"AI News: 解析 {source_name} XML 失败: {e}")
        except Exception as e:
            logger.warning(f"AI News: 处理 {source_name} 出错: {e}")
        
        return items

    def _clean_xml_namespaces(self, content: str) -> str:
        """清理 XML 命名空间，使解析更简单"""
        content = re.sub(r'<\?xml[^>]*\?>', '', content)
        content = re.sub(r'\sxmlns(?::[a-zA-Z0-9_-]+)?=["\'][^"\']*["\']', '', content)
        content = re.sub(r'<([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)', r'<\2', content)
        content = re.sub(r'</([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)', r'</\2', content)
        content = re.sub(r'\s([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)=', r' \2=', content)
        return content

    def _parse_rss_item(self, item: ET.Element, source_name: str, priority: int) -> Optional[dict]:
        """解析 RSS item"""
        title_elem = item.find("title")
        link_elem = item.find("link")
        pub_date_elem = item.find("pubDate")
        desc_elem = item.find("description")
        
        title = title_elem.text if title_elem is not None and title_elem.text else ""
        link = link_elem.text if link_elem is not None and link_elem.text else ""
        pub_date = pub_date_elem.text if pub_date_elem is not None and pub_date_elem.text else ""
        description = desc_elem.text if desc_elem is not None and desc_elem.text else ""
        
        if not title or not link:
            return None
        
        description = re.sub(r'<[^>]+>', '', description)
        description = description[:200] + "..." if len(description) > 200 else description
        
        return {
            "title": title.strip(),
            "link": link.strip(),
            "pub_date": self._parse_date(pub_date),
            "description": description.strip(),
            "source": source_name,
            "priority": priority,
            "category": ""
        }

    def _parse_atom_entry(self, entry: ET.Element, source_name: str, priority: int) -> Optional[dict]:
        """解析 Atom entry"""
        title_elem = entry.find("title")
        link_elem = entry.find("link")
        pub_elem = entry.find("published") or entry.find("updated")
        summary_elem = entry.find("summary") or entry.find("content")
        
        title = title_elem.text if title_elem is not None and title_elem.text else ""
        link = ""
        if link_elem is not None:
            link = link_elem.get("href", "") or (link_elem.text or "")
        pub_date = pub_elem.text if pub_elem is not None and pub_elem.text else ""
        description = summary_elem.text if summary_elem is not None and summary_elem.text else ""
        
        if not title or not link:
            return None
        
        description = re.sub(r'<[^>]+>', '', description)
        description = description[:200] + "..." if len(description) > 200 else description
        
        return {
            "title": title.strip(),
            "link": link.strip(),
            "pub_date": self._parse_date(pub_date),
            "description": description.strip(),
            "source": source_name,
            "priority": priority,
            "category": ""
        }

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期字符串"""
        if not date_str:
            return None
        
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        
        date_str = date_str.strip()
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        
        return None

    def _filter_by_time(self, news_list: list, hours: int) -> list:
        """按时间过滤新闻"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        filtered = []
        
        for news in news_list:
            pub_date = news.get("pub_date")
            if pub_date is None:
                filtered.append(news)
            elif pub_date >= cutoff:
                filtered.append(news)
        
        return filtered

    def _deduplicate(self, news_list: list) -> list:
        """去重"""
        seen_links = set()
        seen_titles = []
        unique = []
        
        news_list.sort(key=lambda x: x.get("priority", 99))
        
        for news in news_list:
            link = news.get("link", "")
            title = news.get("title", "")
            
            if link in seen_links:
                continue
            
            is_similar = False
            for seen_title in seen_titles:
                if SequenceMatcher(None, title.lower(), seen_title.lower()).ratio() > 0.8:
                    is_similar = True
                    break
            
            if is_similar:
                continue
            
            seen_links.add(link)
            seen_titles.append(title)
            unique.append(news)
        
        return unique

    def _categorize(self, news_list: list) -> list:
        """分类新闻"""
        categories = {
            "model_release": {
                "name": "🚀 模型发布",
                "keywords": ["release", "launch", "announce", "gpt", "claude", "gemini", 
                           "grok", "glm", "llama", "mistral", "发布", "推出"]
            },
            "research": {
                "name": "📄 研究论文",
                "keywords": ["paper", "research", "study", "benchmark", "arxiv", 
                           "论文", "研究"]
            },
            "industry": {
                "name": "💼 行业动态",
                "keywords": ["funding", "acquisition", "hire", "layoff", "ipo", 
                           "融资", "收购", "上市"]
            },
            "product": {
                "name": "📦 产品更新",
                "keywords": ["feature", "update", "api", "pricing", "beta", 
                           "功能", "更新", "价格"]
            },
            "opinion": {
                "name": "💬 观点评论",
                "keywords": ["think", "believe", "future", "prediction", "opinion",
                           "观点", "评论", "预测"]
            }
        }
        
        for news in news_list:
            title_lower = news.get("title", "").lower()
            desc_lower = news.get("description", "").lower()
            text = title_lower + " " + desc_lower
            
            news["category"] = "💬 其他"
            
            for cat_key, cat_info in categories.items():
                for keyword in cat_info["keywords"]:
                    if keyword.lower() in text:
                        news["category"] = cat_info["name"]
                        break
                if news["category"] != "💬 其他":
                    break
        
        return news_list

    def _format_news_message(self, news_list: list) -> str:
        """格式化新闻消息"""
        now = datetime.now()
        date_str = now.strftime("%Y年%m月%d日")
        
        sources_count = len(set(n.get("source", "") for n in news_list))
        
        message = f"📰 AI 新闻简报\n"
        message += f"日期：{date_str}\n"
        message += f"来源：已检查 {sources_count} 个订阅源\n"
        message += f"时间范围：过去 {self.config.get('news_hours_range', 24)} 小时\n"
        message += f"共收录：{len(news_list)} 条新闻\n"
        message += "\n" + "=" * 30 + "\n\n"
        
        categories_order = [
            "🚀 模型发布",
            "📄 研究论文", 
            "💼 行业动态",
            "📦 产品更新",
            "💬 观点评论",
            "💬 其他"
        ]
        
        categorized = {}
        for news in news_list:
            cat = news.get("category", "💬 其他")
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(news)
        
        for cat in categories_order:
            if cat in categorized and categorized[cat]:
                message += f"{cat} ({len(categorized[cat])}条)\n\n"
                
                for i, news in enumerate(categorized[cat][:10], 1):
                    title = news.get("title", "无标题")
                    desc = news.get("description", "")
                    source = news.get("source", "未知来源")
                    link = news.get("link", "")
                    
                    message += f"{i}️⃣ {title}\n"
                    if desc:
                        message += f"{desc[:100]}{'...' if len(desc) > 100 else ''}\n"
                    message += f"来源：{source}\n"
                    message += f"{link}\n\n"
                
                if len(categorized[cat]) > 10:
                    message += f"... 还有 {len(categorized[cat]) - 10} 条\n\n"
                
                message += "-" * 20 + "\n\n"
        
        message += "⚠️ 覆盖缺口提醒\n\n"
        message += "以下 AI 实验室未提供 RSS，重大发布请手动检查：\n"
        message += "• 智谱 AI (GLM 系列)\n"
        message += "• DeepSeek\n"
        message += "• 百度 (文心一言)\n"
        message += "• 阿里 (通义千问)\n"
        message += "• 字节跳动 (豆包)\n"
        
        return message

    @filter.command("ainews")
    async def cmd_ainews(self, event: AstrMessageEvent):
        """获取 AI 新闻 - 使用 /ainews 立即获取, /ainews sub 订阅, /ainews unsub 取消订阅"""
        sender_id = event.get_sender_id()
        message_str = event.message_str.strip()
        
        parts = message_str.split()
        sub_cmd = parts[1] if len(parts) > 1 else ""
        
        if sub_cmd == "sub":
            yield event.plain_result(await self._handle_subscribe(sender_id))
            return
        
        if sub_cmd == "unsub":
            yield event.plain_result(await self._handle_unsubscribe(sender_id))
            return
        
        if sub_cmd == "status":
            yield event.plain_result(self._handle_status(sender_id))
            return
        
        yield event.plain_result("正在获取 AI 新闻，请稍候...")
        
        try:
            news_list = await self._fetch_all_news()
            
            if not news_list:
                yield event.plain_result("暂无新闻或获取失败，请稍后重试。")
                return
            
            message_text = self._format_news_message(news_list)
            yield event.plain_result(message_text)
            
        except Exception as e:
            logger.error(f"AI News: 获取新闻失败: {e}")
            yield event.plain_result(f"获取新闻失败: {e}")

    async def _handle_subscribe(self, sender_id: str) -> str:
        """处理订阅"""
        subscribers = list(self.config.get("subscribers", []))
        
        if sender_id in subscribers:
            return f"你已经订阅过了！每日 {self.config.get('push_hour', 8)}:{self.config.get('push_minute', 0):02d} 会收到 AI 新闻推送。"
        
        subscribers.append(sender_id)
        self.config["subscribers"] = subscribers
        self.config.save_config()
        
        return f"订阅成功！每日 {self.config.get('push_hour', 8)}:{self.config.get('push_minute', 0):02d} 会收到 AI 新闻推送。"

    async def _handle_unsubscribe(self, sender_id: str) -> str:
        """处理取消订阅"""
        subscribers = list(self.config.get("subscribers", []))
        
        if sender_id not in subscribers:
            return "你还没有订阅过。"
        
        subscribers.remove(sender_id)
        self.config["subscribers"] = subscribers
        self.config.save_config()
        
        return "已取消订阅。"

    def _handle_status(self, sender_id: str) -> str:
        """查看订阅状态"""
        subscribers = self.config.get("subscribers", [])
        admin_qq = self.config.get("admin_qq", "")
        push_hour = self.config.get("push_hour", 8)
        push_minute = self.config.get("push_minute", 0)
        enabled = self.config.get("enable_scheduled_push", True)
        
        is_subscribed = sender_id in subscribers or sender_id == admin_qq
        
        status = "📊 AI 新闻订阅状态\n\n"
        status += f"定时推送：{'✅ 已启用' if enabled else '❌ 已禁用'}\n"
        status += f"推送时间：每日 {push_hour}:{push_minute:02d}\n"
        status += f"订阅状态：{'✅ 已订阅' if is_subscribed else '❌ 未订阅'}\n"
        status += f"订阅人数：{len(subscribers)} 人\n"
        
        if sender_id == admin_qq:
            status += f"\n你是管理员，将始终收到推送。"
        
        return status
