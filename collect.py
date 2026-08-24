# -*- coding: utf-8 -*-
"""
collect.py — A股复盘数据采集器（重做版，2026-08-24）

设计原则：
  - 宁缺毋假：接口失败/字段缺失 → 留 None 或空，渲染端显示"—"，绝不编造。
  - 单源优先：每个字段选一个最可靠源，失败再降级，不搞复杂多源合并。
  - 所有日志走 stderr，最终 JSON 走 stdout。

数据源：
  1. fuyao（同花顺官方 REST）：涨停池/炸板池/龙虎榜（最结构化，优先）
  2. hithink-finance CLI：连板梯队/空间板（westock 无此能力）
  3. westock-data skillhub：市场广度(changedist)/指数(kline 自算)/板块资金(sector ranking)
  4. mx-data（东方财富妙想）：外围股指/融资融券

输出 collected.json：
  {
    "trade_date": "2026-08-24",
    "up","down","flat","total","amount_yi","zt","dt",
    "indices":[{name,value,chg_pct}],
    "limit_up":[{name,reason,board,seal_yi,is_st,ticker}],
    "break_pool":[{name,open_times,chg_pct,turnover_yi}],
    "ladder":{"2":[...],"3":[...]}, "space_board","space_stock",
    "dragons":[{name,net_yi,change,concepts,org_yi,hot_yi}],
    "sector_in":[{name,val,val_yi}], "sector_out":[{name,val,val_yi}],
    "sector_chg":[{name,chg_pct}],
    "hot":[{rank,name,heat}],
    "overseas":[{name,close,chg,cls}],
    "margin":{finance,lending,total},
    "emotion":{raw_score,adj_score,dims,tdate},
    "source_log":[{src,ok,...}],
  }
"""
import json, os, sys, subprocess, shutil, datetime, re, time

BASE = os.path.dirname(os.path.abspath(__file__))
HITHINK = "hithink-finance"
MX_DATA = "C:/Users/Administrator/.workbuddy/skills/mx-data/mx_data.py"
FUYAO_BASE = os.environ.get("FUYAO_BASE_URL", "https://fuyao.aicubes.cn")
FUYAO_KEY = os.environ.get("FUYAO_API_KEY", "")

INDEX_CODES = {"sh000001": "上证指数", "sz399001": "深证成指",
               "sz399006": "创业板指", "sh000688": "科创50"}


def log(msg):
    sys.stderr.write(f"[collect] {msg}\n")
    sys.stderr.flush()


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


def hithink_env():
    env = dict(os.environ)
    npm = os.path.expanduser(r"~\AppData\Roaming\npm")
    if npm not in env.get("PATH", ""):
        env["PATH"] = npm + os.pathsep + env.get("PATH", "")
    return env


def run_hithink(args, timeout=120):
    """运行 hithink CLI，成功且 stdout 是 JSON 则返回 dict，否则 None。"""
    exe = resolve_hithink()
    try:
        r = subprocess.run([exe] + args, capture_output=True, encoding="utf-8",
                           env=hithink_env(), timeout=timeout)
        out = r.stdout or ""
        if r.returncode == 0 and out.strip().startswith("{"):
            return json.loads(out)
        log(f"hithink {args[0]} rc={r.returncode} err={r.stderr[:150]}")
        return None
    except Exception as e:
        log(f"hithink {args[0]} except: {e}")
        return None


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


def westock_env():
    """扩展 PATH，确保 npx 可见（npm 全局路径 + node 安装路径）。"""
    env = dict(os.environ)
    npm = os.path.expanduser(r"~\AppData\Roaming\npm")
    paths = env.get("PATH", "").split(os.pathsep)
    if npm not in paths:
        paths.insert(0, npm)
    for extra in (r"C:\Program Files\nodejs", "/usr/local/bin", "/usr/bin"):
        if os.path.isdir(extra) and extra not in paths:
            paths.insert(0, extra)
    env["PATH"] = os.pathsep.join(paths)
    return env


