# -*- coding: utf-8 -*-
"""
collect_westock.py — A股复盘采集器（优先用 WeStock Data / 腾讯自选股）

数据源优先级：
  1. WeStock Data（westock-data skillhub，腾讯自选股）
     - changedist            : 市场广度（上涨/下跌/涨停/跌停家数 + 成交额）
     - market-overview trade : 三大指数（上证/深成/创业板）收盘涨跌幅+点位
     - kline sh000688        : 科创50 点位涨跌（补齐第四指数）
     - sector ranking        : 行业/概念涨幅榜 + 行业资金流入 Top5
     - fund flow pt*         : 板块主力净流出（补足净流出方向）
     - lhb                   : 龙虎榜（机构榜/游资榜）
     - market-overview summary : 市场情绪 14 维评分（喂情绪周期研判）
  2. 同花顺 hithink-finance（仅连板梯队/空间板专长）
     - special limit-up-ladder : 2板/3板/空间板（WeStock 无此能力，回退 hithink）

说明：
  - 所有日志走 stderr；最终 JSON 走 stdout（供 update.py 管道消费）。
  - 不编造数据：某源失败则该字段留 None，由 update.py 决定占位/回退。
  - 非交易时段 westockdata 自动返回最近交易日快照（后端控制）。

输出 flat JSON（兼容 collect.py schema）：
  trade_date, up, down, flat, total, amount_yi, zt, dt,
  indices[{name,value,chg_pct}], ladder{2:[],3:[]}, space_board, space_stock,
  hot[], dragons[{name,net_yi,change,concepts}], limit_up[], break_pool[],
  break_rate_real, sector_in[{name,val,val_yi}], sector_out[{name,val,val_yi}],
  sector_chg[], plate_leaders[], breadth_history[], overseas[], margin[],
  emotion(市场情绪14维), source_log[]
"""
import json, os, sys, subprocess, shutil, datetime, re

WESTOCK = "westock-data"
HITHINK = "hithink-finance"

# 第四指数代码
KCB_CODE = "sh000688"

# 板块资金净流出查询篮子（用 fund flow pt* 补足净流出方向）
SECTOR_OUTFLOW_BASKET = [
    ("pt01801080", "通信设备"), ("pt01801081", "半导体"), ("pt01801102", "通信设备二级"),
    ("pt01802011", "医药生物"), ("pt01801041", "银行"), ("pt01801071", "有色金属"),
    ("pt01803010", "计算机"), ("pt01801021", "电力设备"), ("pt01801051", "食品饮料"),
    ("pt01801031", "汽车"), ("pt01802021", "石油石化"), ("pt01801061", "基础化工"),
]


def log(msg):
    sys.stderr.write(f"[westock] {msg}\n")
    sys.stderr.flush()


def westock_env():
    """扩展 PATH，确保 npx 可见（npm 全局路径）。"""
    env = dict(os.environ)
    npm = os.path.expanduser(r"~\AppData\Roaming\npm")
    paths = env.get("PATH", "").split(os.pathsep)
    if npm not in paths:
        paths.insert(0, npm)
    # 常见 node 安装路径
    for extra in (r"C:\Program Files\nodejs", "/usr/local/bin", "/usr/bin"):
        if os.path.isdir(extra) and extra not in paths:
            paths.insert(0, extra)
    env["PATH"] = os.pathsep.join(paths)
    return env


def resolve_npx():
    """定位 npx 可执行文件（Windows 上需带 .cmd 后缀）。"""
    for ext in (".cmd", ".ps1", ""):
        p = shutil.which("npx" + ext)
        if p:
            return p
    npm = os.path.expanduser(r"~\AppData\Roaming\npm")
    for ext in (".cmd", ""):
        cand = os.path.join(npm, "npx" + ext)
        if os.path.isfile(cand):
            return cand
    return "npx"


def run(cmd_args, timeout=150):
    """运行 westock-data skillhub 命令，返回 (rc, text)。"""
    exe = [resolve_npx(), "-y", "westock-data-skillhub@1.0.5"] + cmd_args
    try:
        r = subprocess.run(exe, capture_output=True, encoding="utf-8",
                           timeout=timeout, env=westock_env())
        if r.returncode != 0:
            log(f"westock {' '.join(cmd_args)} rc={r.returncode} err={r.stderr[:200]}")
            return r.returncode, ""
        return 0, r.stdout or ""
    except Exception as e:
        log(f"westock {' '.join(cmd_args)} except: {e}")
        return -1, ""


