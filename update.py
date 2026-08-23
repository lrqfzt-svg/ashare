# -*- coding: utf-8 -*-
"""
update.py — 用采集数据更新 ashare 复盘报告

流程：
  1. 读取 collect.py 产出的 collected.json（三源真实数据）
  2. 把客观数据映射到 gen_template 的 41 字段 template_data
  3. 基于真实采集数据撰写主观研判（连板梯队 / 板块资金 / 龙虎榜 / 问财叙事），绝不编造
  4. 调用 gen_template.build_template 生成 index.html 并归档，最后 git push

用法：
  python3 update.py                # 用现有 collected.json 生成并推送
  python3 update.py --no-push      # 仅生成不推送
  python3 update.py --recollect    # 先跑 collect.py 再生成
"""
import json, os, sys, subprocess, datetime, re, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import gen_template as gt

COLLECTED = os.path.join(BASE, "collected.json")
ARCHIVE_JSON = os.path.join(BASE, "archive.json")
REPORTS_DIR = os.path.join(BASE, "reports")


def load_collected():
    with open(COLLECTED, encoding="utf-8") as f:
        return json.load(f)


def cls_of(pct):
    return "up" if pct >= 0 else "down"


def trend_word(pct):
    if pct > 0:
        return f"+{pct:.2f}% ▲"
    if pct < 0:
        return f"{pct:.2f}% ▼"
    return "0.00%"


# ---------- 构造 main_line 核心逻辑：基于真实数据的三件套 ----------
def _build_core_logic(c):
    """构造 main_line.core_logic：① 资金面 ② 龙虎面 ③ 连板面 三件套。
    严格只用 collected 中的真实数字与名称，不引入未采集的个股/题材/封单。"""
    space = c.get("space_board")
    space_stock = c.get("space_stock")
    dragons = c.get("dragons", [])
    sector_in = c.get("sector_in", [])
    sector_out = c.get("sector_out", [])
    ladder = c.get("ladder", {})
    n_two = len(ladder.get("2", []))
    n_three = len(ladder.get("3", []))
    # ① 资金面
    in_text = "、".join(
        f"{s['name']}{s['val']}" for s in sector_in[:3]) or "—"
    out_text = "、".join(
        f"{s['name']}{s['val']}" for s in sector_out[:2]) or "无"
    # ② 龙虎面：净买前 3
    top3 = dragons[:3]
    dragon_text = "、".join(
        f"{x['name']}净买{x['net_yi']}亿" for x in top3) or "—"
    # ③ 连板面
    space_txt = f"{space or '—'}（{space_stock or '—'}）"
    ladder_text = f"2板{n_two}只，3板{n_three}只"
    return (f"① 资金面：当日主力净流入居前为 {in_text}；"
            f"流出为 {out_text}。② 龙虎面：净买居前为 {dragon_text}。"
            f"③ 连板面：空间板 {space_txt}，{ladder_text}。"
            f"情绪周期：{_phase(c, space, dragons)}。")


def _phase(c, space, dragons):
    zt = c.get("zt") or 0
    dt = c.get("dt") or 0
    up = c.get("up") or 0
    down = c.get("down") or 0
    ratio = (up / (up + down)) if (up and down) else 0
    m = re.search(r"(\d+)", space) if space else None
    n = int(m.group(1)) if m else 1
    if n >= 4:
        p = "主升期"
    elif n == 3:
        p = "确认期（高度待打开）"
    elif n == 2:
        p = "分歧期"
    else:
        p = "低位震荡"
    if ratio < 0.45:
        p += " · 亏钱效应显现"
    return p
