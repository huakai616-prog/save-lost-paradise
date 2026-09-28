"""每日身体报告引擎。

读取 Apple 健康数据（经 iPhone 上的 Health Auto Export 导出），结合日程、天气和手动记录，
生成一份中文的每日身体报告（HTML 邮件 + Markdown + 结构化 JSON）。

只用 Python 标准库，方便在任何环境里直接运行。
"""

__version__ = "0.1.0"