# ---------- 通用 markdown 表格解析 ----------
def parse_tables(md):
    """返回 list of (headers, [rows])，每行是字段列表。"""
    tables = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            headers = [c.strip() for c in line.strip("|").split("|")]
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip("|").split("|")]
                if len(cells) == len(headers):
                    rows.append(cells)
                j += 1
            tables.append((headers, rows))
            i = j
        else:
            i += 1
    return tables


def resolve_hithink():
    for ext in ("", ".cmd", ".ps1", ".bat"):
        p = shutil.which(HITHINK + ext)
        if p:
            return p
    npm = os.path.expanduser(r"~\AppData\Roaming\npm")
    if os.path.isdir(npm):
        for ext in ("", ".cmd"):
            cand = os.path.join(npm, HITHINK + ext)
            if os.path.isfile(cand):
                return cand
    return HITHINK


def run_hithink(args, timeout=90):
    exe = resolve_hithink()
    try:
        r = subprocess.run([exe] + args, capture_output=True, encoding="utf-8", timeout=timeout)
        if r.returncode == 0 and (r.stdout or "").strip().startswith("{"):
            return json.loads(r.stdout)
        log(f"hithink {args[0]} rc={r.returncode} err={r.stderr[:120]}")
        return None
    except Exception as e:
        log(f"hithink {args[0]} except: {e}")
        return None


# ---------- 各维度采集 ----------
def collect_breadth(src_log):
    """市场广度：up/down/zt/dt/amount + breadth_history(单点)。"""
    rc, out = run(["changedist"])
    if rc != 0 or not out:
        src_log.append({"src": "westock.changedist", "ok": False, "note": "无输出"})
        return None, None, None, None, None, [], None, None
    tables = parse_tables(out)
    up = down = flat = zt = dt = None
    amount = None
    history = []
    for headers, rows in tables:
        if "上涨" in headers and "下跌" in headers:
            # 找 上涨/下跌/平盘/涨停/跌停 行
            name_idx = headers.index("上涨") if "上涨" in headers else 0
            # changedist 首表是横向：指标行
            # 实际格式：| 上涨 | 下跌 | 平盘 | 涨停 | 跌停 | 停牌 | 上涨占比 |
            try:
                up = int(rows[0][0]) if rows else None
                down = int(rows[0][1]) if rows else None
                flat = int(rows[0][2]) if (rows and len(rows[0]) > 2) else None
                zt = int(rows[0][3]) if (rows and len(rows[0]) > 3) else None
                dt = int(rows[0][4]) if (rows and len(rows[0]) > 4) else None
            except (ValueError, IndexError):
                pass
        if "两市成交额" in headers:
            # | 两市成交额 | 数值 |
            for r in rows:
                if "两市成交额" in r[0] and "较上日" not in r[0]:
                    m = re.search(r"([\d.]+)\s*亿", r[1])
                    if m:
                        amount = round(float(m.group(1)) / 10000.0, 4)  # 亿 -> 万亿
    # 成交额也可能以加粗文本形式出现： **两市成交额：18792.64亿**
    if amount is None:
        m = re.search(r"两市成交额[：:]\s*([\d.]+)\s*亿", out)
        if m:
            amount = round(float(m.group(1)) / 10000.0, 4)
    # 提取数据日期：从其它文本 "数据日期 `2026-08-21`"
    m = re.search(r"数据日期\s*`?(\d{4}-\d{2}-\d{2})`?", out)
    tdate = m.group(1) if m else None
    if up is not None and down is not None:
        history.append({"date": tdate or "", "up": up, "down": down,
                        "amount": (f"{amount}万亿" if amount else "")})
    src_log.append({"src": "westock.changedist", "ok": up is not None,
                    "up": up, "down": down, "zt": zt, "dt": dt, "amount_yi": amount})
    return up, down, flat, zt, dt, history, tdate, amount