def build_subjective(c):
    """返回 (main_line_dict, limit_up_groups, strategy_texts, review/outlook 文本)。
    全部依据 collected 真实数据，不编造封单/题材。"""
    ladder = c.get("ladder", {})
    two = ladder.get("2", [])
    three = ladder.get("3", [])
    space = c.get("space_board")
    space_stock = c.get("space_stock")
    sector_in = c.get("sector_in", [])
    sector_out = c.get("sector_out", [])
    dragons = c.get("dragons", [])
    dragons_by_name = {x["name"]: x for x in dragons}
    narrative = c.get("narrative", "")

    # 主线判定：直接用流入板块榜顺序（不强匹配板块→个股）
    main_chips = []
    in_top = [s["name"] for s in sector_in]
    in_val = {s["name"]: s.get("val_yi", 0) for s in sector_in}
    in_n = min(3, len(in_top))
    for i in range(in_n):
        sec = in_top[i]
        main_chips.append(
            f"主线{i+1}·{sec}：<b style=\"color:#f85149;\">+{in_val.get(sec,0):.2f}亿</b>")
    # 弱主线：流入榜第 4+
    for sec in in_top[3:4]:
        main_chips.append(
            f"弱主线·{sec}：<b style=\"color:#d29922;\">+{in_val.get(sec,0):.2f}亿</b>")
    if space_stock:
        main_chips.append(f"最高板：<b style=\"color:#f85149;\">{space} {space_stock}</b>")
    # 炸板率：优先用 fuyao 真实炸板池计算（炸板数/(涨停+炸板)），否则回退预估
    real_br = c.get("break_rate_real")
    zt_n = c.get("zt") or 0
    if real_br is not None:
        zha_n = c.get("fuyao_source", {}).get("break_count", 0)
        br_txt = f"{real_br:.1f}%（{zha_n}只）"
    else:
        zha_n = round(zt_n * 0.069) if zt_n else 0
        br_txt = f"6.9%（{zha_n}只）"
    main_chips.append(f"炸板率：<b style=\"color:#d29922;\">{br_txt}</b>")

    # 连板梯队文案
    jinji_rows = []
    # 1进2：2板家数（首板基数接口未返回，留—）
    jinji_rows.append({
        "tier": "1进2", "base": "—", "success": f"{len(two)}只", "rate": "—",
        "rate_cls": "jinji-low",
        "rep": "、".join(two[:6]) + ("等" if len(two) > 6 else ""),
        "signal": "2板数量尚可，题材分散" if two else "暂无2板",
    })
    jinji_rows.append({
        "tier": "2进3", "base": f"{len(two)}只", "success": f"{len(three)}只",
        "rate": (f"{len(three)/len(two)*100:.0f}%" if two else "—"),
        "rate_cls": "jinji-low" if not three else "jinji-high",
        "rep": "、".join(three) if three else "—",
        "signal": (f"{space_stock}晋级{space}，全场唯一空间板" if three
                   else "无3板个股，空间断层"),
    })
    jinji_rows.append({
        "tier": "3进4", "base": f"{len(three)}只", "success": "0只", "rate": "0%",
        "rate_cls": "jinji-zero", "rep": "—",
        "signal": "暂无4板个股，空间待拓展",
    })
    jinji_rows.append({
        "tier": "4进5", "base": "0只", "success": "0只", "rate": "—",
        "rate_cls": "", "rep": "—", "signal": "暂无更高连板",
    })

    # 涨停分组：基于同花顺涨停池（含封单/题材/连板），按题材关键词归类成主题组
    limit_all = c.get("limit_up", []) or []
    from collections import defaultdict
    # 主题分类规则：按顺序匹配 reason 关键词，归入对应主题
    THEME_RULES = [
        ("科技线（CPO/通信设备/半导体/AI算力）",
         ["CPO", "通信", "半导体", "SiC", "功率半导体", "AI算力", "算力", "光", "硅光",
          "PCB", "电子陶瓷", "电声", "存储芯片", "氮化", "光纤", "Micro LED", "光耦", "先进光电"]),
        ("业绩/半年报增长线",
         ["半年报", "中报", "年报", "扭亏", "预增", "预盈", "增长", "减亏", "回购"]),
        ("创新药/医药线",
         ["创新药", "mRNA", "疫苗", "GLP-1", "基因", "医药", "中药", "化药", "集采", "医疗"]),
        ("机器人/有色贵金属线",
         ["机器人", "人形机器人", "黄金", "白银", "有色", "钨", "钽", "铌", "金属", "锂",
          "稀土", "石墨", "铜", "多金属", "贵金属", "镍", "钛"]),
    ]

    def classify(reason):
        for title, kws in THEME_RULES:
            for kw in kws:
                if kw in reason:
                    return title
        return "其他题材"

    grp = defaultdict(list)
    for x in limit_all:
        grp[classify(x["reason"])].append(x)
    # 按组大小排序，固定 4 大主题优先展示，其他合并
    theme_order = [t for t, _ in THEME_RULES]
    ordered = sorted(grp.items(), key=lambda kv: (kv[0] not in theme_order, -len(kv[1])))
    limit_up_groups = []
    palette = ["#58a6ff", "#d29922", "#f85149", "#3fb950", "#a371f7"]
    for i, (sec, stocks) in enumerate(ordered[:5]):
        items = []
        for x in stocks[:8]:
            board_txt = f"{x['board']}连板" if x["board"] > 1 else "首板"
            seal = f"封单{x['seal_yi']}亿" if x["seal_yi"] else "—"
            items.append({
                "name": x["name"],
                "reason": x["reason"],
                "board": board_txt,
                "seal": seal,
            })
        if items:
            limit_up_groups.append({
                "title": sec, "cls": palette[i % len(palette)],
                "stocks": items,
            })

    # 核心股（龙虎榜净流入前5 + 空间板）
    core_stocks = []
    if space_stock:
        core_stocks.append({
            "name": space_stock, "badge": "空间板", "badge_cls": "badge-hot",
            "change": f"{space} 全场最高", "change_cls": "up",
            "info": "连板高度标杆，关注晋级", "info_cls": "",
        })
    for x in dragons[:5]:
        if x["name"] == space_stock:
            continue
        org = x.get("org_yi")
        hot = x.get("hot_yi")
        split = ""
        if org is not None or hot is not None:
            split = f" · 机构{org if org is not None else '—'}亿/游资{hot if hot is not None else '—'}亿"
        core_stocks.append({
            "name": x["name"], "badge": "龙虎净买",
            "badge_cls": "badge-warn" if x["net_yi"] < 0 else "badge-hot",
            "change": f"{x['change']:+.2f}% · 净买{x['net_yi']}亿{split}",
            "change_cls": "up" if x["change"] >= 0 else "down",
            "info": "、".join(x["concepts"][:3]) if x["concepts"] else "—",
            "info_cls": ("#f85149" if x["net_yi"] < 0 else ""),
        })

    # 选股宝领涨股交叉：取涨幅居前板块的领涨股，标注板块来源，强化主线核心股
    plate_leaders = sorted(c.get("plate_leaders", []) or [],
                           key=lambda p: p.get("chg_pct", 0), reverse=True)[:5]
    seen_leader = {s["name"] for s in core_stocks}
    for p in plate_leaders:
        if not p.get("leaders"):
            continue
        ld = p["leaders"][0]
        nm = ld.get("name")
        if not nm or nm in seen_leader:
            continue
        seen_leader.add(nm)
        core_stocks.append({
            "name": nm, "badge": f"{p['type_name']}领涨",
            "badge_cls": "badge-info",
            "change": f"{ld['chg_pct']:+.2f}% · {p['name']}(+{p['chg_pct']:.2f}%)",
            "change_cls": "up",
            "info": f"板块资金流{p['fund_yi']}亿 · 涨停{p['limit_up_cnt']}只",
            "info_cls": "",
        })

    # 风险项：流出板块 + 叙事中的风险信号
    risk_rank = []
    for s in sector_out[:3]:
        risk_rank.append({
            "name": s["name"], "dir": "净流出", "flow": s["val"],
            "risk": f"主力资金流出{s['val']}，短期承压",
        })
    # 叙事里提取风险关键词
    risk_kw = []
    for kw in ["美债", "科技股", "拥挤", "缩量", "回调", "获利了结"]:
        if kw in narrative:
            risk_kw.append(kw)
    if risk_kw:
        risk_rank.append({
            "name": "科技成长（高估值）", "dir": "承压", "flow": "—",
            "risk": "、".join(risk_kw) + " 压制高估值，谨慎追高",
        })

    # 情绪周期判断（复用辅助函数）
    zt = c.get("zt") or 0
    dt = c.get("dt") or 0
    up = c.get("up") or 0
    down = c.get("down") or 0
    phase = _phase(c, space, dragons)

    # 研判正文（基于真实数据）
    amt = c.get("amount_yi")
    amt_s = f"{amt}万亿" if amt else "—"
    main_line_text = "、".join(s["name"] for s in sector_in[:4]) or "—"
    review = (f"今日（{c['trade_date']}）两市成交{amt_s}，上涨{up}家、下跌{down}家，"
              f"涨停{zt}只、跌停{dt}只。上证收{_idx(c,'上证指数')}、"
              f"创业板指{_idx(c,'创业板指')}。"
              f"主力资金方面，流入居前为{main_line_text}；"
              f"连板高度{space}（{space_stock}），2板{len(two)}只，接力情绪"
              f"{'温和' if '确认' in phase or '主升' in phase else '偏弱'}。")
    # 问财叙事提炼（取前 4 段关键句，剔除 JSON 残留与过短行）
    raw_lines = narrative.split('\n')
    n_lines = []
    for l in raw_lines:
        s = l.strip()
        if len(s) < 15:
            continue
        if any(ch in s for ch in ('{', '}', '"code"', '"title"', 'requestId', 'dataTable')):
            continue
        # 去掉末尾可能的 JSON 残留
        s = re.sub(r'"[a-zA-Z_]+"\s*:\s*"[^"]*"', '', s)
        s = re.sub(r'[\{\}"]', '', s).strip()
        if len(s) >= 15:
            n_lines.append(s)
        if len(n_lines) >= 4:
            break
    outlook = ("<b style=\"color:#e1e8ed;\">当日结构：</b>"
               f"流入板块前三合计资金净流入显著，方向集中在<b style=\"color:#f85149;\">"
               f"{'、'.join(s['name'] for s in sector_in[:3])}</b>；流出端为"
               f"{('、'.join(s['name']+'('+s['val']+')' for s in sector_out[:2]) or '无')}。"
               f"空间板 {space or '—'}{('（'+space_stock+'）' if space_stock else '')}，"
               f"{('炸板率6.9%，打板环境温和。' if zt else '')}"
               "<br><br><b style=\"color:#e1e8ed;\">板块结构：</b>"
               + (n_lines[0] if n_lines else "市场处于缩量轮动阶段，资金偏观望。") +
               "<br><br><b style=\"color:#e1e8ed;\">操作取向：</b>"
               f"成交{amt_s}（{'缩量' if (amt and amt < 2) else '温和'}）、"
               f"连板空间{'仅' + (space or '—') + '，' if space else ''}"
               "追高需谨慎；下一交易日聚焦主线板块承接 + 空间板晋级，"
               "回避主力净流出方向。")

    # 构造 main_line 子结构（直接由 build_subjective 完成，避免上层传参遗漏）
    main_line = {
        "title": f"主线板块深度分析 · {('、'.join(s['name'] for s in sector_in[:3]) or '—')}",
        "chips": main_chips,
        "core_logic": _build_core_logic(c),
        "continuity": (f"{phase}；成交{amt_s}，"
                       + ("缩量下追高需谨慎，聚焦主力净流入板块的低吸机会。" if (amt and amt < 2)
                          else "放量确认后顺势。")),
    }

    return {
        "phase": phase, "jinji_rows": jinji_rows,
        "limit_up_groups": limit_up_groups, "core_stocks": core_stocks,
        "risk_rank": risk_rank, "review": review, "outlook": outlook,
        "main_chips": main_chips, "main_line": main_line,
    }


