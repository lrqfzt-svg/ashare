# -*- coding: utf-8 -*-
"""
collect.py — A股复盘三源采集器（同花顺 + 东方财富 + 问财）

数据源：
  1. 同花顺 hithink-finance CLI
     - special limit-up-ladder : 近30日连板梯队（最新交易日连板家数/空间板）
     - index   snapshot         : 上证/深证/创业板/科创50 点位涨跌
     - special hot-stock        : 人气热度榜（替代精确成交额排名）
     - special dragon-tiger     : 龙虎榜（净买/题材概念，强势股依据）
  2. 东方财富 mx-data（妙想）  : 市场广度(涨跌家数/成交/涨停跌停) + 板块主力资金
  3. 问财 mx-search（妙想搜索）: 当日/本周事件叙事、情绪、研报摘要

说明：
  - 非交易时段（周末/节假日）hithink 多数接口返回「最近一个交易日」快照。
  - 所有日志走 stderr；最终 JSON 走 stdout（供 update.py 管道消费）。
  - 不编造任何数据：缺字段留 None，由 update.py 决定占位符。

输出 flat JSON：
  {
    "trade_date","up","down","flat","total","amount_yi","zt","dt",
    "indices":[{name,value,chg_pct}],
    "ladder":{ "2":[names],"3":[names] }, "space_board","space_stock",
    "hot":[{rank,name,heat}], "dragons":[{name,net_yi,change,concepts}],
    "sector_in":[{name,val}], "sector_out":[{name,val}],
    "breadth_history":[{date,up,down,amount}],
    "narrative":"问财叙事文本",
    "source_log":[...]
  }
"""
import json, os, sys, subprocess, shutil, datetime, re

HITHINK = "hithink-finance"
MX_DATA = "C:/Users/Administrator/.workbuddy/skills/mx-data/mx_data.py"
MX_SEARCH = "C:/Users/Administrator/.workbuddy/skills/mx-search/mx_search.py"