def collect_indices(src_log):
    """三大指数 + 科创50，返回 (indices 列表, 数据日期)。"""
    indices = []
    tdate = None
    # 统一用 kline 实时算（market-overview trade 后端数据日期滞后，不实时）
    idx_codes = [("上证指数", "sh000001"), ("深证成指", "sz399001"),
                 ("创业板指", "sz399006"), ("科创50", KCB_CODE)]
    for name, code in idx_codes:
        rc2, out2 = run(["kline", code, "--period", "day", "--limit", "2"])
        if rc2 == 0 and out2:
            tables = parse_tables(out2)
            for headers, rows in tables:
                if "last" in headers and "date" in headers:
                    try:
                        l_i = headers.index("last")
                        d_i = headers.index("date")
                        if len(rows) >= 2:
                            v0 = float(rows[0][l_i])
                            v1 = float(rows[1][l_i])
                            chg_f = round((v0 - v1) / v1 * 100, 2)
                            tdate = rows[0][d_i]  # 当日行日期
                            indices.append({
                                "name": name,
                                "value": rows[0][l_i],
                                "chg_pct": (f"+{chg_f:.2f}%" if chg_f >= 0
                                            else f"{chg_f:.2f}%"),
                            })
                    except (ValueError, IndexError):
                        pass
        else:
            src_log.append({"src": f"westock.kline.{code}", "ok": False})
    src_log.append({"src": "westock.indices", "ok": len(indices) > 0, "count": len(indices)})
    return indices, tdate


def collect_sector(src_log):
    """板块资金：流入用 sector ranking 行业资金 Top5；流出用 fund flow pt* 篮子补足。"""
    sector_in = []
    sector_out = []
    sector_chg = []
    plate_leaders = []
    # 1) sector ranking（行业资金流入 Top5 + 行业/概念涨幅排名，当日实时）
    rc, out = run(["sector", "ranking"])
    if rc == 0 and out:
        tables = parse_tables(out)
        for headers, rows in tables:
            h = {x: i for i, x in enumerate(headers)}
            if "mainNetInflow" in h:
                # 行业资金流入 Top（带 mainNetInflow）
                for r in rows:
                    try:
                        name = r[h["name"]]
                        chg = float(r[h["changePct"]]) if "changePct" in h else None
                        net = float(r[h["mainNetInflow"]])  # 单位：万元
                        net_yi = round(net / 1e4, 2)
                        if net_yi > 0:
                            sector_in.append({"name": name, "val": f"+{net_yi:.2f}亿",
                                              "val_yi": net_yi})
                        elif net_yi < 0:
                            sector_out.append({"name": name, "val": f"{net_yi:.2f}亿",
                                               "val_yi": net_yi})
                    except (ValueError, IndexError):
                        continue
            elif "changePct" in h and "leadStock" in h and "mainNetInflow" not in h:
                # 行业/概念涨幅榜（无资金列）
                for r in rows:
                    try:
                        name = r[h["name"]]
                        chg = float(r[h["changePct"]])
                        lead = r[h["leadStock"]] if "leadStock" in h else ""
                        sector_chg.append({"name": name, "chg_pct": chg})
                        if lead:
                            lm = re.match(r"([^\(\n]+)\(([\d.]+)\)", lead)
                            lname = lm.group(1).strip() if lm else lead
                            lpct = float(lm.group(2)) if lm else None
                            plate_leaders.append({"plate": name, "name": lname,
                                                  "chg_pct": lpct})
                    except (ValueError, IndexError):
                        continue
    else:
        src_log.append({"src": "westock.sector.ranking", "ok": False})

    # 2) 净流出补足：fund flow pt*（仅当 sector_out 不足时用）
    if len(sector_out) < 2:
        for code, name in SECTOR_OUTFLOW_BASKET:
            rc, out = run(["fund", "flow", code])
            if rc != 0 or not out:
                continue
            tables = parse_tables(out)
            for headers, rows in tables:
                h = {x: i for i, x in enumerate(headers)}
                if "MainNetFlow" in h:
                    for r in rows:
                        try:
                            net = float(r[h["MainNetFlow"]])
                            net_yi = round(net / 1e8, 2)
                            if net_yi < 0:
                                sector_out.append({"name": name, "val": f"{net_yi:.2f}亿",
                                                  "val_yi": net_yi})
                        except (ValueError, IndexError):
                            continue
            if len(sector_out) >= 3:
                break
        # 去重（同名保留首个）
        seen = {}
        for s in sector_out:
            seen.setdefault(s["name"], s)
        sector_out = list(seen.values())[:5]

    # sector_in 去重
    seen = {}
    for s in sector_in:
        seen.setdefault(s["name"], s)
    sector_in = list(seen.values())[:5]

    src_log.append({"src": "westock.sector", "ok": True,
                    "in": len(sector_in), "out": len(sector_out),
                    "chg": len(sector_chg), "leaders": len(plate_leaders)})
    return sector_in, sector_out, sector_chg, plate_leaders