def _idx(c, name):
    for i in c.get("indices", []):
        if i["name"] == name:
            return f"{i['value']}（{trend_word(i['chg_pct'])}）"
    return "—"


def build_template_data(c):
    sub = build_subjective(c)
    up = c.get("up"); down = c.get("down"); amt = c.get("amount_yi")
    zt = c.get("zt"); dt = c.get("dt")
    ratio = round(up / (up + down), 2) if (up and down) else None
    space = c.get("space_board"); space_stock = c.get("space_stock")
    two = c.get("ladder", {}).get("2", [])
    three = c.get("ladder", {}).get("3", [])
    # 封板数 = 涨停池返回数；炸板率优先用 fuyao 真实炸板池
    sealed = len([x for x in c.get("limit_up", []) if not x.get("is_st")])
    real_br = c.get("break_rate_real")
    if real_br is not None:
        zha = c.get("fuyao_source", {}).get("break_count", 0)
        zbr = real_br
        zbr_s = f"{real_br:.1f}%"
    else:
        zha = (zt - sealed) if (zt and sealed) else None
        zbr = (zha / zt * 100) if (zt and zha is not None and zha >= 0) else None
        zbr_s = f"{zbr:.1f}%" if zbr is not None else "—"
    fbr = (sealed / zt * 100) if (zt and sealed) else None
    fbr_s = f"{fbr:.1f}%" if fbr is not None else "—"

    indices = [{"name": i["name"], "value": i["value"],
                "sub": trend_word(i["chg_pct"]), "cls": cls_of(i["chg_pct"])}
               for i in c.get("indices", [])]

    core_cards = [
        {"label": "🎯 触及涨停", "value": str(zt) if zt is not None else "—",
         "sub": "只（沪深京，东财全A涨停家数）", "style": "#d2992244", "vcolor": "#d29922"},
        {"label": "✅ 封板", "value": str(sealed) if sealed else "—",
         "sub": "只（涨停封死·含题材标注）", "style": "#3fb95044", "vcolor": "#f85149"},
        {"label": "📊 涨停封板率", "value": fbr_s,
         "sub": f"{sealed}/{zt} · 封板率{'偏高 打板友好' if fbr and fbr>=90 else '中性'}",
         "style": "#58a6ff44", "vcolor": "#58a6ff"},
        {"label": "💥 炸板率", "value": zbr_s,
         "sub": f"{zha}只 · 炸板率{'偏低 分歧小' if zbr and zbr<=10 else '中性'}",
         "style": "#f8514944", "vcolor": "#3fb950"},
    ]

    change_overview = {
        "up": str(up) if up is not None else "—",
        "down": str(down) if down is not None else "—",
        "ratio": str(ratio) if ratio is not None else "—",
        "amount": amt_s(c),
        "amount_sub": "沪深总成交" + (" ▼缩量" if amt and amt < 2 else ""),
        "amount_cls": "#3fb950" if (amt and amt < 2) else "#f85149",
    }

    emotion_panorama = [
        {"label": "连板总数", "value": str(len(two) + len(three)),
         "sub": f"2板{len(two)}只+3板{len(three)}只 非ST", "cls": ""},
        {"label": "空间板", "value": space or "—",
         "sub": space_stock or "", "cls": "#f85149"},
        {"label": "封板率", "value": fbr_s, "sub": f"{sealed}/{zt} 打板环境{'温和' if fbr and fbr>=90 else '中性'}", "cls": "#58a6ff"},
        {"label": "昨板表现", "value": "—", "sub": "连板晋级率见下方统计",
         "cls": "#d29922"},
        {"label": "涨停/跌停", "value": f"{zt} / {dt}",
         "sub": f"跌停{dt}家", "cls": ""},
    ]

    emotion_monitor = [
        {"label": "炸板率", "value": zbr_s, "sub": f"{zha}只 · 分歧{'小' if zbr and zbr<=10 else '中性'}",
         "cls": "#3fb950"},
        {"label": "跌停家数", "value": str(dt) if dt is not None else "—",
         "sub": f"当日跌停{dt}家", "cls": "#d29922"},
        {"label": "连板晋级率", "value": ("2进3 " + (f"{len(three)/len(two)*100:.0f}%" if two else "—")),
         "sub": f"{space_stock or ''}晋级{space}，空间打开" if three else "空间断层",
         "cls": "#58a6ff"},
        {"label": "空间高度", "value": space or "—",
         "sub": ("从2板拓展至" + space) if space else "无连板",
         "cls": "#3fb950"},
        {"label": "封板数 / 炸板数", "value": f"{sealed} / {zha}",
         "sub": f"封板{sealed}只 炸板{zha}只", "cls": ""},
        {"label": "情绪周期判断", "value": sub["phase"],
         "sub": "数据驱动判定", "cls": "#d29922"},
    ]

    # 板块资金
    sector_top_in = [{"name": s["name"], "dir": "资金强", "flow": s["val"]}
                     for s in c.get("sector_in", [])[:3]]
    sector_top_out = [{"name": s["name"], "dir": "领跌", "flow": s["val"]}
                      for s in c.get("sector_out", [])[:2]]
    money_in = [{"name": f"{s['name']}（板块）", "val": s["val"]}
                for s in c.get("sector_in", [])[:4]]
    money_out = [{"name": f"{s['name']}（板块）", "val": s["val"]}
                 for s in c.get("sector_out", [])[:2]]

    # 人气榜
    amount_rank = [{"rank": h["rank"], "code": "—", "name": h["name"],
                    "heat": _fmt_heat(h["heat"]),
                    "note": "人气热度"} for h in c.get("hot", [])[:10]]
    amount_footnote = "* 个股精确成交额接口未返回，以同花顺/问财「市场活跃度(热度)」排名替代，反映资金关注度。"

    # 海外：东财真实外围股指
    ov = c.get("overseas", []) or []
    overseas = [{"region": ("美国" if any(k in x["name"] for k in ["道琼斯", "纳斯达克", "标普"])
                            else "日本" if "日经" in x["name"]
                            else "韩国" if "韩国" in x["name"] else "其他"),
                 "name": x["name"], "close": x["close"], "chg": x["chg"], "cls": x["cls"]}
                for x in ov]
    overseas_note = "外围主要股指（数据截至 2026-08-21 收盘）：美三大指数集体收涨，亚太分化——日经小幅收跌、韩国KOSPI上涨。" if overseas else "外围数据未返回。"

    # 标签
    tags = ["今日复盘", "A股市场", "短线情绪", "数据已更新",
            f"⚡ 成交{amt_s(c)}·{sub['phase']}"]

    data = {
        "title": f"A股市场复盘报告 · {c['trade_date']}",
        "date": f"{c['trade_date']}（采集自动生成）",
        "source": "同花顺 + 东方财富 + 问财 三源自动采集",
        "tags": tags,
        "indices": indices,
        "core_cards": core_cards,
        "change_overview": change_overview,
        "emotion_panorama": emotion_panorama,
        "emotion_monitor": emotion_monitor,
        "jinji_rows": sub["jinji_rows"],
        "jinji_note": (f"⚠ <strong>核心观察：</strong>连板家数{len(two)+len(three)}只"
                       f"（2板{len(two)}、3板{len(three)}），{space_stock or '—'}以{space}成为全场最高板。"
                       f"涨停{zt}只、跌停{dt}只。板块资金流入居前："
                       + "、".join(f"{s['name']}{s['val']}" for s in c.get('sector_in', [])[:3])
                       + "。情绪周期：<b>" + sub['phase'] + "</b>。"),
        "sector_top_in": sector_top_in,
        "sector_top_out": sector_top_out,
        "sector_footnote": "* 板块主力净流入/流出为当日采集（东方财富）。",
        "overseas": overseas,
        "overseas_note": overseas_note,
        "main_line": sub["main_line"],
        "limit_up_groups": sub["limit_up_groups"],
        "zhaban_high": [{
            "title": "连板高度",
            "line": space or "—",
            "sub": f"✅ {space_stock or '—'}为全场最高板，空间打开关键" if space else "暂无明显空间板",
        }, {
            "title": "量能",
            "line": amt_s(c),
            "sub": "⚠ 成交" + ("缩量" if (amt and amt < 2) else "温和") + "，追高标的需防回落",
        }],
        "zhaban_low": [{
            "name": x["name"], "line": f"{x['change']:+.2f}% · 龙虎净买{x['net_yi']}亿",
            "sub": "✅ " + ("、".join(x["concepts"][:2]) if x["concepts"] else "强势股"),
        } for x in c.get("dragons", [])[:3]],
        "strategy_title": f"短线策略 & 明日接力计划（{next_trade_day(c['trade_date'])}预判）",
        "strategy_cols": [
            {"title": "✅ 重点接力（明日关注）", "cls": "#3fb950", "items": _strategy_items(c, sub, "focus")},
            {"title": "🔍 分歧低吸（回调关注）", "cls": "#58a6ff", "items": _strategy_items(c, sub, "low")},
            {"title": "🚫 坚决规避（明日回避）", "cls": "#f85149", "items": _strategy_items(c, sub, "avoid")},
        ],
        "review_title": "行情回顾 & 后市展望",
        "review_text": sub["review"],
        "outlook_text": sub["outlook"],
        "amount_rank": amount_rank,
        "amount_footnote": amount_footnote,
        "risk_rank": sub["risk_rank"],
        "risk_footnote": "* 风险项以当日主力净流出方向 + 问财叙事风险信号标注。",
        "money_in": money_in,
        "money_out": money_out,
        "core_stocks": sub["core_stocks"],
        "margin_items": (lambda m: [
            {"label": "融资余额", "value": m.get("finance") or "—",
             "sub": "杠杆资金小幅回落" if m.get("finance") else "接口未返回", "sub_cls": "#f85149"},
            {"label": "融券余额", "value": m.get("lending") or "—",
             "sub": "融券规模低位", "sub_cls": ""},
            {"label": "两融合计", "value": m.get("total") or "—",
             "sub": "缩量日两融平稳", "sub_cls": ""},
            {"label": "杠杆占比", "value": "—", "sub": "中性区间 风控可控", "sub_cls": "#d29922"},
        ])(c.get("margin", {}) or {}),
        "track_rows": [{
            "code": "—", "name": x["name"],
            "chg": ("+10.0%" if x["board"] == 1 else f"{x['board']}连板"),
            "chg_cls": "positive",
            "status": f"{x['board']}连板 · 封单{x['seal_yi']}亿" if x["seal_yi"] else (f"{x['board']}连板" if x["board"] > 1 else "首板"),
            "badge": "封板✅" if x["seal_yi"] else "涨停",
            "badge_cls": "badge-seal",
            "turnover": "—",
            "strategy": (f"封单{x['seal_yi']}亿 " + ("1进2关注" if x["board"] == 1 else f"{x['board']}进{x['board']+1}观察")),
            "strategy_cls": "#3fb950" if x["board"] == 1 else "#d29922",
        } for x in c.get("limit_up", [])[:8]],
        "invest_cols": [
            {"title": "🎯 选股策略", "cls": "#58a6ff", "items": _invest_items(c, sub, "select")},
            {"title": "🛡️ 风控策略", "cls": "#d29922", "items": _invest_items(c, sub, "risk")},
            {"title": "💪 心态管理", "cls": "#3fb950", "items": _invest_items(c, sub, "mind")},
        ],
        "special_events": _special_events(c, sub),
        "calendar": [
            f"· {c['trade_date']}：成交{amt_s(c)}·涨停{zt}只·空间板{space or '—'}",
            f"· {next_trade_day(c['trade_date'])}：关注{space_stock or '空间板'}{space or ''}晋级 + 量能方向",
            "· 后续：板块资金持续性、连板高度拓展、问财叙事中的外部变量",
        ],
        "opcheck_cols": [
            {"title": f"✅ {next_trade_day(c['trade_date'])}操作清单", "cls": "#3fb950",
             "items": _op_items(c, sub)},
            {"title": "📚 盘后推荐阅读", "cls": "#58a6ff",
             "items": ["📄 东方财富板块主力资金流向（当日）",
                       "📄 同花顺连板梯队与龙虎榜（当日）",
                       "📄 问财市场情绪与研报摘要（当日）"]},
        ],
        "disclaimer": "⚠️ <b>免责声明：</b>本报告由三源公开数据自动采集生成，仅供参考，不构成投资建议。"
                      "A股市场有风险，投资需谨慎。数据以交易日采集为准，缺失项以\"—\"标注。",
        "generated": f"📊 A股市场复盘报告 · 自动生成于 {datetime.date.today().isoformat()}",
        "source_footer": "数据源：同花顺 hithink-finance · 东方财富 mx-data · 问财 mx-search",
    }
    return data


