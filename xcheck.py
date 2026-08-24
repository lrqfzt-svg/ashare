# -*- coding: utf-8 -*-
"""
xcheck.py — 三源交叉验证（东财 / 同花顺 / 问财）

目的：对同一交易日(2026-08-21)的同一维度，分别用三源取数并比对一致性。
约束：
  - 东财 mx-data 免费版每日 150 次配额易耗尽，耗尽时只能用 collect.py 中的
    MX_FALLBACK 真实缓存值（8-21 实测）作为静态对照基准，标注 [缓存]。
  - 同花顺 hithink-finance 无直接「板块资金排名」命令，板块维度不参与该源对照。
  - 问财两个 skill（market-query / sector-selector）通过 openapi.iwencai.com 实时取数。

输出：结构化 JSON 到 stdout，并打印一份人类可读的对比表到 stderr。
"""
import json, os, sys, subprocess, shutil, datetime

IWENCAI_KEY = os.environ.get("IWENCAI_API_KEY", "")
IWENCAI_BASE = os.environ.get("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
MK = "C:/Users/Administrator/.iwencai-skillhub/skills/hithink-market-query/scripts/cli.py"
SC = "C:/Users/Administrator/.iwencai-skillhub/skills/hithink-sector-selector/scripts/cli.py"
HITHINK = "hithink-finance"
MX_DATA = "C:/Users/Administrator/.workbuddy/skills/mx-data/mx_data.py"
MX_SEARCH = "C:/Users/Administrator/.workbuddy/skills/mx-search/mx_search.py"

# 东财 8-21 真实缓存（collect.py MX_FALLBACK），作为静态对照基准
EMX = {
    "sector_in": [("通信设备", 85.32), ("有色金属", 88.29), ("黄金", 13.78), ("半导体", 6.23)],
    "sector_out": [("医药生物", -91.11), ("银行", -8.49)],
}

TRADE_DATE = "2026-08-21"


def log(m):
    sys.stderr.write(f"[xcheck] {m}\n"); sys.stderr.flush()


def iwencai(script, query, limit=10, timeout=40):
    if not IWENCAI_KEY:
        log("IWENCAI_API_KEY 未设置"); return None
    try:
        r = subprocess.run([sys.executable, script, "--query", query,
                            "--limit", str(limit), "--timeout", str(timeout)],
                           capture_output=True, encoding="utf-8", timeout=timeout + 10)
        if r.returncode != 0:
            log(f"iwencai rc={r.returncode} {r.stderr[:120]}"); return None
        return json.loads(r.stdout)
    except Exception as e:
        log(f"iwencai except: {e}"); return None


def parse_flow(d):
    """问财 market-query 板块主力净买入额 -> [(name, yi)]，单位元转亿。"""
    out = []
    for x in (d or {}).get("datas", []):
        name = x.get("指数简称") or x.get("板块名称")
        # 取最后一个数值字段（带日期后缀的主力净买入额）
        keys = [k for k in x if "净买入" in k or "净流入" in k]
        if not keys:
            # 兜底：最后一个非名称字段
            skip = {"指数代码", "指数简称", "指数类型", "成分领域", "板块名称", "板块代码"}
            keys = [k for k in x if k not in skip]
        if not name or not keys:
            continue
        v = x[keys[-1]]
        try:
            out.append((name, round(float(v) / 1e8, 2)))
        except Exception:
            pass
    return out


def parse_sector_chg(d):
    out = []
    for x in (d or {}).get("datas", []):
        name = x.get("指数简称") or x.get("板块名称")
        keys = [k for k in x if "涨跌幅" in k]
        if not name or not keys:
            continue
        try:
            out.append((name, float(x[keys[-1]])))
        except Exception:
            pass
    return out


def hithink(args, timeout=120):
    # 同 collect.py：优先解析 npm 安装路径
    exe = HITHINK
    for ext in ("", ".cmd", ".ps1"):
        p = shutil.which(HITHINK + ext)
        if p:
            exe = p; break
    else:
        for d in (os.path.expanduser(r"~\AppData\Roaming\npm"),
                  r"C:\Program Files\nodejs", "/usr/local/bin"):
            if os.path.isdir(d):
                for ext in ("", ".cmd"):
                    cand = os.path.join(d, HITHINK + ext)
                    if os.path.isfile(cand):
                        exe = cand; break
    try:
        env = dict(os.environ)
        npm = os.path.expanduser(r"~\AppData\Roaming\npm")
        if npm not in env.get("PATH", ""):
            env["PATH"] = npm + os.pathsep + env.get("PATH", "")
        r = subprocess.run([exe] + args, capture_output=True, encoding="utf-8", env=env, timeout=timeout)
        if r.returncode == 0 and r.stdout.strip().startswith("{"):
            return json.loads(r.stdout)
        log(f"hithink {args[0]} rc={r.returncode} out0={r.stdout[:60]!r}")
        return None
    except Exception as e:
        log(f"hithink {args[0]} except: {e}")
        return None


def main():
    log("=== 三源交叉验证 start ===")
    report = {"trade_date": TRADE_DATE, "sources": {}, "checks": []}

    # ---- 源1：问财 market-query 板块主力净买入额 ----
    mq = iwencai(MK, f"{TRADE_DATE} 主力净买入额排名前15的行业板块", limit=15)
    mq_flow = parse_flow(mq)
    report["sources"]["iwencai_market_query"] = {
        "ok": bool(mq), "count": len(mq_flow),
        "sector_flow_top": [{"name": n, "val_yi": v} for n, v in mq_flow[:10]]}

    # ---- 源2：问财 sector-selector 行业板块涨幅 ----
    sc = iwencai(SC, f"{TRADE_DATE} 涨幅前15的行业板块", limit=15)
    sc_chg = parse_sector_chg(sc)
    report["sources"]["iwencai_sector_selector"] = {
        "ok": bool(sc), "count": len(sc_chg),
        "sector_chg_top": [{"name": n, "chg_pct": v} for n, v in sc_chg[:10]]}

    # ---- 源3：同花顺 涨停池 + 连板（个股维度，非板块资金） ----
    import datetime as _dt
    ladder = hithink(["special", "limit-up-ladder", "--format", "json"])
    pool = None
    tdate = None
    if ladder:
        items = ladder.get("data", {}).get("item", [])
        tdate = items[0].get("date") if items else None
        log(f"ladder tdate={tdate}")
    if tdate:
        y, m, d = (int(x) for x in tdate.split("-"))
        ms = int(_dt.datetime(y, m, d, 0, 0, 0,
                             tzinfo=_dt.timezone(_dt.timedelta(hours=8))).timestamp() * 1000)
        pool = hithink(["special", "limit-up-pool", "--size", "200",
                        "--date-ms", str(ms), "--format", "json"])
    pool_items = (pool or {}).get("data", {}).get("item", [])
    report["sources"]["hithink"] = {
        "ok": bool(pool), "limit_up_count": len(pool_items), "tdate": tdate}

    # ---- 交叉校验1：板块资金流（问财实时 vs 东财缓存） ----
    # 东财缓存为申万口径，问财为同花顺三级行业口径，按「方向一致性」比对
    emx_all = EMX["sector_in"] + EMX["sector_out"]  # (name, yi)
    mq_map = {n: v for n, v in mq_flow}
    # 东财申万口径 -> 问财同花顺行业关键词（模糊对齐）
    ALIAS = {
        "通信设备": ["通信设备", "通信网络设备"],
        "有色金属": ["工业金属", "能源金属", "有色金属"],
        "黄金": ["贵金属", "黄金"],
        "半导体": ["半导体"],
        "医药生物": ["医药", "生物制药", "化学制药"],
        "银行": ["银行"],
    }
    matched = []
    for nm, ev in emx_all:
        kws = ALIAS.get(nm, [nm])
        mv = None
        hit = None
        for kn, kv in mq_map.items():
            if any(k in kn for k in kws):   # 仅正向：问财板块名包含东财关键词
                mv = kv; hit = kn; break
        if mv is not None:
            same_sign = (ev > 0) == (mv > 0)
            matched.append({"eastmoney": nm, "emx_yi": ev,
                            "iwencai": mv, "iwencai_name": hit,
                            "same_sign": same_sign})
        else:
            matched.append({"eastmoney": nm, "emx_yi": ev,
                            "iwencai": None, "iwencai_name": None,
                            "same_sign": None, "note": "问财无对应板块"})
    report["checks"].append({
        "dim": "板块主力资金流（问财实时 vs 东财8-21缓存）",
        "note": "口径不同(申万 vs 同花顺三级行业)，仅比对方向一致性",
        "matched": matched,
        "direction_consistent": all(m["same_sign"] for m in matched) if matched else None,
    })

    # ---- 交叉校验2：问财两源内部一致性（资金流入板块是否也涨幅居前） ----
    top_flow_names = {n for n, v in mq_flow[:8] if v > 0}
    top_chg_names = {n for n, v in sc_chg[:8] if v > 0}
    overlap = top_flow_names & top_chg_names
    report["checks"].append({
        "dim": "问财内部：资金流入 Top vs 涨幅 Top 重叠",
        "flow_top": sorted(top_flow_names),
        "chg_top": sorted(top_chg_names),
        "overlap": sorted(overlap),
        "overlap_count": len(overlap),
    })

    # ---- 交叉校验3：同花顺涨停池 个股能否在问财查到行情（抽样） ----
    sample = [it.get("name") for it in pool_items[:5] if it.get("name")]
    sample_flow = []
    for nm in sample:
        d = iwencai(MK, f"{nm} 最新价 涨跌幅 主力净买入额", limit=1)
        if d and d.get("datas"):
            x = d["datas"][0]
            sample_flow.append({"name": nm, "found": True,
                                 "keys": [k for k in x if "涨" in k or "净买" in k][:3]})
        else:
            sample_flow.append({"name": nm, "found": False})
    report["checks"].append({
        "dim": "个股维度：同花顺涨停池 抽样 vs 问财可查",
        "samples": sample_flow,
    })

    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
    # 人类可读摘要
    sys.stderr.write("\n===== 交叉验证摘要 =====\n")
    for c in report["checks"]:
        sys.stderr.write(f"\n■ {c['dim']}\n")
        if c["dim"].startswith("板块主力资金流"):
            for m in c["matched"]:
                sys.stderr.write(f"   {m['eastmoney']:>8} 东财{m['emx_yi']:>8.2f}亿 | "
                                 f"问财{m['iwencai']:>8.2f}亿 | 方向{'一致' if m['same_sign'] else '冲突'}\n")
            sys.stderr.write(f"   方向一致性: {c['direction_consistent']}\n")
        elif c["dim"].startswith("问财内部"):
            sys.stderr.write(f"   资金Top: {c['flow_top']}\n")
            sys.stderr.write(f"   涨幅Top: {c['chg_top']}\n")
            sys.stderr.write(f"   重叠({c['overlap_count']}): {c['overlap']}\n")
        elif c["dim"].startswith("个股维度"):
            for s in c["samples"]:
                sys.stderr.write(f"   {s['name']}: {'可查' if s['found'] else '未查到'}\n")


if __name__ == "__main__":
    main()
