# Changelog

所有版本更新记录。

## [0.0.9] - 2026-03-08
### Changed
- 修正 metadata.yaml 中的 repo 字段为实际仓库地址
- 添加 CHANGELOG.md 版本更新记录

## [0.0.8] - 2026-03-08
### Removed
- 移除调试日志代码

## [0.0.7] - 2026-03-08
### Fixed
- 修复定时推送无法发送消息的问题，改用 OneBot API 直接发送私聊

## [0.0.6] - 2026-03-07
### Changed
- 支持多时段推送配置 (push_times)
- 移除冗余的 onebot_platform_id 配置项

## [0.0.5] - 2026-03-07
### Added
- 添加调试日志输出原始新闻内容

## [0.0.4] - 2026-03-07
### Added
- 集成 AstrBot 内置 LLM 进行中文摘要
- 新增 enable_llm_summary 和 llm_provider_id 配置项

## [0.0.3] - 2026-03-07
### Fixed
- 增强网络错误处理和超时设置

## [0.0.2] - 2026-03-07
### Fixed
- 修复 XML 命名空间解析问题

## [0.0.1] - 2026-03-07
### Added
- 初始版本
- RSS/Atom 新闻抓取
- 定时推送功能
- /ainews 命令支持