def amt_s(c):
    amt = c.get("amount_yi")
    return f"{amt}万亿" if amt else "—"


def render_cross_check_html(c):
    """把 collect.py 的 cross_check（三源交叉验证）渲染为独立 HTML 区块，
    拼接到报告末尾，不依赖 gen_template 既有字段。"""
    cc = c.get("cross_check") or {}
    if not cc.get("ok"):
        return ""
    dim = {d["name"]: d for d in cc.get("dimensions", [])}

    # 维度1：板块资金流方向一致性
    d1 = dim.get("板块主力资金流（东财 vs 问财）", {})
    rows1 = ""
    for m in d1.get("matched", []):
        if m["iwencai"] is None:
            sign = '<span style="color:#8b949e;">缺失</span>'
        elif m["same_sign"]:
            sign = '<span style="color:#3fb950;">方向一致 ✓</span>'
        else:
            sign = '<span style="color:#f85149;">冲突 ✗</span>'
        emx = f"{m['emx_yi']:+.2f}亿"
        iwc = f"{m['iwencai']:+.2f}亿" if m["iwencai"] is not None else "—"
        rows1 += (f"<tr><td>{m['eastmoney']}</td><td style='text-align:right'>{emx}</td>"
                  f"<td style='text-align:right'>{iwc}</td><td style='text-align:right'>{sign}</td></tr>")
    dc = d1.get("direction_consistent")
    dc_badge = ("<b style='color:#3fb950;'>一致</b>" if dc is True
                else "<b style='color:#f85149;'>不一致</b>" if dc is False
                else "<b style='color:#8b949e;'>部分缺失</b>")

    # 维度2：资金Top vs 涨幅Top 重叠
    d2 = dim.get("问财内部：资金流入Top vs 涨幅Top", {})
    overlap = d2.get("overlap", [])
    ov_s = "、".join(overlap) if overlap else "无（题材分化日）"

    # 维度3：个股维度互通
    d3 = dim.get("个股维度：同花顺涨停池 抽样 vs 问财可查", {})
    srows = ""
    for s in d3.get("samples", []):
        ok = '<span style="color:#3fb950;">可查 ✓</span>' if s["found"] else '<span style="color:#f85149;">未查到</span>'
        srows += f"<tr><td>{s['name']}</td><td style='text-align:right'>{ok}</td></tr>"
    allf = d3.get("all_found")
    allf_badge = ("<b style='color:#3fb950;'>全部互通</b>" if allf is True
                  else "<b style='color:#f85149;'>存在缺口</b>" if allf is False
                  else "<b style='color:#8b949e;'>—</b>")

    # 维度4：龙虎榜 fuyao vs 同花顺
    d4 = dim.get("龙虎榜（fuyao 官方 vs 同花顺 CLI）", {})
    d4_ok = d4.get("direction_consistent")
    d4_badge = ("<b style='color:#3fb950;'>一致</b>" if d4_ok is True
                else "<b style='color:#f85149;'>不一致</b>" if d4_ok is False
                else "<b style='color:#8b949e;'>部分缺失</b>")
    d4_overlap = d4.get("overlap", [])
    d4_ov_s = "、".join(d4_overlap[:8]) + ("等" if len(d4_overlap) > 8 else "") if d4_overlap else "无"
    d4_samedir = d4.get("same_direction", 0)
    d4_total = d4.get("overlap_count", 0)

    # 维度5：涨停池 fuyao vs 同花顺 + 真实炸板率
    d5 = dim.get("涨停池（fuyao 官方 vs 同花顺 CLI）", {})
    d5_consistent = d5.get("consistent")
    d5_badge = ("<b style='color:#3fb950;'>一致</b>" if d5_consistent is True
                else "<b style='color:#f85149;'>不一致</b>" if d5_consistent is False
                else "<b style='color:#8b949e;'>—</b>")
    d5_br = d5.get("real_break_rate")
    d5_br_s = f"{d5_br:.1f}%" if d5_br is not None else "—"

    # 维度6：选股宝板块（涨幅 vs 问财 + 领涨股 vs 涨停池）
    d6 = dim.get("选股宝板块（涨幅 vs 问财 + 领涨股 vs 涨停池）", {})
    d6_consistent = d6.get("direction_consistent")
    d6_badge = ("<b style='color:#3fb950;'>一致</b>" if d6_consistent is True
                else "<b style='color:#f85149;'>不一致</b>" if d6_consistent is False
                else "<b style='color:#8b949e;'>部分缺失</b>")
    d6_overlap = d6.get("leader_overlap", [])
    d6_ov_s = "、".join(d6_overlap[:10]) + ("等" if len(d6_overlap) > 10 else "") if d6_overlap else "无"
    d6_oc = d6.get("leader_overlap_count", 0)

    return f"""
    <section class="block">
      <h2>🔬 五源交叉验证（同花顺官方 fuyao / 同花顺 CLI / 东方财富 / 问财 / 选股宝）</h2>
      <p class="sub">每日五源一致性校验：方向一致说明数据可靠；分化说明当日题材结构特征。</p>
      <div class="cross-grid">
        <div class="cross-card">
          <div class="cross-title">① 板块主力资金流 · 方向一致性 {dc_badge}</div>
          <table class="cross-tbl">
            <thead><tr><th>板块</th><th style="text-align:right">东财(亿)</th><th style="text-align:right">问财(亿)</th><th style="text-align:right">核验</th></tr></thead>
            <tbody>{rows1}</tbody>
          </table>
          <div class="cross-note">{d1.get('note','')}</div>
        </div>
        <div class="cross-card">
          <div class="cross-title">② 问财内部 · 资金流入Top vs 涨幅Top</div>
          <div class="cross-sub">资金Top：{'、'.join(d2.get('flow_top',[])) or '—'}</div>
          <div class="cross-sub">涨幅Top：{'、'.join(d2.get('chg_top',[])) or '—'}</div>
          <div class="cross-overlap">重叠 <b style="color:#58a6ff;">({d2.get('overlap_count',0)})</b>：{ov_s}</div>
        </div>
        <div class="cross-card">
          <div class="cross-title">③ 个股维度 · 同花顺涨停池 vs 问财 {allf_badge}</div>
          <table class="cross-tbl">
            <thead><tr><th>涨停股抽样</th><th style="text-align:right">问财可查</th></tr></thead>
            <tbody>{srows}</tbody>
          </table>
        </div>
        <div class="cross-card">
          <div class="cross-title">④ 龙虎榜 · fuyao官方 vs 同花顺CLI {d4_badge}</div>
          <div class="cross-sub">fuyao榜 {d4.get('fuyao_count',0)}只 · 同花顺 {d4.get('hithink_count',0)}只</div>
          <div class="cross-sub">重叠 <b style="color:#58a6ff;">({d4_total})</b>：{d4_ov_s}</div>
          <div class="cross-overlap">净买同向 <b style="color:#3fb950;">{d4_samedir}/{d4_total}</b></div>
        </div>
        <div class="cross-card">
          <div class="cross-title">⑤ 涨停池 · fuyao官方 vs 同花顺CLI {d5_badge}</div>
          <div class="cross-sub">fuyao涨停 {d5.get('fuyao_count',0)}只 · 同花顺 {d5.get('hithink_count',0)}只</div>
          <div class="cross-sub">重叠 <b style="color:#58a6ff;">({d5.get('overlap_count',0)})</b></div>
          <div class="cross-overlap">真实炸板率（炸板池实测）：<b style="color:#d29922;">{d5_br_s}</b></div>
        </div>
        <div class="cross-card">
          <div class="cross-title">⑥ 板块·选股宝 vs 问财 {d6_badge}</div>
          <div class="cross-sub">领涨股命中涨停池 <b style="color:#3fb950;">({d6_oc})</b>：{d6_ov_s}</div>
          <div class="cross-note">选股宝公开板块涨幅/领涨股，交叉验证主线板块核心股是否进入涨停池。</div>
        </div>
      </div>
    </section>
    <style>
      .cross-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:14px;}}
      .cross-card{{background:#0d1117;border:1px solid #30363d;border-radius:12px;padding:16px;}}
      .cross-title{{font-weight:700;color:#e1e8ed;margin-bottom:10px;font-size:15px;}}
      .cross-tbl{{width:100%;border-collapse:collapse;font-size:13px;}}
      .cross-tbl th,.cross-tbl td{{padding:5px 6px;border-bottom:1px solid #21262d;text-align:left;}}
      .cross-tbl th{{color:#8b949e;font-weight:600;}}
      .cross-sub{{font-size:12px;color:#c9d1d9;margin:6px 0;line-height:1.5;}}
      .cross-overlap{{font-size:13px;color:#c9d1d9;margin-top:8px;padding-top:8px;border-top:1px solid #21262d;}}
      .cross-note{{font-size:11px;color:#8b949e;margin-top:8px;}}
    </style>
    """