def _kline_chg(code):
    """用 kline 近2日 last 自算个股涨跌幅（百分比浮点，失败返回 None）。"""
    if not code:
        return None
    rc, out = run(["kline", code, "--period", "day", "--limit", "2"])
    if rc != 0 or not out:
        return None
    for headers, rows in parse_tables(out):
        if "last" in headers and len(rows) >= 2:
            try:
                li = headers.index("last")
                v0 = float(rows[0][li])
                v1 = float(rows[1][li])
                return round((v0 - v1) / v1 * 100, 2)
            except (ValueError, IndexError):
                return None
    return None


def _parse_lhb_block(block, dtype):
    """解析单个龙虎榜区块（机构榜/游资榜）的表格，返回 dragon 列表。"""
    out_list = []
    tables = parse_tables(block)
    for headers, rows in tables:
        h = {x: i for i, x in enumerate(headers)}
        if "净买入额" in h and "名称" in h:
            for r in rows:
                try:
                    name = r[h["名称"]]
                    code = r[h["代码"]] if "代码" in h else None
                    net_raw = r[h.get("净买入额", 0)]
                    m = re.search(r"(-?[\d.]+)\s*亿", net_raw)
                    net_yi = float(m.group(1)) if m else None
                    d = {"name": name, "code": code, "net_yi": net_yi, "change": None,
                         "concepts": [], "type": dtype}
                    if dtype == "org":
                        d["org_yi"] = net_yi
                        d["hot_yi"] = None
                    else:
                        d["hot_yi"] = net_yi
                        d["org_yi"] = None
                    out_list.append(d)
                except (ValueError, IndexError):
                    continue
    return out_list


def collect_dragons(src_log):
    """龙虎榜：组合查询机构榜+游资榜，按 markdown 标题归属类型，标注 org_yi/hot_yi。"""
    dragons = []
    rc, out = run(["lhb", "--type", "institution,hotmoney"])
    if rc != 0 or not out:
        src_log.append({"src": "westock.lhb", "ok": False})
        return dragons
    # 按 **机构榜** / **游资榜** 标题切分区块
    dtype = "org"
    blocks = []
    cur = []
    for line in out.splitlines():
        m = re.match(r"\*\*([^*]+)\*\*\s*\(?\d*只?\)?", line.strip())
        if m and ("机构" in m.group(1) or "游资" in m.group(1)):
            if cur:
                blocks.append((dtype, "\n".join(cur)))
            dtype = "org" if "机构" in m.group(1) else "hot"
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append((dtype, "\n".join(cur)))
    if not blocks:
        blocks = [("org", out)]
    for dt, blk in blocks:
        dragons += _parse_lhb_block(blk, dt)
    if not dragons:
        src_log.append({"src": "westock.lhb", "ok": False})
        return dragons
    # 合并同名：机构榜与游资榜可能含同一只，合并 org_yi/hot_yi/net_yi
    merged = {}
    for d in dragons:
        nm = d["name"]
        if nm not in merged:
            merged[nm] = {"name": nm, "code": None, "net_yi": None, "change": None,
                          "concepts": [], "org_yi": None, "hot_yi": None, "type": "both",
                          "chg_pct": None}
        m = merged[nm]
        if d.get("code") and not m["code"]:
            m["code"] = d["code"]
        if d["org_yi"] is not None:
            m["org_yi"] = d["org_yi"]
        if d["hot_yi"] is not None:
            m["hot_yi"] = d["hot_yi"]
        if d["net_yi"] is not None:
            m["net_yi"] = d["net_yi"]
    dragons = list(merged.values())
    # 用 kline 补个股涨跌幅（westock 机构榜不返回 chg_pct）
    filled = 0
    for d in dragons:
        if d.get("code"):
            chg = _kline_chg(d["code"])
            if chg is not None:
                d["change"] = chg
                d["chg_pct"] = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
                filled += 1
    src_log.append({"src": "westock.lhb", "ok": True, "count": len(dragons),
                    "chg_filled": filled})
    return dragons