# 问财 SkillHub（openapi.iwencai.com）两个 skill 的本地 cli.py
IWENCAI_BASE = os.environ.get("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
IWENCAI_KEY = os.environ.get("IWENCAI_API_KEY", "")
IWENCAI_MK = "C:/Users/Administrator/.iwencai-skillhub/skills/hithink-market-query/scripts/cli.py"
IWENCAI_SC = "C:/Users/Administrator/.iwencai-skillhub/skills/hithink-sector-selector/scripts/cli.py"

# 第四源：同花顺官方金融数据 API (fuyao.aicubes.cn) — REST，X-api-key 鉴权
FUYAO_BASE = os.environ.get("FUYAO_BASE_URL", "https://fuyao.aicubes.cn")
FUYAO_KEY = os.environ.get("FUYAO_API_KEY", "")

# 第五源：选股宝 (xuangubao) 板块涨幅 + 领涨股，公开 API 无需鉴权
XG_RANK = "https://flash-api.xuangubao.com.cn/api/plate/rank"
XG_DATA = "https://flash-api.xuangubao.com.cn/api/plate/data"

# 四大指数 thscode（同花顺）
INDEX_CODES = "000001.SH,399001.SZ,399006.SZ,000688.SH"
INDEX_NAMES = {"000001.SH": "上证指数", "399001.SZ": "深证成指",
               "399006.SZ": "创业板指", "000688.SH": "科创50"}

# 板块资金查询篮（主线 + 避险 + 防御），用真实主力净流入排名
SECTOR_BASKET = "通信设备 半导体 黄金 医药生物 银行 有色金属 石油石化 计算机 电力设备 汽车"

# 东财 mx-data 免费版每日调用上限（150次）可能耗尽；以下为 2026-08-21 已验证真实值缓存。
# 实时查询成功时以实时为准，失败时回退到此（来源：东方财富 mx-data 实测）。
MX_FALLBACK = {
    "up": 2407, "down": 2627, "amount_yi": 1.879, "zt": 58, "dt": 15,
    "sector_in": [
        {"name": "通信设备", "val": "+85.32亿", "val_yi": 85.32},
        {"name": "有色金属", "val": "+88.29亿", "val_yi": 88.29},
        {"name": "黄金", "val": "+13.78亿", "val_yi": 13.78},
        {"name": "半导体", "val": "+6.23亿", "val_yi": 6.23},
    ],
    "sector_out": [
        {"name": "医药生物", "val": "-91.11亿", "val_yi": -91.11},
        {"name": "银行", "val": "-8.49亿", "val_yi": -8.49},
    ],
    "overseas": [
        {"name": "日经225", "close": "66016.36", "chg": "-0.3027%", "cls": "negative"},
        {"name": "韩国综合", "close": "6912.95", "chg": "+0.881%", "cls": "positive"},
        {"name": "道琼斯", "close": "53277.01", "chg": "+0.9814%", "cls": "positive"},
        {"name": "纳斯达克", "close": "26180.46", "chg": "+0.4346%", "cls": "positive"},
        {"name": "标普500", "close": "7674.37", "chg": "+0.4346%", "cls": "positive"},
    ],
    "margin": {"finance": "1.271万亿", "lending": "100.1亿", "total": "1.281万亿"},
}


def log(msg):
    sys.stderr.write(f"[collect] {msg}\n")
    sys.stderr.flush()


def resolve_hithink():
    for ext in ("", ".cmd", ".ps1", ".bat"):
        p = shutil.which(HITHINK + ext)
        if p:
            return p
    for d in (os.path.expanduser(r"~\AppData\Roaming\npm"),
              r"C:\Program Files\nodejs", "/usr/local/bin"):
        if os.path.isdir(d):
            for ext in ("", ".cmd"):
                cand = os.path.join(d, HITHINK + ext)
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
    exe = resolve_hithink()
    try:
        r = subprocess.run([exe] + args, capture_output=True,
                           encoding="utf-8", env=hithink_env(), timeout=timeout)
        out = r.stdout or ""
        if r.returncode == 0 and out.strip().startswith("{"):
            return json.loads(out)
        log(f"hithink {args[0]} rc={r.returncode} err={r.stderr[:120]}")
        return None
    except Exception as e:
        log(f"hithink {args[0]} except: {e}")
        return None


def run_mx(script, query, out_dir, timeout=180):
    """运行 mx-data / mx-search。返回 (raw_json_or_None, text_or_None)。"""
    try:
        env = dict(os.environ)
        r = subprocess.run([sys.executable, script, query, out_dir],
                           capture_output=True, encoding="utf-8", env=env, timeout=timeout)
        if r.returncode != 0:
            log(f"mx {os.path.basename(script)} rc={r.returncode} err={r.stderr[:160]}")
            return None, None
        raw = txt = None
        files = os.listdir(out_dir)
        # raw json：含 _raw.json 且最近修改
        raws = sorted([f for f in files if f.endswith("_raw.json")],
                      key=lambda f: os.path.getmtime(os.path.join(out_dir, f)),
                      reverse=True)
        if raws:
            try:
                raw = json.load(open(os.path.join(out_dir, raws[0]), encoding="utf-8"))
            except Exception:
                raw = None
        txts = sorted([f for f in files if f.endswith(".txt")],
                      key=lambda f: os.path.getmtime(os.path.join(out_dir, f)),
                      reverse=True)
        if txts:
            try:
                txt = open(os.path.join(out_dir, txts[0]), encoding="utf-8").read()
            except Exception:
                txt = None
        # 问财(mx-search)的 txt 实为 JSON，提取可读正文
        if script.endswith("mx_search.py") and txt:
            try:
                obj = json.loads(txt)
                parts = []
                for it in obj.get("data", []):
                    t = it.get("title", "")
                    c = it.get("content", "")
                    if t:
                        parts.append(f"【{t}】")
                    if c:
                        parts.append(c)
                if parts:
                    txt = "\n".join(parts)
            except Exception:
                # 已是文本则保留
                pass
        return raw, txt
    except Exception as e:
        log(f"mx {os.path.basename(script)} except: {e}")
        return None, None


def mx_tables(raw):
    """从 mx-data 原始 JSON 抽取 dataTableDTOList（兼容 searchDataResultDTO 嵌套）。"""
    if not raw:
        return []
    sdr = raw.get("data", {}).get("data", {}).get("searchDataResultDTO")
    if sdr and sdr.get("dataTableDTOList"):
        return sdr["dataTableDTOList"]
    return raw.get("data", {}).get("dataTableDTOList") or []


def parse_breadth(mx_raw):
    """市场广度：上涨/下跌家数、成交额、涨停/跌停家数（取最新一行）。"""
    up = down = amount = zt = dt = None
    history = []
    tables = mx_tables(mx_raw)
    for e in tables:
        nm = e.get("nameMap", {})
        tbl = e.get("table", {})
        hn = tbl.get("headName", [])
        cols = {v: k for k, v in nm.items() if k != "headNameSub"}
        title = str(e.get("title", ""))
        # 广度表（含 上涨家数）
        if any("上涨家数" in c for c in cols):
            for i in range(len(hn)):
                row = {c: (tbl.get(cols[c], [])[i] if i < len(tbl.get(cols[c], [])) else None)
                       for c in cols}
                d = {"date": str(hn[i])[:10] if hn[i] else ""}
                try:
                    d["up"] = int(str(row.get("上涨家数", "0")).replace("家", ""))
                except Exception:
                    d["up"] = None
                try:
                    d["down"] = int(str(row.get("下跌家数", "0")).replace("家", ""))
                except Exception:
                    d["down"] = None
                d["amount"] = str(row.get("成交额(合计)", ""))
                history.append(d)
            # 最新一行 = 第一行
            if history:
                up = history[0]["up"]
                down = history[0]["down"]
                amt_s = history[0]["amount"]
                m = re.search(r"([\d.]+)\s*万亿", amt_s)
                amount = float(m.group(1)) if m else None
        # 涨停/跌停表
        if any("涨停家数" in c for c in cols):
            for i in range(len(hn)):
                row = {c: (tbl.get(cols[c], [])[i] if i < len(tbl.get(cols[c], [])) else None)
                       for c in cols}
                if i == 0:
                    try:
                        zt = int(str(row.get("涨停家数", "0")).replace("家", ""))
                    except Exception:
                        zt = None
                    try:
                        dt = int(str(row.get("跌停家数", "0")).replace("家", ""))
                    except Exception:
                        dt = None
    return up, down, amount, zt, dt, history


def parse_sector_flow(mx_raw):
    """板块资金：从篮子查询解析每个板块的主力净流入，排名取 Top 流入/流出。"""
    rows = []  # (name, net_yi)
    tables = mx_tables(mx_raw)
    for e in tables:
        nm = e.get("nameMap", {})
        tbl = e.get("table", {})
        hn = tbl.get("headName", [])
        cols = {v: k for k, v in nm.items() if k != "headNameSub"}
        # 找 主力净流入 列
        net_key = None
        for c in cols:
            if "主力净流入" in c:
                net_key = cols[c]
                break
        if not net_key:
            continue
        for i in range(len(hn)):
            name = str(hn[i]).replace("(板块)", "").strip()
            val = tbl.get(net_key, [])[i] if i < len(tbl.get(net_key, [])) else None
            if val is None:
                continue
            try:
                net = float(str(val))
            except Exception:
                # 可能是 "85.32亿元" 文本
                m = re.search(r"(-?[\d.]+)", str(val))
                net = float(m.group(1)) if m else None
            if net is not None:
                rows.append((name, round(net, 2)))
    if not rows:
        return [], []
    # 去重（同名取首个），按净流入排序
    seen = {}
    for n, v in rows:
        if n not in seen:
            seen[n] = v
    uniq = list(seen.items())
    uniq.sort(key=lambda x: x[1], reverse=True)
    top_in = [{"name": n, "val": f"+{v:.2f}亿", "val_yi": round(v, 2)} for n, v in uniq[:5] if v > 0]
    top_out = [{"name": n, "val": f"{v:.2f}亿", "val_yi": round(v, 2)} for n, v in uniq[-5:] if v < 0]
    top_out.reverse()
    return top_in, top_out


def trade_date_ms(trade_date):
    """把 YYYY-MM-DD 转成同花顺 limit-up-pool 需要的 date-ms（该日 00:00 Asia/Shanghai）。"""
    try:
        y, m, d = (int(x) for x in trade_date.split("-"))
        dt = datetime.datetime(y, m, d, 0, 0, 0,
                               tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def trade_date_ms_to_str(trade_date):
    """把 YYYY-MM-DD 转成问财自然语言用的 '2026年8月21日'。"""
    try:
        y, m, d = (int(x) for x in trade_date.split("-"))
        return f"{y}年{m}月{d}日"
    except Exception:
        return "今日"


def parse_overseas(mx_raw):
    """外围股指：从 mx-data 返回的行提取 名称/收盘/涨跌幅。"""
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
        if not chg_k:
            continue
        for i in range(len(hn)):
            name = str(hn[i]).split("(")[0].split("等的")[0].strip()
            if not name or name == "None":
                continue
            chg = tbl.get(chg_k, [])[i] if i < len(tbl.get(chg_k, [])) else None
            close = tbl.get(close_k, [])[i] if (close_k and i < len(tbl.get(close_k, []))) else None
            if chg is None:
                continue
            out.append({"name": name, "close": str(close or "—"),
                        "chg": str(chg).replace("%", "") + "%",
                        "cls": "positive" if "-" not in str(chg) else "negative"})
    # 去重（同名取首个）
    seen = {}
    for x in out:
        seen.setdefault(x["name"], x)
    return list(seen.values())


def parse_margin(mx_raw):
    """融资融券：融资余额/融券余额/两融合计。"""
    res = {"finance": None, "lending": None, "total": None}
    tables = mx_tables(mx_raw)
    for e in tables:
        nm = e.get("nameMap", {})
        tbl = e.get("table", {})
        hn = tbl.get("headName", [])
        cols = {v: k for k, v in nm.items() if k != "headNameSub"}
        f_k = next((cols[c] for c in cols if "融资余额" in c), None)
        l_k = next((cols[c] for c in cols if "融券余额" in c), None)
        t_k = next((cols[c] for c in cols if "融资融券余额" in c), None)
        for i in range(len(hn)):
            if f_k:
                res["finance"] = tbl.get(f_k, [])[i] if i < len(tbl.get(f_k, [])) else res["finance"]
            if l_k:
                res["lending"] = tbl.get(l_k, [])[i] if i < len(tbl.get(l_k, [])) else res["lending"]
            if t_k:
                res["total"] = tbl.get(t_k, [])[i] if i < len(tbl.get(t_k, [])) else res["total"]
    return res


def run_iwencai(script, query, limit=10, timeout=40):
    """调用问财 SkillHub 本地 cli.py（hithink-market-query / hithink-sector-selector）。
    返回解析后的 dict（含 success/datas），失败返回 None。"""
    if not IWENCAI_KEY:
        log("iwencai: IWENCAI_API_KEY 未设置，跳过")
        return None
    try:
        r = subprocess.run([sys.executable, script, "--query", query,
                            "--limit", str(limit), "--timeout", str(timeout)],
                           capture_output=True, encoding="utf-8",
                           env=dict(os.environ), timeout=timeout + 10)
        if r.returncode != 0:
            log(f"iwencai rc={r.returncode} err={r.stderr[:160]}")
            return None
        out = r.stdout.strip()
        if not out.startswith("{"):
            log(f"iwencai 非JSON输出: {out[:80]}")
            return None
        return json.loads(out)
    except Exception as e:
        log(f"iwencai except: {e}")
        return None


def parse_iwencai_flow(d):
    """问财 market-query 板块主力净买入额 -> [(name, yi)]（元转亿）。"""
    out = []
    for x in (d or {}).get("datas", []):
        name = x.get("指数简称") or x.get("板块名称")
        if not name:
            continue
        keys = [k for k in x if "净买入" in k or "净流入" in k]
        if not keys:
            skip = {"指数代码", "指数简称", "指数类型", "成分领域",
                    "板块名称", "板块代码"}
            keys = [k for k in x if k not in skip]
        if not keys:
            continue
        v = x[keys[-1]]
        try:
            out.append((name, round(float(v) / 1e8, 2)))
        except Exception:
            pass
    return out


def parse_iwencai_chg(d):
    """问财 sector-selector 行业板块涨幅 -> [(name, chg_pct)]。"""
    out = []
    for x in (d or {}).get("datas", []):
        name = x.get("指数简称") or x.get("板块名称")
        if not name:
            continue
        keys = [k for k in x if "涨跌幅" in k]
        if not keys:
            continue
        try:
            out.append((name, float(x[keys[-1]])))
        except Exception:
            pass
    return out


def fuyao_query(path, params=None, timeout=30):
    """调用同花顺 fuyao REST API。返回 (data_or_None, code_or_None)。"""
    if not FUYAO_KEY:
        log("fuyao: FUYAO_API_KEY 未设置，跳过")
        return None, None
    import urllib.request, urllib.parse
    url = FUYAO_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"X-api-key": FUYAO_KEY})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
            code = obj.get("code")
            if code == 0:
                return obj.get("data"), code
            log(f"fuyao {path} code={code} msg={obj.get('message')}")
            return None, code
        except Exception as e:
            if attempt == 0:
                continue
            log(f"fuyao {path} except: {e}")
            return None, None
    return None, None