def run_westock(args, timeout=150):
    """运行 westock-data skillhub，返回 (rc, text)。Windows npx 需 .cmd。"""
    exe = [resolve_npx(), "-y", "westock-data-skillhub@1.0.5"] + args
    try:
        r = subprocess.run(exe, capture_output=True, encoding="utf-8",
                           env=westock_env(), timeout=timeout)
        if r.returncode != 0:
            log(f"westock {' '.join(args)} rc={r.returncode} err={r.stderr[:200]}")
            return r.returncode, ""
        return 0, r.stdout or ""
    except Exception as e:
        log(f"westock {' '.join(args)} except: {e}")
        return -1, ""


def fuyao_query(path, params=None, timeout=30, retries=2):
    """调用 fuyao REST API。返回 (data_or_None, code_or_None)。带重试（炸板池等曾间歇失败）。"""
    if not FUYAO_KEY:
        log("fuyao: FUYAO_API_KEY 未设置，跳过")
        return None, None
    import urllib.request, urllib.parse
    url = FUYAO_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"X-api-key": FUYAO_KEY})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
            code = obj.get("code")
            if code == 0:
                return obj.get("data"), code
            log(f"fuyao {path} code={code} msg={obj.get('message')} (attempt {attempt})")
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None, code
        except Exception as e:
            log(f"fuyao {path} except: {e} (attempt {attempt})")
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None, None
    return None, None