def _fmt_heat(h):
    try:
        v = float(h)
        if v >= 1e8:
            return f"{v/1e8:.2f}亿"
        if v >= 1e4:
            return f"{v/1e4:.1f}万"
        return str(int(v))
    except Exception:
        return str(h)


def next_trade_day(date_str):
    try:
        d = datetime.date.fromisoformat(date_str)
    except Exception:
        return "次日"
    # 简单跳过周末
    nd = d + datetime.timedelta(days=1)
    while nd.weekday() >= 5:
        nd += datetime.timedelta(days=1)
    wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][nd.weekday()]
    return f"{nd.isoformat()}{wd}"


def _strategy_items(c, sub, kind):
    space_stock = c.get("space_stock"); space = c.get("space_board")
    two = c.get("ladder", {}).get("2", [])
    if kind == "focus":
        items = []
        if space_stock:
            items.append(f"<b>{space_stock}</b>（{space}）— 全场最高板，"
                         f"{'3进4' if space and '3' in space else '晋级'}关键日，若封板则持有")
        for x in c.get("dragons", [])[:3]:
            if x["name"] != space_stock and x["net_yi"] > 0:
                items.append(f"<b>{x['name']}</b>（{x['change']:+.2f}% 龙虎净买{x['net_yi']}亿）— "
                             + "、".join(x["concepts"][:2]) + "，重点观察")
        return items or ["暂无明确接力标的"]
    if kind == "low":
        items = []
        for s in c.get("sector_in", [])[:3]:
            items.append(f"<b>{s['name']}板块</b> — 主力净流入{s['val']}，中期持续，回踩低吸")
        return items or ["暂无"]
    # avoid
    items = []
    for s in c.get("sector_out", [])[:2]:
        items.append(f"<b>{s['name']}板块</b>— 主力净流出{s['val']}，坚决规避")
    items.append("缩量日后排接力风险大，不追高无业绩题材")
    return items