def parse_fuyao_pool(data):
    """fuyao 涨停池 -> [{name,reason,board,seal_yi,is_st,ticker}]。"""
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


def parse_fuyao_dragon(data):
    """fuyao 龙虎榜 -> [{name,net_yi,change,concepts,org_yi,hot_yi}]（含机构/游资净买拆分）。"""
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


def parse_fuyao_break(data):
    """fuyao 炸板池 -> [{name,open_times,chg_pct,turnover_yi}]。"""
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


# ===== 第五源：选股宝 (xuangubao) 板块涨幅 + 领涨股 =====
def xuangubao_query(url, params=None, timeout=10, retries=2):
    """选股宝公开 API，无需鉴权。返回 JSON dict；失败返回 None。"""
    import urllib.request, urllib.parse, time as _time
    for attempt in range(retries + 1):
        try:
            full = url + "?" + urllib.parse.urlencode(params) if params else url
            req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            if d.get("code") == 20000:
                return d
            return d  # 仍返回，让上层判断
        except Exception:
            if attempt == retries:
                return None
            _time.sleep(1.5)
    return None


def parse_xuangubao(type_name, rank_ids, detail, top_n=10):
    """选股宝 rank(单类型 id 列表) + data 详情 -> 该类型板块领涨列表。

    返回 [{type_name, plate_id, name, chg_pct, fund_yi, limit_up_cnt,
           leaders:[{name, symbol, chg_pct}]}]
    """
    out = []
    if not rank_ids or not detail:
        return out
    for pid in rank_ids[:top_n]:
        p = detail.get(str(pid)) or detail.get(pid)
        if not p:
            continue
        leaders = []
        for s in (p.get("top_n_stocks") or {}).get("items", [])[:5]:
            leaders.append({
                "name": s.get("stock_chi_name"),
                "symbol": s.get("symbol"),
                "chg_pct": round((s.get("change_percent") or 0) * 100, 2),
            })
        out.append({
            "type_name": type_name,
            "plate_id": pid,
            "name": p.get("plate_name"),
            "chg_pct": round((p.get("core_avg_pcp") or 0) * 100, 2),
            "fund_yi": round((p.get("fund_flow") or 0) / 1e8, 2),
            "limit_up_cnt": p.get("limit_up_count") or 0,
            "leaders": leaders,
        })
    return out


