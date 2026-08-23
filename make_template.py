# -*- coding: utf-8 -*-
"""
make_template.py — 一键生成【模板克隆版】HTML 报告的入口（仅模板版，不含网页版）

本仓库（D:/github/ashare）仅用于上传 GitHub，只维护「收盘复盘模板版」，
不维护「收盘复盘与明日研判」网页版。网页版相关文件（gen_web.py / web_data.json / _share）不在此仓库。

流程：
  1. 解析数据：优先读外部 JSON（template_data.json），若不存在则用内置样例并落盘，方便日后改。
  2. 调用 gen_template.build_template 生成模板版 HTML。
  3. 可选同步到分享目录（--sync），覆盖 _tpl_share/index.html（部署由外部 CloudStudio 完成）。

用法：
  python3 make_template.py              # 用现有/样例数据生成模板版
  python3 make_template.py --dump       # 仅把内置样例数据写成 JSON（供日后编辑）
  python3 make_template.py --sync       # 生成后同步到 _tpl_share/
  python3 make_template.py tdata.json   # 指定外部数据
"""
import json, os, sys, shutil, time
import gen_template as gt

BASE = os.path.dirname(os.path.abspath(__file__))

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

def main():
    args = sys.argv[1:]
    if "--dump" in args:
        dump_samples(); return

    sync = "--sync" in args
    args = [a for a in args if a not in ("--sync",)]

    tpath = args[0] if len(args) > 0 else os.path.join(BASE, "template_data.json")

    tdata = load_or_sample(tpath, gt.SAMPLE_TEMPLATE_DATA)

    # 文件名按数据日期动态生成（从 title/date 解析 YYYY-MM-DD，失败则用今天）
    def _date_slug(td):
        import re
        for k in ("title", "date", "generated"):
            s = str(td.get(k, ""))
            m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
            if m:
                return m.group(1)
        return time.strftime("%Y-%m-%d")
    tname = f"收盘复盘模板版_{_date_slug(tdata)}.html"
    thtml = gt.build_template(tdata)
    with open(os.path.join(BASE, tname), "w", encoding="utf-8") as f: f.write(thtml)
    print(f"OK 模板版 -> {tname} ({len(thtml)} bytes)")

    if sync:
        # Cloudflare Pages 入口固定为根 index.html；直接覆盖之（确保入库可部署）
        shutil.copy(os.path.join(BASE, tname), os.path.join(BASE, "index.html"))
        print(f"  同步 {tname} -> index.html （Cloudflare Pages 站点入口）")

if __name__ == "__main__":
    main()