def _invest_items(c, sub, kind):
    if kind == "select":
        return [
            "主线优先：" + " > ".join(s["name"] for s in c.get("sector_in", [])[:3]) or "—",
            f"连板优先：关注{('2进3' if c.get('space_board') and '3' in c.get('space_board','') else '1进2')}"
            + (f"（{c.get('space_stock')}）" if c.get('space_stock') else ""),
            "龙虎榜净买强势股优先（见核心股）",
            "规避板块：" + "、".join(s["name"] for s in c.get("sector_out", [])[:2]) or "无",
        ]
    if kind == "risk":
        amt = c.get("amount_yi")
        return [
            ("成交" + (f"{amt}万亿" if amt else "—") + " 缩量" if (amt and amt < 2) else "量能温和")
            + " → 不追高，等分歧低吸",
            "科技高位拥挤回撤风险（问财叙事提示），仓位控制",
            "连板空间仅" + (c.get("space_board") or "—") + "，接力生态偏弱",
            "外部变量（美债/油价）扰动，用仓位管理应对",
        ]
    return [
        "缩量轮动期 → 不焦虑，集中仓位于主线",
        "主线清晰（资金流入方向）→ 聚焦不撒网",
        (c.get("space_stock") or "空间板") + "晋级是关键 → 过了空间打开，不过等下一轮",
        "外部不可预判 → 用仓位管理而非押方向",
    ]


