# -*- coding: utf-8 -*-
"""
make_daily.py — ashare 一键流水线（重做版）

流程：collect.py 采集 → gen_report.py 渲染 → 更新 archive.json → 可推送 git

用法：
  python3 make_daily.py            # 采集+渲染+更新归档
  python3 make_daily.py --no-push  # 仅本地，不 git 推送
"""
import json, os, subprocess, sys, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
COLLECTED = os.path.join(BASE, "collected.json")
REPORTS = os.path.join(BASE, "reports")
ARCHIVE = os.path.join(BASE, "archive.json")


def load_json(p):
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def update_archive(c):
    """把当期报告追加进 archive.json（同日覆盖）。"""
    date = c.get("trade_date")
    if not date:
        return
    os.makedirs(REPORTS, exist_ok=True)
    entry = {
        "date": date,
        "title": f"📊 A股市场复盘报告 · {date}",
        "slug": date,
        "up": str(c.get("up") or "—"),
        "down": str(c.get("down") or "—"),
        "amount": f"{c.get('amount_yi'):.4f}万亿" if c.get("amount_yi") else "—",
        "zt": str(c.get("zt") or "—"),
        "dt": str(c.get("dt") or "—"),
    }
    arch = load_json(ARCHIVE) or []
    arch = [x for x in arch if x.get("date") != date]
    arch.insert(0, entry)
    arch.sort(key=lambda x: x["date"], reverse=True)
    save_json(ARCHIVE, arch)
    print(f"[make] archive.json 更新：{date}（共 {len(arch)} 条）")


def main():
    no_push = "--no-push" in sys.argv
    env = dict(os.environ)
    npm = os.path.expanduser(r"~\AppData\Roaming\npm")
    if npm not in env.get("PATH", ""):
        env["PATH"] = npm + os.pathsep + env.get("PATH", "")
    # 1) 采集
    r = subprocess.run([sys.executable, os.path.join(BASE, "collect.py")],
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=600)
    if r.returncode != 0:
        print("[make] collect.py 失败：", r.stderr[-300:])
        sys.exit(1)
    with open(COLLECTED, "w", encoding="utf-8") as f:
        f.write(r.stdout)
    c = json.loads(r.stdout)
    # 2) 渲染
    subprocess.run([sys.executable, os.path.join(BASE, "gen_report.py")], check=True)
    # 2.5) 门户首页
    subprocess.run([sys.executable, os.path.join(BASE, "gen_index.py")], check=True)
    # 3) 归档
    update_archive(c)
    # 4) 推送（默认）
    if no_push:
        print("[make] --no-push，跳过 git push")
        return
    date = c.get("trade_date")
    try:
        _prod = ["index.html", "archive.html", "archive.json",
                 "collected.json", "a-share-report-*.html", "reports"]
        subprocess.run(["git", "add", *_prod], cwd=BASE, check=True)
        subprocess.run(["git", "commit", "-m", f"auto: 复盘 {date}"],
                       cwd=BASE, check=True)
        subprocess.run(["git", "push"], cwd=BASE, check=True)
        print(f"[make] git push 完成：auto: 复盘 {date}")
    except subprocess.CalledProcessError as e:
        print(f"[make] git 操作失败：{e}")


if __name__ == "__main__":
    main()