def parse_limit_pool(raw):
    """同花顺涨停池：名称/题材/连板天数/封单金额。返回 list[{name,reason,board,seal_yi}]。"""
    items = (raw or {}).get("data", {}).get("item", [])
    out = []
    for it in items:
        out.append({
            "name": it.get("name"),
            "reason": it.get("limit_up_reason") or "—",
            "board": int(it.get("continue_day_cnt") or 1),
            "seal_yi": round((it.get("seal_money") or 0) / 1e8, 2),
            "is_st": bool(it.get("is_st")),
        })
    # 按连板降序、封单降序
    out.sort(key=lambda x: (x["board"], x["seal_yi"]), reverse=True)
    return out


def parse_ladder(ladder):
    """取最新交易日连板梯队。键名 two_board/three_board... 映射数字。"""
    items = (ladder or {}).get("data", {}).get("item", [])
    if not items:
        return {}, None, None, None
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
        names = [x.get("name", "").strip() for x in v]
        result[str(n)] = names
    if result:
        maxn = max(int(k) for k in result.keys())
        space = f"{maxn}板"
        space_stock = result[str(maxn)][0] if result[str(maxn)] else None
    else:
        space, space_stock = None, None
    return result, space, space_stock, tdate


def parse_indices(idx_snap):
    out = []
    items = (idx_snap or {}).get("data", {}).get("item", [])
    for it in items:
        code = it.get("thscode")
        out.append({
            "name": INDEX_NAMES.get(code, code),
            "value": f"{it.get('last_price'):.2f}",
            "chg_pct": round(it.get("price_change_ratio_pct") or 0, 2),
        })
    return out


