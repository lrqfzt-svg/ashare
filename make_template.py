# -*- coding: utf-8 -*-
"""
make_template.py — 一键生成【模板克隆版】HTML 报告的入口（仅模板版，不含网页版）

本仓库（D:/github/ashare）仅用于上传 GitHub，只维护「收盘复盘模板版」，
不维护「收盘复盘与明日研判」网页版。网页版相关文件（gen_web.py / web_data.json / _share）不在此仓库。

流程：
  1. 解析数据：优先读外部 JSON（template_data.json），若不存在则用内置样例并落盘，方便日后改。
  2. 调用 gen_template.build_template 生成模板版 HTML。
  3. 可选同步到分享目录（--sync），覆盖根 index.html（Cloudflare Pages 站点入口）。
  4. --archive 模式：额外把当日报告存为 reports/<date>.html（不覆盖历史），并回写
     archive.json（追加一条 {date,title,slug,up,down,amount,zt,dt}），供 archive.html 列表页使用。

用法：
  python3 make_template.py              # 用现有/样例数据生成模板版 + 覆盖 index.html
  python3 make_template.py --dump       # 仅把内置样例数据写成 JSON（供日后编辑）
  python3 make_template.py --sync       # 同 --archive（生成 index.html + reports/ + archive.json）
  python3 make_template.py --archive    # 生成 index.html + reports/<date>.html + 回写 archive.json
  python3 make_template.py tdata.json   # 指定外部数据
"""
import json, os, sys, shutil, time
import gen_template as gt

BASE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_JSON = os.path.join(BASE, "archive.json")
REPORTS_DIR = os.path.join(BASE, "reports")

def dump_samples():
    with open(os.path.join(BASE, "template_data.json"), "w", encoding="utf-8") as f:
        json.dump(gt.SAMPLE_TEMPLATE_DATA, f, ensure_ascii=False, indent=2)
    print("已导出 template_data.json（可编辑后传给生成器）")

def load_or_sample(path, sample):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    # 落盘样例，便于日后编辑
    with open(os.path.join(BASE, os.path.basename(path) if path else "sample.json"), "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    print(f"[info] 未找到 {path}，已落盘样例供编辑：{os.path.basename(path) if path else 'sample.json'}")
    return sample

def _date_slug(td):
    """从数据里解析 YYYY-MM-DD 作为文件名 slug，失败用今天。"""
    import re
    for k in ("title", "date", "generated"):
        s = str(td.get(k, ""))
        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            return m.group(1)
    return time.strftime("%Y-%m-%d")

def write_archive(td, slug):
    """回写 archive.json：追加/更新一条当日记录。"""
    rec = {
        "date": slug,
        "title": td.get("title", ""),
        "slug": slug,
        "up": td.get("change_overview", {}).get("up", ""),
        "down": td.get("change_overview", {}).get("down", ""),
        "amount": td.get("change_overview", {}).get("amount", ""),
        "zt": "",
        "dt": "",
    }
    # 尝试从 core_cards / emotion_panorama 取涨停跌停家数
    for c in td.get("core_cards", []):
        if "涨停" in c.get("label", "") and "触及" not in c.get("label", ""):
            rec["zt"] = c.get("value", "")
        if "封板" in c.get("label", ""):
            rec["zt"] = c.get("value", "")
    for c in td.get("emotion_panorama", []):
        if "涨停/跌停" in c.get("label", ""):
            v = str(c.get("value", ""))
            if "/" in v:
                a, b = v.split("/", 1)
                rec["zt"] = a.strip()
                rec["dt"] = b.strip()
    # 读取已有
    arr = []
    if os.path.exists(ARCHIVE_JSON):
        try:
            arr = json.load(open(ARCHIVE_JSON, encoding="utf-8"))
        except Exception:
            arr = []
    arr = [r for r in arr if r.get("date") != slug]  # 同日覆盖
    arr.append(rec)
    arr.sort(key=lambda r: r.get("date", ""), reverse=True)  # 新的在前
    with open(ARCHIVE_JSON, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False, indent=2)
    print(f"  归档记录 -> archive.json ({len(arr)} 条, 最新 {slug})")

def main():
    args = sys.argv[1:]
    if "--dump" in args:
        dump_samples(); return

    # --sync 与 --archive 等价：生成 index.html + reports/ + archive.json
    archive = ("--sync" in args) or ("--archive" in args)
    args = [a for a in args if a not in ("--sync", "--archive")]

    tpath = args[0] if len(args) > 0 else os.path.join(BASE, "template_data.json")

    tdata = load_or_sample(tpath, gt.SAMPLE_TEMPLATE_DATA)

    slug = _date_slug(tdata)
    thtml = gt.build_template(tdata)
    # 覆盖根 index.html（Cloudflare Pages 入口）
    with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
        f.write(thtml)
    print(f"OK index.html (最新) -> {slug} ({len(thtml)} bytes)")

    # 归档：每期独立存 reports/<date>.html，不覆盖历史
    os.makedirs(REPORTS_DIR, exist_ok=True)
    rpath = os.path.join(REPORTS_DIR, f"{slug}.html")
    with open(rpath, "w", encoding="utf-8") as f:
        f.write(thtml)
    print(f"  归档 -> reports/{slug}.html")

    write_archive(tdata, slug)

if __name__ == "__main__":
    main()