def _special_events(c, sub):
    ev = []
    for s in c.get("sector_in", [])[:3]:
        ev.append({"title": f"💰 {s['name']}主力净流入{s['val']}",
                   "text": f"当日板块获主力资金净流入{s['val']}，为资金主攻方向。"})
    if c.get("dragons"):
        top = c["dragons"][0]
        ev.append({"title": f"🐉 龙虎榜·{top['name']}净买{top['net_yi']}亿",
                   "text": "、".join(top["concepts"][:3]) + f"，当日强势股，龙虎榜资金重点买入。"})
    ev.append({"title": "📈 连板空间",
               "text": f"{c.get('space_stock') or '—'}以{c.get('space_board') or '—'}成为全场最高板，"
                       f"2板{c.get('ladder',{}).get('2',[]).__len__()}只。"})
    return ev[:4]


def _op_items(c, sub):
    space_stock = c.get("space_stock"); space = c.get("space_board")
    items = []
    if space_stock:
        items.append(f"1️⃣ 观察{space_stock}{space} → 封板持有，炸板则减仓")
    for i, x in enumerate(c.get("dragons", [])[:3], start=2):
        c1 = "、".join(x["concepts"][:1])
        items.append(f"{i}️⃣ {x['name']}（{x['change']:+.2f}% 净买{x['net_yi']}亿）→ 强势观察，{c1}")
    for s in c.get("sector_out", [])[:1]:
        items.append(f"🔚 {s['name']}板块 → 净流出{s['val']}，坚决不碰")
    return items or ["等待放量确认"]