def collect_emotion(src_log):
    """市场情绪 14 维评分（market-overview summary，数据日期可能滞后）。"""
    rc, out = run(["market-overview", "--type", "summary"])
    if rc != 0 or not out:
        src_log.append({"src": "westock.market-overview.summary", "ok": False})
        return None
    emotion = {"raw_score": None, "adj_score": None, "dims": [], "tdate": None}
    # 数据日期（后端实际数据日期，可能滞后于请求日）
    dm = re.search(r"数据日期\s*`?(\d{4}-\d{2}-\d{2})`?", out)
    if dm:
        emotion["tdate"] = dm.group(1)
    # 总评
    m = re.search(r"原始评分\s*\*\*\s*([\d.]+)\s*\*\*\s*/\s*调整评分\s*\*\*\s*([\d.]+)\s*\*\*", out)
    if m:
        emotion["raw_score"] = float(m.group(1))
        emotion["adj_score"] = float(m.group(2))
    # 维度表
    tables = parse_tables(out)
    for headers, rows in tables:
        if "维度" in headers and "得分" in headers:
            di = headers.index("维度")
            si = headers.index("得分")
            sti = headers.index("状态") if "状态" in headers else None
            for r in rows:
                emotion["dims"].append({
                    "dim": r[di],
                    "score": r[si],
                    "status": r[sti] if sti is not None else "",
                })
    src_log.append({"src": "westock.emotion", "ok": len(emotion["dims"]) > 0,
                    "raw": emotion["raw_score"], "adj": emotion["adj_score"],
                    "tdate": emotion["tdate"]})
    return emotion


def collect_ladder(src_log):
    """连板梯队 + 空间板：回退 hithink（westock 无此能力）。"""
    data = run_hithink(["special", "limit-up-ladder"])
    if not data or not data.get("ok"):
        src_log.append({"src": "hithink.limit-up-ladder", "ok": False})
        return {}, None, None
    try:
        item = data["data"]["item"][0]
        boards = item["boards"]
        two = [b["name"].strip() for b in boards.get("two_board", [])]
        three = [b["name"].strip() for b in boards.get("three_board", [])]
        # 空间板：最高 board_num
        space = None
        space_stock = None
        for key in ("seven_over", "six_board", "five_board", "four_board",
                    "three_board", "two_board"):
            lst = boards.get(key, [])
            if lst:
                # 取列表中第一个作为空间板代表
                space = lst[0]["board_num"]
                space_stock = lst[0]["name"].strip()
                break
        ladder = {"2": two, "3": three}
        src_log.append({"src": "hithink.limit-up-ladder", "ok": True,
                        "two": len(two), "three": len(three),
                        "space": space, "space_stock": space_stock})
        return ladder, space, space_stock
    except (KeyError, IndexError, TypeError) as e:
        src_log.append({"src": "hithink.limit-up-ladder", "ok": False, "err": str(e)})
        return {}, None, None


def main():
    src_log = []
    up = down = flat = zt = dt = None
    history = []
    tdate = None
    amount = None
    # 广度
    res = collect_breadth(src_log)
    if res:
        up, down, flat, zt, dt, history, tdate, amount = res
    # 指数（含数据日期）
    indices, tdate_idx = collect_indices(src_log)
    if not tdate and tdate_idx:
        tdate = tdate_idx
    # 板块
    sector_in, sector_out, sector_chg, plate_leaders = collect_sector(src_log)
    # 龙虎榜
    dragons = collect_dragons(src_log)
    # 情绪
    emotion = collect_emotion(src_log)
    # 连板梯队
    ladder, space, space_stock = collect_ladder(src_log)

    result = {
        "trade_date": tdate,
        "up": up, "down": down, "flat": flat,
        "total": (up + down if (up and down) else None),
        "amount_yi": amount,
        "zt": zt, "dt": dt,
        "indices": indices,
        "ladder": ladder,
        "space_board": space,
        "space_stock": space_stock,
        "hot": [],
        "dragons": dragons,
        "limit_up": [],
        "break_pool": [],
        "break_rate_real": None,
        "fuyao_source": {"limit_up_count": None, "break_count": None, "dragon_count": len(dragons)},
        "sector_in": sector_in,
        "sector_out": sector_out,
        "sector_chg": sector_chg,
        "plate_leaders": plate_leaders,
        "breadth_history": history,
        "overseas": [],
        "margin": [],
        "emotion": emotion,
        "cross_check": {"ok": False, "note": "westock 单源，跳过交叉校验", "dimensions": []},
        "source_log": src_log,
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
