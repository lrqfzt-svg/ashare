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
import json, os, sys, shutil
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

    tname = "收盘复盘模板版_2026-08-21.html"
    thtml = gt.build_template(tdata)
    with open(os.path.join(BASE, tname), "w", encoding="utf-8") as f: f.write(thtml)
    print(f"OK 模板版 -> {tname} ({len(thtml)} bytes)")

    if sync:
        ddir = os.path.join(BASE, "_tpl_share")
        os.makedirs(ddir, exist_ok=True)
        shutil.copy(os.path.join(BASE, tname), os.path.join(ddir, "index.html"))
        print(f"  同步 {tname} -> _tpl_share/index.html （外部 CloudStudio 部署可刷新分享链接）")

if __name__ == "__main__":
    main()