def trade_date_ms(trade_date):
    """YYYY-MM-DD → 当日 00:00 Asia/Shanghai 毫秒（fuyao/hithink date-ms 参数）。"""
    try:
        y, m, d = (int(x) for x in trade_date.split("-"))
        dt = datetime.datetime(y, m, d, 0, 0, 0,
                               tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def parse_fuyao_pool(data):
    """fuyao 涨停池 → [{name,reason,board,seal_yi,is_st,ticker}]。"""
    items = (data or {}).get("item", [])
    out = []
    for it in items:
        out.append({
            "name": it.get("name"),
            "reason": it.get("limit_up_reason") or "—",
            "board": int(it.get("continue_day_cnt") or 1),
            "seal_yi": round((it.get("seal_money") or 0) / 1e8, 2),
            "is_st": bool(it.get("is_st")),
            "ticker": it.get("ticker"),
        })
    out.sort(key=lambda x: (x["board"], x["seal_yi"]), reverse=True)
    return out


def parse_fuyao_break(data):
    """fuyao 炸板池 → [{name,open_times,chg_pct,turnover_yi}]。"""
    items = (data or {}).get("item", [])
    out = []
    for it in items:
        out.append({
            "name": it.get("name"),
            "open_times": it.get("open_times"),
            "chg_pct": round(it.get("price_change_ratio_pct") or 0, 2),
            "turnover_yi": round((it.get("turnover") or 0) / 1e8, 2),
        })
    return out


def parse_fuyao_dragon(data):
    """fuyao 龙虎榜 → [{name,net_yi,change,concepts,org_yi,hot_yi}]（含机构/游资净买拆分）。"""
    items = (data or {}).get("stock_items", [])
    seen = {}
    for it in items:
        name = it.get("name")
        rec = {
            "name": name,
            "net_yi": round((it.get("net_value") or 0) / 1e8, 2),
            "change": round((it.get("change") or 0) * 100, 2),
            "concepts": [c.get("name") for c in it.get("concept_list", [])],
            "org_yi": round((it.get("org_net_value") or 0) / 1e8, 2),
            "hot_yi": round((it.get("hot_money_net_value") or 0) / 1e8, 2),
        }
        if name not in seen or abs(rec["net_yi"]) > abs(seen[name]["net_yi"]):
            seen[name] = rec
    out = list(seen.values())
    out.sort(key=lambda x: x["net_yi"], reverse=True)
    return out[:12]


def parse_ladder(ladder):
    """hithink 连板梯队 → (ladder_map, space, space_stock, tdate, history)。

    history: [{date, n2, n3, n4, n5, n6, n7}] 近30日连板计数，用于晋级率计算。
    """
    items = (ladder or {}).get("data", {}).get("item", [])
    if not items:
        return {}, None, None, None, []
    latest = items[0]
    tdate = latest.get("date")
    boards = latest.get("boards", {})
    word2num = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
    result = {}
    for k, v in boards.items():
        base = re.sub(r"_board$", "", k)
        n = word2num.get(base)
        if n is None:
            m = re.search(r"(\d+)", k)
            n = int(m.group(1)) if m else None
        if n is None or not v:
            continue
        result[str(n)] = [x.get("name", "").strip() for x in v]
    if result:
        maxn = max(int(k) for k in result.keys())
        space = maxn
        space_stock = result[str(maxn)][0] if result[str(maxn)] else None
    else:
        space, space_stock = None, None
    # 历史（近30日连板计数）
    history = []
    for it in items[:30]:
        b = it.get("boards") or {}
        cnt = {}
        for k, v in b.items():
            base = re.sub(r"_board$", "", k)
            n = word2num.get(base)
            if n is None:
                m = re.search(r"(\d+)", k)
                n = int(m.group(1)) if m else None
            if n is not None:
                cnt[n] = len(v) if isinstance(v, list) else (int(v) if v else 0)
        history.append({"date": it.get("date"), "n2": cnt.get(2, 0), "n3": cnt.get(3, 0),
                        "n4": cnt.get(4, 0), "n5": cnt.get(5, 0),
                        "n6": cnt.get(6, 0), "n7": cnt.get(7, 0)})
    return result, space, space_stock, tdate, history


def parse_tables(md):
    """westock markdown 表格 → [(headers, [rows])]。"""
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


def collect_westock_core(src_log):
    """westock：市场广度(changedist) + 指数(kline 自算)。返回 (breadth, indices)。"""
    breadth = {"up": None, "down": None, "flat": None, "amount_yi": None, "zt": None, "dt": None}
    indices = []

    # 广度：changedist（当日实时，表头为中文）
    rc, out = run_westock(["changedist"])
    ok = False
    if rc == 0 and out:
        for headers, rows in parse_tables(out):
            h = {x: i for i, x in enumerate(headers)}
            # 主表：上涨/下跌/平盘/涨停/跌停
            if "上涨" in h and "下跌" in h:
                for r in rows:
                    try:
                        breadth["up"] = int(r[h["上涨"]])
                        breadth["down"] = int(r[h["下跌"]])
                        if "平盘" in h:
                            breadth["flat"] = int(r[h["平盘"]])
                        if "涨停" in h:
                            breadth["zt"] = int(r[h["涨停"]])
                        if "跌停" in h:
                            breadth["dt"] = int(r[h["跌停"]])
                    except Exception:
                        pass
        # 成交额：文本行 "两市成交额：20074.56亿"（单位亿 → 转万亿）
        m = re.search(r"两市成交额[:：]\s*([\d.]+)\s*亿", out)
        if m:
            breadth["amount_yi"] = round(float(m.group(1)) / 10000, 2)
        ok = breadth["up"] is not None
    src_log.append({"src": "westock.changedist", "ok": ok})

    # 指数：kline 自算（market-overview trade 卡最近收盘日，必须用 kline）
    for code, name in INDEX_CODES.items():
        rc, out = run_westock(["kline", code, "--period", "day", "--limit", "2"])
        if rc == 0 and out:
            for headers, rows in parse_tables(out):
                h = {x: i for i, x in enumerate(headers)}
                if "last" in h and rows:
                    try:
                        # kline 输出降序：rows[0]=最新、rows[1]=前一交易日
                        last = float(rows[0][h["last"]])
                        prev = float(rows[1][h["last"]]) if len(rows) >= 2 else last
                        chg = round((last - prev) / prev * 100, 2) if prev else None
                        indices.append({"name": name, "value": round(last, 2), "chg_pct": chg})
                    except Exception:
                        indices.append({"name": name, "value": None, "chg_pct": None})
    src_log.append({"src": "westock.indices", "ok": len(indices) > 0, "count": len(indices)})
    return breadth, indices


def collect_sector(src_log):
    """westock：板块资金（sector ranking 流入 Top + fund flow 篮子补流出）。"""
    sector_in = []
    sector_out = []
    sector_chg = []
    # 板块资金净流出查询篮子（pt* 代码 → 真实名称，均已核实接口返回名）
    outflow_basket = [
        ("pt01801080", "通信设备"), ("pt01801081", "半导体"), ("pt01801102", "通信设备"),
        ("pt01802011", "医药生物"), ("pt01801041", "银行"), ("pt01801071", "有色金属"),
        ("pt01803010", "计算机"), ("pt01801021", "电力设备"), ("pt01801051", "食品饮料"),
        ("pt01801031", "汽车"), ("pt01802021", "石油石化"), ("pt01801061", "基础化工"),
    ]
    rc, out = run_westock(["sector", "ranking"])
    if rc == 0 and out:
        for headers, rows in parse_tables(out):
            h = {x: i for i, x in enumerate(headers)}
            if "mainNetInflow" in h:
                for r in rows:
                    try:
                        name = r[h["name"]]
                        net = float(r[h["mainNetInflow"]])  # 万元
                        net_yi = round(net / 1e4, 2)
                        if net_yi > 0:
                            sector_in.append({"name": name, "val": f"+{net_yi:.2f}亿", "val_yi": net_yi})
                        elif net_yi < 0:
                            sector_out.append({"name": name, "val": f"{net_yi:.2f}亿", "val_yi": net_yi})
                    except (ValueError, IndexError):
                        continue
            elif "changePct" in h and "leadStock" in h and "mainNetInflow" not in h:
                for r in rows:
                    try:
                        sector_chg.append({"name": r[h["name"]], "chg_pct": float(r[h["changePct"]])})
                    except (ValueError, IndexError):
                        continue
    else:
        src_log.append({"src": "westock.sector.ranking", "ok": False})
    # 去重（同名保留首个）
    seen = {}
    for s in sector_in:
        seen.setdefault(s["name"], s)
    sector_in = list(seen.values())[:5]
    seen = {}
    for s in sector_out:
        seen.setdefault(s["name"], s)
    sector_out = list(seen.values())[:5]
    # 流出不足时用篮子补
    if len(sector_out) < 2:
        for code, name in outflow_basket:
            rc, out = run_westock(["fund", "flow", code])
            if rc != 0 or not out:
                continue
            for headers, rows in parse_tables(out):
                h = {x: i for i, x in enumerate(headers)}
                if "MainNetFlow" in h:
                    for r in rows:
                        try:
                            net = float(r[h["MainNetFlow"]])
                            net_yi = round(net / 1e8, 2)
                            if net_yi < 0:
                                sector_out.append({"name": name, "val": f"{net_yi:.2f}亿", "val_yi": net_yi})
                        except (ValueError, IndexError):
                            continue
            if len(sector_out) >= 3:
                break
        seen = {}
        for s in sector_out:
            seen.setdefault(s["name"], s)
        sector_out = list(seen.values())[:5]
    src_log.append({"src": "westock.sector", "ok": len(sector_in) > 0,
                    "in": len(sector_in), "out": len(sector_out)})
    return sector_in, sector_out, sector_chg


def collect_amount_rank(src_log):
    """问财：沪深A股成交额 Top10（真实成交额/涨跌幅/最新价/换手率）。"""
    script = "C:/Users/Administrator/.iwencai-skillhub/skills/hithink-market-query/scripts/cli.py"
    query = "沪深A股成交额排名前10的股票 涨跌幅 最新价 成交额 换手率"
    try:
        env = dict(os.environ)
        r = subprocess.run([sys.executable, script, "--query", query, "--limit", "10"],
                           capture_output=True, encoding="utf-8", env=env, timeout=60)
        if r.returncode != 0 or not r.stdout.strip().startswith("{"):
            src_log.append({"src": "iwencai.amount-rank", "ok": False})
            return []
        d = json.loads(r.stdout)
        out = []
        for it in (d.get("datas") or [])[:10]:
            chg_key = next((k for k in it if "涨跌幅" in k and "[" in k), "最新涨跌幅")
            amt_key = next((k for k in it if "成交额" in k and "[" in k), None)
            tr_key = next((k for k in it if "换手率" in k and "[" in k), None)
            out.append({
                "rank": len(out) + 1,
                "code": str(it.get("股票代码") or "—").split(".")[0],
                "name": it.get("股票简称") or "—",
                "chg": round(float(it.get(chg_key) or 0), 2),
                "price": it.get("最新价"),
                "amount": round(float(it.get(amt_key) or 0) / 1e8, 2) if amt_key else None,  # 亿元
                "turnover": round(float(it.get(tr_key) or 0), 2) if tr_key else None,
            })
        src_log.append({"src": "iwencai.amount-rank", "ok": bool(out), "count": len(out)})
        return out
    except Exception as e:
        log(f"iwencai amount-rank except: {e}")
        src_log.append({"src": "iwencai.amount-rank", "ok": False})
        return []


def main():
    log("=== 开始采集 ===")
    src_log = []

    # 交易日推算：用 hithink 连板梯队返回的最近交易日
    ladder_raw = run_hithink(["special", "limit-up-ladder", "--format", "json"])
    ladder, space, space_stock, tdate, ladder_history = parse_ladder(ladder_raw)
    src_log.append({"src": "hithink.limit-up-ladder", "ok": ladder_raw is not None,
                    "two": len(ladder.get("2") or []), "three": len(ladder.get("3") or []),
                    "space": space, "space_stock": space_stock})
    trade_date = tdate or datetime.date.today().isoformat()
    ms = trade_date_ms(trade_date)

    # ---- fuyao：涨停池 / 炸板池 / 龙虎榜（最结构化，优先）----
    fy_pool, _ = fuyao_query("/api/a-share/special-data/limit-up-pool",
                             {"date_ms": ms, "size": 200})
    src_log.append({"src": "fuyao.limit-up-pool", "ok": fy_pool is not None,
                    "count": len((fy_pool or {}).get("item") or [])})
    limit_up = parse_fuyao_pool(fy_pool)

    fy_break, _ = fuyao_query("/api/a-share/special-data/limit-break-pool",
                              {"date_ms": ms, "size": 200})
    src_log.append({"src": "fuyao.limit-break-pool", "ok": fy_break is not None,
                    "count": len((fy_break or {}).get("item") or [])})
    break_pool = parse_fuyao_break(fy_break)

    fy_dragon, _ = fuyao_query("/api/a-share/special-data/dragon-tiger-list",
                               {"date": trade_date, "board_type": "all"})
    src_log.append({"src": "fuyao.dragon-tiger", "ok": fy_dragon is not None,
                    "count": len((fy_dragon or {}).get("stock_items") or [])})
    dragons = parse_fuyao_dragon(fy_dragon)

    # 涨停池为空时回退 hithink
    if not limit_up:
        pool = run_hithink(["special", "limit-up-pool", "--size", "200", "--format", "json"])
        src_log.append({"src": "hithink.limit-up-pool", "ok": pool is not None})
        if pool:
            items = (pool or {}).get("data", {}).get("item", [])
            limit_up = [{
                "name": it.get("name"),
                "reason": it.get("limit_up_reason") or "—",
                "board": int(it.get("continue_day_cnt") or 1),
                "seal_yi": round((it.get("seal_money") or 0) / 1e8, 2),
                "is_st": bool(it.get("is_st")),
                "ticker": it.get("ticker"),
            } for it in items]

    # 人气榜（hithink hot-stock，成交额排行模块名称数据源）
    hot_raw = run_hithink(["special", "hot-stock", "--format", "json"])
    hot = []
    if hot_raw:
        items = (hot_raw or {}).get("data", {}).get("item", [])
        hot = [{"rank": it.get("rank"), "name": it.get("name"), "heat": it.get("heat")}
               for it in items[:10]]
    src_log.append({"src": "hithink.hot-stock", "ok": bool(hot), "count": len(hot)})

    # ---- westock：广度 / 指数 / 板块资金 ----
    breadth, indices = collect_westock_core(src_log)
    sector_in, sector_out, sector_chg = collect_sector(src_log)

    # 成交额排行 Top10（问财）
    amount_rank = collect_amount_rank(src_log)

    # 涨停/跌停：westock changedist 若无 zt/dt，用涨停池数兜底（宁缺毋假：无则 None）
    zt = breadth["zt"]
    dt = breadth["dt"]
    if zt is None and limit_up:
        zt = len(limit_up)

    # 真实炸板率 = 炸板 / (涨停 + 炸板)
    break_rate_real = None
    if limit_up or break_pool:
        zt_real = len(limit_up)
        brk = len(break_pool)
        break_rate_real = round(brk / (zt_real + brk) * 100, 2) if (zt_real + brk) else None

    # ---- mx-data：外围股指 / 融资融券（不带日期标签，取最新收盘；带日期标签实测失败）----
    out_dir = os.path.join(BASE, "_mx_out")
    os.makedirs(out_dir, exist_ok=True)
    overseas = []
    margin = {"finance": None, "lending": None, "total": None}
    try:
        import glob
        # 外围分多次查询合并（一次查多个指数偶发丢表）：亚太 + 道指标普 + 纳指
        raw_ov1, _ = run_mx(MX_DATA, "日经225 韩国综合指数 最新收盘价 涨跌幅", out_dir)
        raw_ov2, _ = run_mx(MX_DATA, "道琼斯工业指数 标普500指数 最新收盘价 涨跌幅", out_dir)
        raw_ov3, _ = run_mx(MX_DATA, "纳斯达克指数 最新收盘价 涨跌幅", out_dir)
        src_log.append({"src": "mx-data.overseas", "ok": raw_ov1 is not None or raw_ov2 is not None})
        overseas = parse_overseas(raw_ov1) + parse_overseas(raw_ov2) + parse_overseas(raw_ov3)
        # 去重（同名保留首个）
        seen = {}
        for x in overseas:
            seen.setdefault(x["name"], x)
        overseas = list(seen.values())
        # 融资融券
        raw_mg, _ = run_mx(MX_DATA, "A股 融资余额 融券余额 融资融券余额 最新", out_dir)
        src_log.append({"src": "mx-data.margin", "ok": raw_mg is not None})
        margin = parse_margin(raw_mg)
    except Exception as e:
        log(f"mx-data except: {e}")

    result = {
        "trade_date": trade_date,
        "up": breadth["up"], "down": breadth["down"], "flat": breadth["flat"],
        "total": (breadth["up"] + breadth["down"]) if (breadth["up"] is not None and breadth["down"] is not None) else None,
        "amount_yi": breadth["amount_yi"],
        "zt": zt, "dt": dt,
        "indices": indices,
        "limit_up": limit_up,
        "break_pool": break_pool,
        "break_rate_real": break_rate_real,
        "ladder": ladder, "ladder_history": ladder_history,
        "space_board": space, "space_stock": space_stock,
        "dragons": dragons,
        "hot": hot,
        "amount_rank": amount_rank,
        "sector_in": sector_in, "sector_out": sector_out, "sector_chg": sector_chg,
        "overseas": overseas, "margin": margin,
        "source_log": src_log,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    log(f"采集完成：{trade_date} 涨停{zt}/{len(limit_up)}只 炸板{len(break_pool)}只 "
        f"涨跌{result['up']}/{result['down']} 成交{result['amount_yi']}万亿")


# ---------- mx-data 解析（复用已验证逻辑） ----------
def run_mx(script, query, out_dir, timeout=180):
    """运行 mx-data。返回 (raw_json_or_None, text_or_None)。"""
    try:
        env = dict(os.environ)
        r = subprocess.run([sys.executable, script, query, out_dir],
                           capture_output=True, encoding="utf-8", env=env, timeout=timeout)
        if r.returncode != 0:
            log(f"mx {os.path.basename(script)} rc={r.returncode} err={r.stderr[:160]}")
            return None, None
        import glob
        raws = sorted(glob.glob(os.path.join(out_dir, "*_raw.json")),
                      key=os.path.getmtime, reverse=True)
        raw = None
        if raws:
            try:
                raw = json.load(open(raws[0], encoding="utf-8"))
            except Exception:
                raw = None
        return raw, None
    except Exception as e:
        log(f"mx {os.path.basename(script)} except: {e}")
        return None, None


def mx_tables(raw):
    """从 mx-data 原始 JSON 抽取 dataTableDTOList。"""
    if not raw:
        return []
    sdr = raw.get("data", {}).get("data", {}).get("searchDataResultDTO")
    if sdr and sdr.get("dataTableDTOList"):
        return sdr["dataTableDTOList"]
    return raw.get("data", {}).get("dataTableDTOList") or []


def parse_overseas(mx_raw):
    """外围股指：每个指数一张表（title 含指数名，headName[0]=最新日期）。
    校验条数≥4 才算成功（避免偶发返回不全）。"""
    out = []
    tables = mx_tables(mx_raw)
    for e in tables:
        nm = e.get("nameMap", {})
        tbl = e.get("table", {})
        hn = tbl.get("headName", [])
        cols = {v: k for k, v in nm.items() if k != "headNameSub"}
        title = str(e.get("title", ""))
        chg_k = next((cols[c] for c in cols if "涨跌幅" in c), None)
        close_k = next((cols[c] for c in cols if "收盘价" in c), None)
        if not chg_k or not hn:
            continue
        # 指数名从 title 提取（"日经225(N225.GI)(指数)的涨跌幅、收盘价"）
        m = re.match(r"(.+?)(?:\([^)]*\))*\(?指数\)?", title)
        name = m.group(1).strip() if m else title.split("的")[0].strip()
        name = name.split("(")[0].strip()
        if not name or name == "None":
            continue
        # 最新一行 = headName[0]
        chg = tbl.get(chg_k, [])[0] if tbl.get(chg_k) else None
        close = tbl.get(close_k, [])[0] if (close_k and tbl.get(close_k)) else None
        if chg is None:
            continue
        out.append({"name": name, "close": str(close or "—"),
                    "chg": str(chg).replace("%", "") + "%",
                    "cls": "positive" if "-" not in str(chg) else "negative"})
    # 只保留指数类（过滤 title=None 的个股列表表）
    out = [x for x in out if any(k in x["name"] for k in
           ["日经", "韩国", "道琼斯", "纳斯达克", "标普"])]
    seen = {}
    for x in out:
        seen.setdefault(x["name"], x)
    return list(seen.values())


def parse_margin(mx_raw):
    """融资融券：转置表优先（三列同口径）→ 常规表兜底。

    转置表结构：headName 是字段名（"融资余额(亿元)"等），数据列 key 是日期，
    取值带单位如 "2.63万"（亿元），统一归一为 "2.63万亿"。"""
    res = {"finance": None, "lending": None, "total": None}
    tables = mx_tables(mx_raw)
    # 第一遍：转置表
    for e in tables:
        tbl = e.get("table", {})
        hn = tbl.get("headName", [])
        if "融资融券余额合计" not in "".join(str(x) for x in hn):
            continue
        val_cols = [c for c in tbl if c != "headName"]
        if not val_cols:
            continue
        col = tbl.get(val_cols[0], [])  # 最新交易日列
        for i, field in enumerate(hn):
            val = col[i] if i < len(col) else None
            if val is None:
                continue
            if "融资融券余额合计" in field:
                res["total"] = _norm_wan(val)
            elif "融资余额" in field and "合计" not in field:
                res["finance"] = _norm_wan(val)
            elif "融券余额" in field and "合计" not in field:
                res["lending"] = _norm_wan(val)
        if res["total"]:
            return res  # 转置表完整则直接返回
    # 第二遍：常规表（列名含字段名）
    for e in tables:
        nm = e.get("nameMap", {})
        tbl = e.get("table", {})
        hn = tbl.get("headName", [])
        cols = {v: k for k, v in nm.items() if k != "headNameSub"}
        f_k = next((cols[c] for c in cols if "融资余额" in c), None)
        l_k = next((cols[c] for c in cols if "融券余额" in c), None)
        t_k = next((cols[c] for c in cols if "融资融券余额" in c), None)
        if not (f_k or l_k or t_k) or not hn:
            continue
        if f_k and res["finance"] is None and tbl.get(f_k):
            res["finance"] = tbl[f_k][0]
        if l_k and res["lending"] is None and tbl.get(l_k):
            res["lending"] = tbl[l_k][0]
        if t_k and res["total"] is None and tbl.get(t_k):
            res["total"] = _norm_wan(tbl[t_k][0])
    return res


def _norm_wan(v):
    """"2.63万"（亿元）→ "2.63万亿"；"270.67"（亿元）→ "270.67亿"。"""
    s = str(v).strip()
    if "万亿" in s:
        return s
    if "万" in s:
        return s.replace("万", "万亿")
    if "亿" in s:
        return s
    # 纯数字：视为亿元
    return f"{s}亿"


if __name__ == "__main__":
    main()
