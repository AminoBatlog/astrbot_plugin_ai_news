# AstrBot AI 新闻推送插件

每日定时推送 AI 行业新闻到 QQ，支持 OneBot v11 协议。

## 功能特点

- **定时推送**：每日定时自动推送 AI 新闻简报
- **多源聚合**：从 10+ 个精选 RSS 源获取新闻
- **智能分类**：自动将新闻分为模型发布、研究论文、行业动态等类别
- **去重过滤**：自动去除重复新闻
- **订阅管理**：支持用户自主订阅/取消订阅

## 数据源

### 聚合器
- TLDR AI - 每日 AI 行业摘要
- Hacker News - 技术社区热点
- The Decoder - AI 专题新闻
- Last Week in AI - 每周 AI 汇总
- Marktechpost - AI 研究报道

### 实验室博客
- Anthropic News - Claude 发布动态
- OpenAI Research - GPT 研究进展
- xAI News - Grok 发布动态
- Google AI - Gemini/DeepMind 公告
- Claude Code Changelog - CLI 更新

## 安装

1. 将插件文件夹放入 AstrBot 的 `data/plugins/` 目录
2. 在 AstrBot WebUI 中启用插件
3. 配置管理员 QQ 号和推送时间

## 配置说明

在 AstrBot WebUI 的插件配置中设置：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| admin_qq | 管理员 QQ 号 | - |
| subscribers | 订阅者 QQ 号列表 | [] |
| push_hour | 推送时间（小时） | 8 |
| push_minute | 推送时间（分钟） | 0 |
| enable_scheduled_push | 启用定时推送 | true |
| news_hours_range | 新闻时间范围（小时） | 24 |

## 使用方法

### 指令

| 指令 | 说明 |
|------|------|
| `/ainews` | 立即获取 AI 新闻 |
| `/ainews sub` | 订阅每日推送 |
| `/ainews unsub` | 取消订阅 |
| `/ainews status` | 查看订阅状态 |

### 消息格式

新闻推送采用分类展示，每条新闻包含：
- 标题
- 摘要
- 来源
- 原文链接

## 覆盖缺口

以下 AI 实验室暂无 RSS 源，重大发布需手动关注：
- 智谱 AI (GLM 系列)
- DeepSeek
- 百度 (文心一言)
- 阿里 (通义千问)
- 字节跳动 (豆包)
- Mistral AI
- Meta AI

## 依赖

- aiohttp >= 3.8.0

## 许可证

AGPL-3.0

## 作者

战狼阿米诺

## 致谢

- RSS 源参考自 [ai-news-skill](https://github.com/tensakulabs/ai-news-skill)
- 实验室博客 RSS 由 [Olshansk/rss-feeds](https://github.com/Olshansk/rss-feeds) 生成
