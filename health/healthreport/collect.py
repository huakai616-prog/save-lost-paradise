"""把 Google Drive 连接器下载的文件落到磁盘上。

每日任务里，Claude 用 Google Drive 连接器的 download_file_content 下载 Health Auto Export
的 JSON。连接器返回的是 {"content": <base64>, "id", "mimeType", "title"}：
  - 结果较大时，Claude Code 会把它存成 ~/.claude/projects/<项目>/tool-results/mcp-*download_file_content*.txt；
  - 结果较小时，它直接出现在对话记录 ~/.claude/projects/<项目>/<会话>.jsonl 里。
这个模块把两处都扫一遍，解码后写成真正的文件，免得让模型把几十 KB 的 base64 再抄写一遍。
"""

import base64
import glob
import json
import os
import re
import time


def _candidates_from_obj(obj):
    """在任意嵌套的 JSON 里找 {"content": base64, "title": ...} 这样的下载结果。"""
    if isinstance(obj, dict):
        if isinstance(obj.get("content"), str) and ("title" in obj or "mimeType" in obj) and "id" in obj:
            yield obj
        for v in obj.values():
            yield from _candidates_from_obj(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _candidates_from_obj(v)
    elif isinstance(obj, str) and obj.startswith("{") and '"content"' in obj:
        try:
            yield from _candidates_from_obj(json.loads(obj))
        except ValueError:
            pass


def _safe_name(title, file_id):
    name = re.sub(r"[\\/:*?\"<>|\s]+", "_", title or file_id).strip("._") or file_id
    return name


def scan(roots=None, since_hours=24, title_filter=None):
    """返回 {file_id: (mtime, title, mimeType, bytes)}，同一个文件取最新的一次下载。"""
    roots = roots or [os.path.expanduser("~/.claude/projects")]
    cutoff = time.time() - since_hours * 3600
    found = {}

    def consider(obj, mtime):
        for c in _candidates_from_obj(obj):
            title = c.get("title") or ""
            if title_filter and not re.search(title_filter, title, re.I):
                continue
            try:
                data = base64.b64decode(c["content"], validate=False)
            except (ValueError, TypeError):
                continue
            fid = c.get("id") or title
            if fid not in found or found[fid][0] <= mtime:
                found[fid] = (mtime, title, c.get("mimeType"), data)

    for root in roots:
        # 1) 大结果：tool-results 里的独立文件
        for p in glob.glob(os.path.join(root, "**", "tool-results", "*download_file_content*"), recursive=True):
            mt = os.path.getmtime(p)
            if mt < cutoff:
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    consider(json.load(f), mt)
            except (ValueError, OSError):
                continue
        # 2) 小结果：会话记录里的 tool_result
        for p in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            mt = os.path.getmtime(p)
            if mt < cutoff:
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if "mimeType" not in line:   # 下载结果里一定有 mimeType
                            continue
                        try:
                            consider(json.loads(line), mt + i * 1e-6)
                        except ValueError:
                            continue
            except OSError:
                continue
    return found


EXT = {"application/json": ".json", "text/csv": ".csv", "application/zip": ".zip", "text/plain": ".txt"}


def write(found, out_dir):
    """文件名 = 标题 + Drive 文件 ID 前 6 位（不同文件夹里可能有同名文件，比如指标和体能训练两个自动导出）。"""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for fid, (mtime, title, mime, data) in sorted(found.items(), key=lambda kv: kv[1][0]):
        stem, ext = os.path.splitext(_safe_name(title, fid))
        if ext.lower() not in (".json", ".csv", ".zip", ".xml", ".txt"):
            stem, ext = stem + ext, EXT.get(mime or "", "")
        name = f"{stem}__{re.sub(r'[^A-Za-z0-9]', '', fid)[:6]}{ext}"
        path = os.path.join(out_dir, name)
        with open(path, "wb") as f:
            f.write(data)
        written.append((path, len(data)))
    return written