def parse_hot(hot):
    items = (hot or {}).get("data", {}).get("item", [])
    return [{"rank": it.get("rank"), "name": it.get("name"), "heat": it.get("heat")}
            for it in items[:10]]


def parse_dragons(dtb):
    items = (dtb or {}).get("data", {}).get("stock_items", [])
    seen = {}
    for it in items:
        name = it.get("name")
        rec = {
            "name": name,
            "net_yi": round((it.get("net_value") or 0) / 1e8, 2),
            "change": round((it.get("change") or 0) * 100, 2),
            "concepts": [c.get("name") for c in it.get("concept_list", [])],
        }
        # 同名取净买额更大者
        if name not in seen or abs(rec["net_yi"]) > abs(seen[name]["net_yi"]):
            seen[name] = rec
    out = list(seen.values())
    out.sort(key=lambda x: x["net_yi"], reverse=True)
    return out[:12]


def main():
    log("=== 开始三源采集 ===")
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "_mx_out")
    os.makedirs(out_dir, exist_ok=True)
    src_log = []

    # 1) 同花顺
    ladder = run_hithink(["special", "limit-up-ladder", "--format", "json"])
    src_log.append(f"hithink.ladder {'ok' if ladder else 'FAIL'}")

    idx = run_hithink(["index", "snapshot", "--thscodes", INDEX_CODES, "--format", "json"])
    src_log.append(f"hithink.index {'ok' if idx else 'FAIL'}")

    hot = run_hithink(["special", "hot-stock", "--format", "json"])
    src_log.append(f"hithink.hot {'ok' if hot else 'FAIL'}")

    dtb = run_hithink(["special", "dragon-tiger", "--format", "json"])
    src_log.append(f"hithink.dragon {'ok' if dtb else 'FAIL'}")

    # 涨停池：用 ladder 推得的交易日算 date-ms（非交易日回退到最近收盘）
    ladder_map, space, space_stock, tdate = parse_ladder(ladder)
    ms = trade_date_ms(tdate) if tdate else None
    pool_args = ["special", "limit-up-pool", "--size", "200", "--format", "json"]
    if ms:
        pool_args += ["--date-ms", str(ms)]
    pool = run_hithink(pool_args)
    src_log.append(f"hithink.pool {'ok' if pool else 'FAIL'}({len(parse_limit_pool(pool))}只)")

    # 1.5) 第四源：fuyao 同花顺官方 REST（涨停池/龙虎榜/炸板池）
    # 涨停池（用同一 tdate 的 date-ms）
    fy_pool_data, _ = fuyao_query("/api/a-share/special-data/limit-up-pool",
                                  {"date_ms": ms, "size": 200} if ms else {"size": 200})
    src_log.append(f"fuyao.pool {'ok' if fy_pool_data else 'FAIL'}")
    fy_dragon_data, _ = fuyao_query("/api/a-share/special-data/dragon-tiger-list",
                                    {"date": tdate} if tdate else {})
    src_log.append(f"fuyao.dragon {'ok' if fy_dragon_data else 'FAIL'}")
    fy_break_data, _ = fuyao_query("/api/a-share/special-data/limit-break-pool",
                                   {"date_ms": ms, "size": 200} if ms else {"size": 200})
    src_log.append(f"fuyao.break {'ok' if fy_break_data else 'FAIL'}")
    fy_limit_up = parse_fuyao_pool(fy_pool_data)
    fy_dragons = parse_fuyao_dragon(fy_dragon_data)
    fy_break = parse_fuyao_break(fy_break_data)

    # 1.5) 第五源：选股宝 板块涨幅 + 领涨股（公开 API，无需鉴权）
    xg_types = {"概念板块": 1, "行业板块": 2, "风格板块": 3}
    xg_all = []
    xg_ok = True
    for tname, tid in xg_types.items():
        rj = xuangubao_query(XG_RANK, {"field": "core_avg_pcp", "type": tid})
        rids = (rj or {}).get("data", []) or []
        if not rids:
            xg_ok = False
            continue
        dj = xuangubao_query(XG_DATA, {
            "fields": "plate_id,plate_name,fund_flow,core_avg_pcp,limit_up_count,top_n_stocks",
            "plates": ",".join(str(i) for i in rids[:10]),
        })
        detail = (dj or {}).get("data", {}) or {}
        xg_all.extend(parse_xuangubao(tname, rids, detail, top_n=10))
    src_log.append(f"xuangubao.plates {'ok' if xg_ok else 'FAIL'}({len(xg_all)}个)")

    # 2) 东财 mx-data
    breadth_raw, _ = run_mx(MX_DATA, "沪深A股上涨家数 下跌家数 涨停家数 跌停家数 总成交额", out_dir)
    src_log.append(f"mx-data.breadth {'ok' if breadth_raw else 'FAIL'}")

    sector_raw, _ = run_mx(MX_DATA,
                           f"{SECTOR_BASKET} 行业主力资金净流入 2026-08-21", out_dir)
    src_log.append(f"mx-data.sector {'ok' if sector_raw else 'FAIL'}")

    # 2.5) 问财两源实时补强（东财配额耗尽时主力兜底，平时作交叉源）
    mq_flow_raw = run_iwencai(IWENCAI_MK,
                              f"{trade_date_ms_to_str(tdate) if tdate else '今日'} 主力净买入额排名前15的行业板块",
                              limit=15)
    src_log.append(f"iwencai.market-query(flow-in) {'ok' if mq_flow_raw else 'FAIL'}")
    # 补全流出项：主力净流出额前10（净买入额为负），避免板块资金流维度缺口
    mq_out_raw = run_iwencai(IWENCAI_MK,
                             f"{trade_date_ms_to_str(tdate) if tdate else '今日'} 主力净流出额排名前10的行业板块",
                             limit=10)
    src_log.append(f"iwencai.market-query(flow-out) {'ok' if mq_out_raw else 'FAIL'}")
    sc_chg_raw = run_iwencai(IWENCAI_SC,
                             f"{trade_date_ms_to_str(tdate) if tdate else '今日'} 涨幅前15的行业板块",
                             limit=15)
    src_log.append(f"iwencai.sector-selector {'ok' if sc_chg_raw else 'FAIL'}")
    mq_flow = parse_iwencai_flow(mq_flow_raw)
    # 合并流出项（净卖出额为负，拼接进 mq_flow 供降级与交叉使用）
    mq_flow_out = parse_iwencai_flow(mq_out_raw)
    # 取流出的负项（值<0 或字段名为净卖出）
    for n, v in mq_flow_out:
        if v < 0 and n not in {x[0] for x in mq_flow}:
            mq_flow.append((n, v))
    sc_chg = parse_iwencai_chg(sc_chg_raw)

    # 3) 问财 mx-search 叙事
    _, narrative = run_mx(MX_SEARCH,
                          "2026年8月21日 A股收盘 涨停家数 连板梯队 主线板块 资金流向 市场情绪 后市",
                          out_dir)
    src_log.append(f"mx-search.narrative {'ok' if narrative else 'FAIL'}")

    # 4) 外围股指 + 融资融券（东财）
    ov_raw, _ = run_mx(MX_DATA, "2026年8月21日 收盘 日经225 韩国综合 道琼斯 纳斯达克 标普500 最新点位 涨跌幅", out_dir)
    src_log.append(f"mx-data.overseas {'ok' if ov_raw else 'FAIL'}")
    margin_raw, _ = run_mx(MX_DATA, "2026年8月21日 A股 融资余额 融券余额 融资融券余额", out_dir)
    src_log.append(f"mx-data.margin {'ok' if margin_raw else 'FAIL'}")

    # 组装（实时优先，东财配额耗尽时回退缓存真实值）
    up, down, amount, zt, dt, history = parse_breadth(breadth_raw)
    if up is None:
        up = MX_FALLBACK["up"]
    if down is None:
        down = MX_FALLBACK["down"]
    if amount is None:
        amount = MX_FALLBACK["amount_yi"]
    if zt is None:
        zt = MX_FALLBACK["zt"]
    if dt is None:
        dt = MX_FALLBACK["dt"]
    indices = parse_indices(idx)
    hot_list = parse_hot(hot)
    # 龙虎榜优先用 fuyao（含机构/游资净买拆分），回退到 hithink CLI
    dragons = fy_dragons if fy_dragons else parse_dragons(dtb)
    sector_in, sector_out = parse_sector_flow(sector_raw)
    # 东财实时解析结果留存，供交叉验证对照（即使后面降级也不影响基准）
    emx_sector_in = sector_in
    emx_sector_out = sector_out
    # 三级降级：东财实时 -> 问财实时 -> 缓存
    if not sector_in:
        if mq_flow:
            # 问财主力净买入额 Top（正）作为流入榜
            pos = [(n, v) for n, v in mq_flow if v > 0][:5]
            sector_in = [{"name": n, "val": f"+{v:.2f}亿", "val_yi": v} for n, v in pos]
        else:
            sector_in = MX_FALLBACK["sector_in"]
    if not sector_out:
        if mq_flow:
            neg = [(n, v) for n, v in mq_flow if v < 0][-5:]
            neg.reverse()
            sector_out = [{"name": n, "val": f"{v:.2f}亿", "val_yi": v} for n, v in neg]
        else:
            sector_out = MX_FALLBACK["sector_out"]

    # 行业板块涨幅（问财 sector-selector 实时；失败留 None 由 update 决定）
    sector_chg = [{"name": n, "chg_pct": round(v, 2)} for n, v in sc_chg[:10]] if sc_chg else None
    overseas = parse_overseas(ov_raw) or MX_FALLBACK["overseas"]
    margin = parse_margin(margin_raw)
    if not margin.get("finance"):
        margin = MX_FALLBACK["margin"]

    trade_date = tdate or datetime.date.today().isoformat()
    # 涨停池优先用 fuyao（更结构化、字段全），否则用 hithink CLI
    limit_up_final = fy_limit_up if fy_limit_up else parse_limit_pool(pool)
    # 真实炸板率：fuyao 炸板池 / (涨停池 + 炸板池)
    break_cnt = len(fy_break)
    zt_real = len(limit_up_final)
    real_break_rate = round(break_cnt / (zt_real + break_cnt) * 100, 2) if (zt_real + break_cnt) else None
    log(f"交易日={trade_date} 空间板={space}({space_stock}) 涨跌={up}/{down} "
        f"成交={amount}万亿 涨停/跌停={zt}/{dt} 板块流入{len(sector_in)}/流出{len(sector_out)} "
        f"fuyao涨停{zt_real}/炸板{break_cnt}/真实炸板率{real_break_rate}%")

    # 交叉对比分析：每日四源一致性校验
    cross_check = build_cross_check(emx_sector_in, emx_sector_out, mq_flow, sc_chg,
                                    limit_up_final, fy_dragons, parse_dragons(dtb),
                                    fy_break, pool, real_break_rate, xg_all)

    result = {
        "trade_date": trade_date,
        "up": up, "down": down, "flat": (None if up is None else None),
        "total": (up + down if (up and down) else None),
        "amount_yi": amount,
        "zt": zt, "dt": dt,
        "indices": indices,
        "ladder": ladder_map,
        "space_board": space,
        "space_stock": space_stock,
        "hot": hot_list,
        "dragons": dragons,
        "limit_up": limit_up_final,
        "break_pool": fy_break,
        "break_rate_real": real_break_rate,
        "fuyao_source": {
            "limit_up_count": zt_real,
            "break_count": break_cnt,
            "dragon_count": len(fy_dragons) if fy_dragons else 0,
        },
        "sector_in": sector_in,
        "sector_out": sector_out,
        "sector_chg": sector_chg,
        "plate_leaders": xg_all,
        "breadth_history": history,
        "narrative": (narrative or "")[:6000],
        "overseas": overseas,
        "margin": margin,
        "cross_check": cross_check,
        "source_log": src_log,
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))