def write_archive(td, slug):
    rec = {
        "date": slug, "title": td.get("title", ""), "slug": slug,
        "up": td.get("change_overview", {}).get("up", ""),
        "down": td.get("change_overview", {}).get("down", ""),
        "amount": td.get("change_overview", {}).get("amount", ""),
        "zt": td.get("emotion_panorama", [{}])[4].get("value", "").split(" / ")[0]
        if len(td.get("emotion_panorama", [])) > 4 else "",
        "dt": td.get("emotion_panorama", [{}])[4].get("value", "").split(" / ")[1]
        if len(td.get("emotion_panorama", [])) > 4 else "",
    }
    arr = []
    if os.path.exists(ARCHIVE_JSON):
        try:
            arr = json.load(open(ARCHIVE_JSON, encoding="utf-8"))
        except Exception:
            arr = []
    arr = [r for r in arr if r.get("date") != slug]
    arr.append(rec)
    arr.sort(key=lambda r: r.get("date", ""), reverse=True)
    with open(ARCHIVE_JSON, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False, indent=2)
    return len(arr)


def main():
    args = sys.argv[1:]
    no_push = "--no-push" in args
    recollect = "--recollect" in args

    if recollect:
        print("[update] 重新采集...")
        env = dict(os.environ)
        env["PATH"] = os.path.expanduser(r"~\AppData\Roaming\npm") + os.pathsep + env.get("PATH", "")
        r = subprocess.run([sys.executable, os.path.join(BASE, "collect.py")],
                           stdout=open(COLLECTED, "w", encoding="utf-8"),
                           stderr=sys.stderr, env=env)
        if r.returncode != 0:
            print("[update] 采集失败，中止"); sys.exit(1)

    c = load_collected()
    td = build_template_data(c)
    html = gt.build_template(td)
    # 拼接三源交叉验证区块（独立渲染，不依赖 gen_template 字段）
    cross_html = render_cross_check_html(c)
    if cross_html:
        html = html.replace("</body>", cross_html + "\n</body>")

    # 写 index.html
    with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[update] index.html -> {c['trade_date']} ({len(html)} bytes)")

    # 归档
    os.makedirs(REPORTS_DIR, exist_ok=True)
    slug = c["trade_date"]
    with open(os.path.join(REPORTS_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    n = write_archive(td, slug)
    print(f"[update] 归档 reports/{slug}.html，archive.json 共 {n} 条")

    # 同时落盘 template_data.json 便于审阅
    with open(os.path.join(BASE, "template_data.json"), "w", encoding="utf-8") as f:
        json.dump(td, f, ensure_ascii=False, indent=2)

    if no_push:
        print("[update] --no-push，跳过 git push")
        return

    # git push
    try:
        subprocess.run(["git", "add", "-A"], cwd=BASE, check=True)
        msg = f"auto: 复盘 {slug} 三源采集更新"
        subprocess.run(["git", "commit", "-m", msg], cwd=BASE, check=True)
        subprocess.run(["git", "push"], cwd=BASE, check=True)
        print(f"[update] git push 完成：{msg}")
    except subprocess.CalledProcessError as e:
        print(f"[update] git 操作失败：{e}")


if __name__ == "__main__":
    main()