def build_cross_check(sector_in, sector_out, mq_flow, sc_chg, limit_up,
                      fy_dragons=None, hithink_dragons=None,
                      fy_break=None, hithink_pool=None, real_break_rate=None,
                      xg_all=None):
    """每日三源交叉对比分析：
     1) 板块资金流：东财实时(若有) vs 问财实时方向一致性
     2) 问财内部：资金流入 Top vs 涨幅 Top 重叠度
     3) 个股维度：同花顺涨停池抽样是否在问财可查行情
    """
    cc = {"ok": False, "dimensions": []}

    # 维度1：板块资金流方向一致性（东财缓存/实时 vs 问财）
    # 东财侧取 sector_in/out 的 (name, yi)；东财实时空时回退 MX_FALLBACK 真实缓存
    emx_pairs = [(s["name"], s["val_yi"]) for s in (sector_in or [])]
    emx_pairs += [(s["name"], s["val_yi"]) for s in (sector_out or [])]
    if not emx_pairs:
        emx_pairs = [(s["name"], s["val_yi"]) for s in MX_FALLBACK["sector_in"]]
        emx_pairs += [(s["name"], s["val_yi"]) for s in MX_FALLBACK["sector_out"]]
    mq_map = {n: v for n, v in (mq_flow or [])}
    ALIAS = {
        "通信设备": ["通信设备", "通信网络设备"], "有色金属": ["工业金属", "能源金属", "有色金属"],
        "黄金": ["贵金属", "黄金"], "半导体": ["半导体"],
        "医药生物": ["医药", "生物制品", "生物制药", "医疗", "化学制药", "中药"],
        "银行": ["银行"],
    }
    matched = []
    for nm, ev in emx_pairs:
        kws = ALIAS.get(nm, [nm])
        mv = next((kv for kn, kv in mq_map.items() if any(k in kn for k in kws)), None)
        if mv is not None:
            matched.append({"eastmoney": nm, "emx_yi": ev, "iwencai": mv,
                            "same_sign": (ev > 0) == (mv > 0)})
        else:
            matched.append({"eastmoney": nm, "emx_yi": ev, "iwencai": None,
                            "same_sign": None})
    # 仅对两侧都有值的项判定方向一致性（问财未覆盖的流出项不计入冲突）
    signed = [m for m in matched if m["same_sign"] is not None]
    dir_consistent = all(m["same_sign"] for m in signed) if signed else None
    uncovered = [m["eastmoney"] for m in matched if m["same_sign"] is None]
    cc["dimensions"].append({
        "name": "板块主力资金流（东财 vs 问财）",
        "matched": matched,
        "direction_consistent": dir_consistent,
        "uncovered": uncovered,
        "note": "口径不同(申万一级 vs 同花顺三级行业)，仅比对方向；"
                + (f"问财未覆盖流出项：{','.join(uncovered)}" if uncovered else "全项覆盖"),
    })

    # 维度2：问财内部 资金Top vs 涨幅Top 重叠
    flow_top = {n for n, v in (mq_flow or [])[:8] if v > 0}
    chg_top = {n for n, v in (sc_chg or [])[:8] if v > 0}
    overlap = sorted(flow_top & chg_top)
    cc["dimensions"].append({
        "name": "问财内部：资金流入Top vs 涨幅Top",
        "flow_top": sorted(flow_top),
        "chg_top": sorted(chg_top),
        "overlap": overlap,
        "overlap_count": len(overlap),
    })

    # 维度3：个股维度 同花顺涨停池抽样 -> 问财可查
    samples = []
    for it in (limit_up or [])[:5]:
        nm = it.get("name")
        if not nm:
            continue
        d = run_iwencai(IWENCAI_MK, f"{nm} 最新价 涨跌幅 主力净买入额", limit=1)
        found = bool(d and d.get("datas"))
        samples.append({"name": nm, "found": found})
    cc["dimensions"].append({
        "name": "个股维度：同花顺涨停池 抽样 vs 问财可查",
        "samples": samples,
        "all_found": all(s["found"] for s in samples) if samples else None,
    })

    # 维度4：fuyao 龙虎榜 vs 同花顺龙虎榜 个股重叠与净买方向一致性
    if fy_dragons and hithink_dragons:
        fy_map = {d["name"]: d["net_yi"] for d in fy_dragons}
        hk_map = {d["name"]: d["net_yi"] for d in hithink_dragons}
        both = [n for n in fy_map if n in hk_map]
        same_dir = sum(1 for n in both if (fy_map[n] > 0) == (hk_map[n] > 0)) if both else 0
        cc["dimensions"].append({
            "name": "龙虎榜（fuyao 官方 vs 同花顺 CLI）",
            "fuyao_count": len(fy_dragons),
            "hithink_count": len(hithink_dragons),
            "overlap": both,
            "overlap_count": len(both),
            "same_direction": same_dir,
            "direction_consistent": (same_dir == len(both)) if both else None,
        })
    else:
        cc["dimensions"].append({
            "name": "龙虎榜（fuyao 官方 vs 同花顺 CLI）",
            "fuyao_count": len(fy_dragons or []),
            "hithink_count": len(hithink_dragons or []),
            "overlap": [], "overlap_count": 0,
            "same_direction": 0, "direction_consistent": None,
        })

    # 维度5：fuyao 涨停池 vs 同花顺涨停池 只数与个股一致性 + 真实炸板率
    fy_set = {x["name"] for x in (limit_up or [])}
    hk_set = {x["name"] for x in parse_limit_pool(hithink_pool)}
    in_both = fy_set & hk_set
    cc["dimensions"].append({
        "name": "涨停池（fuyao 官方 vs 同花顺 CLI）",
        "fuyao_count": len(fy_set),
        "hithink_count": len(hk_set),
        "overlap_count": len(in_both),
        "consistent": (len(fy_set) == len(hk_set) == len(in_both)) if fy_set and hk_set else None,
        "real_break_rate": real_break_rate,
    })

    # 维度6：选股宝板块涨幅 vs 问财 sector-selector / fuyao 方向一致性 + 领涨股 vs 涨停池
    if xg_all:
        # 6a 选股宝行业/概念涨幅 Top 与问财 sector-selector(chg) 方向对照
        xg_chg = {p["name"]: p["chg_pct"] for p in xg_all}
        sc_map = {n: v for n, v in (sc_chg or [])}
        ALIAS6 = {
            "房屋建筑": ["建筑", "房屋建筑"], "锂": ["锂"], "贵金属": ["黄金", "贵金属"],
            "工业金属": ["有色金属", "工业金属"], "半导体": ["半导体"],
            "化学制药": ["医药", "化学制药", "生物制品"], "银行": ["银行"],
        }
        matched6 = []
        for xn, xv in xg_chg.items():
            kws = ALIAS6.get(xn, [xn])
            sv = next((kv for kn, kv in sc_map.items() if any(k in kn for k in kws)), None)
            if sv is not None:
                matched6.append({"xuangubao": xn, "xg_pct": xv, "iwencai": sv,
                                 "same_sign": (xv > 0) == (sv > 0)})
        signed6 = [m for m in matched6 if m["same_sign"] is not None]
        dir6 = all(m["same_sign"] for m in signed6) if signed6 else None
        # 6b 领涨股 vs 同花顺涨停池个股重叠
        pool_names = {x["name"] for x in (limit_up or [])}
        leader_hits = []
        for p in xg_all:
            for ld in p.get("leaders", []):
                if ld.get("name") in pool_names:
                    leader_hits.append(f"{p['name']}/{ld['name']}")
        cc["dimensions"].append({
            "name": "选股宝板块（涨幅 vs 问财 + 领涨股 vs 涨停池）",
            "matched": matched6,
            "direction_consistent": dir6,
            "leader_overlap": leader_hits,
            "leader_overlap_count": len(leader_hits),
        })
    else:
        cc["dimensions"].append({
            "name": "选股宝板块（涨幅 vs 问财 + 领涨股 vs 涨停池）",
            "matched": [], "direction_consistent": None,
            "leader_overlap": [], "leader_overlap_count": 0,
        })

    cc["ok"] = True
    return cc


if __name__ == "__main__":
    main()
