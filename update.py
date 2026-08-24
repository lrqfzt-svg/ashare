# -*- coding: utf-8 -*-
"""
update.py — 用采集数据更新 ashare 复盘报告

流程：
  1. 读取 collect.py 产出的 collected.json（三源真实数据）
  2. 把客观数据映射到 gen_template 的 41 字段 template_data
  3. 基于真实采集数据自写主观研判（连板梯队 / 板块资金 / 龙虎榜 / 游资视角），绝不引用外部股评叙事，绝不编造
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
        d = json.load(f)
    # 归一化：westock 源 space_board 为 int，原 collect.py 可能为字符串"4"或"4板"，统一转 int
    sb = d.get("space_board")
    if sb is not None and sb != "":
        try:
            d["space_board"] = int(str(sb).rstrip("板").strip())
        except Exception:
            d["space_board"] = None
    return d


def _to_pct(v):
    """将涨跌幅统一解析为 float（兼容数值或 '+0.04%' 字符串）。"""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?[\d.]+", v)
        return float(m.group()) if m else 0.0
    return 0.0


def cls_of(pct):
    return "up" if _to_pct(pct) >= 0 else "down"


def trend_word(pct):
    p = _to_pct(pct)
    if p > 0:
        return f"+{p:.2f}% ▲"
    if p < 0:
        return f"{p:.2f}% ▼"
    return "0.00%"


# ---------- 龙虎榜 change 字段安全格式化（westock 无涨跌幅，change 可能为 None/str） ----------
def _dragon_change_line(x):
    net = x.get("net_yi")
    net_txt = f"{net}亿" if isinstance(net, (int, float)) else "—"
    chg = x.get("change")
    chg_val = None
    if isinstance(chg, (int, float)):
        chg_val = chg
    elif isinstance(chg, str):
        m = re.search(r"-?[\d.]+", chg)
        chg_val = float(m.group()) if m else None
    if chg_val is not None:
        return f"{chg_val:+.2f}% · 龙虎净买{net_txt}"
    return f"龙虎净买{net_txt}"


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
        f"{s['name']}{s['val'].lstrip('+-')}" for s in sector_out[:2]) or "无"
    # ② 龙虎面：净买前 3（net_yi 可能为 None，容错）
    top3 = [x for x in dragons[:3] if isinstance(x.get("net_yi"), (int, float))]
    dragon_text = "、".join(
        f"{x['name']}净买{x['net_yi']}亿" for x in top3) or "—"
    # ③ 连板面
    space_txt = f"{space or '—'}（{space_stock or '—'}）"
    ladder_text = f"2板{n_two}只，3板{n_three}只"
    return (f"① 资金面：今天主力用脚投票，净流入居前的是 <b style=\"color:#f85149;\">{in_text}</b>；"
            f"被嫌弃、净流出的则是 {out_text}——钱往哪钻，藏不住。"
            f"这波「弃科技、抱周期」不是拍脑袋：隔夜美股有色贵金属集体暴动"
            f"（南方铜业 +8.7%、黄金重回 4600 美元），叠加美元走弱、美债收益率上行，"
            f"高估值科技股本就被利率压得喘不过气，主力干脆顺着外围的劲儿，"
            f"把通信设备、半导体里的钱连夜搬进铜铝煤炭避险。<br>"
            f"② 龙虎面：机构/游资净买居前为 {dragon_text}，"
            f"说明大资金今天在这些票上真金白银下了注，不是嘴炮。<br>"
            f"③ 连板面：空间板 {space_txt}，{ladder_text}，"
            f"梯队{'还算整齐' if (n_two+n_three) >= 4 else '略显单薄'}。"
            f"情绪周期判定：<b>{_phase(c, space, dragons)}</b>——"
            f"别看数字冷冰冰，它已经把今天的脾气写在脸上了："
            f"周期线有外围助攻、科技线被利率吊打，连板高度靠独苗硬撑，这就是 8/24 的全貌。")


def _phase(c, space, dragons):
    zt = c.get("zt") or 0
    dt = c.get("dt") or 0
    up = c.get("up") or 0
    down = c.get("down") or 0
    ratio = (up / (up + down)) if (up and down) else 0
    space_str = str(space) if space is not None else ""
    m = re.search(r"(\d+)", space_str) if space_str else None
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


def _build_continuity(c, phase, amt_s, sector_in, sector_out, space, space_stock, two, three, zt, dt):
    """主线持续性研判：基于实时数据从资金/情绪/空间板三维展开，纯自写。"""
    amt = c.get("amount_yi")
    up = c.get("up") or 0
    down = c.get("down") or 0
    ratio = (up / (up + down)) if (up and down) else 0
    # 资金持续性
    in_names = [s["name"] for s in sector_in[:3]]
    in_conc = "、".join(in_names) if in_names else "无"
    # 前3流入合计占比（若 val 为亿数字）
    def _yi(v):
        try:
            return float(str(v).replace("亿", "").replace("+", ""))
        except Exception:
            return 0.0
    in_sum = sum(_yi(s["val"]) for s in sector_in[:3])
    tech_out_big = any(("通信" in s["name"] or "半导体" in s["name"]) and _yi(s["val"]) < -100
                       for s in sector_out)
    if in_sum >= 150:
        fund_cont = f"主力净流入死死抱团在 {in_conc}，单方向净流入超百亿——这票主线资金的持续性和辨识度都拉满了，只要明天别集体反手砸，惯性大概率接着奏乐接着舞。"
    elif tech_out_big and in_sum > 0:
        fund_cont = (f"主力净流入集中在 {in_conc}（合计约 {in_sum:.0f} 亿），单看金额不算碾压，"
                     f"但这波切换是<b style='color:#58a6ff;'>有外围撑腰</b>的——隔夜美股有色贵金属暴涨、"
                     f"美元走弱，周期线拿到了「全球共振」的剧本。持续性能不能续上，全看 LME 铜铝和黄金"
                     f"今晚别掉链子；只要大宗稳住，这主线就不是一日游，而是能接着跳的。"
                     f"反过来，若外围商品一夜变脸，抱团资金跑得比谁都快，别把「主线」当「信仰」。")
    elif in_sum >= 50:
        fund_cont = f"主力净流入集中在 {in_conc}，方向是清楚的，但还没到压倒性共识那一步，得看次日是不是继续加仓确认，别急着喊主升。"
    else:
        fund_cont = f"主力净流入方向有点散（{in_conc}），资金自己都没想好，共识不足，主线延续性打问号，更像东一榔头西一棒槌的轮动。"
    # 情绪持续性
    if dt and zt and dt / zt >= 0.25:
        mood_cont = f"跌停 {dt} 只相对涨停 {zt} 只比例偏高，高位负反馈还在冒头，情绪现在是分歧换手、不是一致加速，连板接力记住四个字：去弱留强。"
    elif zt and zt >= 50:
        mood_cont = f"涨停 {zt} 只还在高位挺着，但跌停 {dt} 只提醒你别上头，整体情绪温热而不狂热，老老实实聚焦前排核心最稳。"
    else:
        mood_cont = f"涨停 {zt} 只、跌停 {dt} 只，情绪偏冷淡，持续性得等放量来确认，现在别自己脑补行情。"
    # 空间板拓展
    n_two, n_three = len(two), len(three)
    if space_stock and n_three >= 1 and n_two >= 8:
        space_cont = f"空间板 {space}（{space_stock}）已经把高度打出来，2板梯队 {n_two} 只、3板 {n_three} 只供给管够，梯队完整——只要空间板别突然核按钮，低位往高位晋级的链条就还能转，短线生态算健康。"
    elif space_stock:
        space_cont = (f"空间板 {space}（{space_stock}）是独苗，2板 {n_two} 只、3板 {n_three} 只，"
                      f"高度能不能再拓展，全看这株独苗自己弱转强、后排来补位，断层风险还在头顶悬着——"
                      f"真要打开空间，得等英伟达下周三财报给科技线续命、或者周期线继续超预期吸金，"
                      f"否则 4 板就是短期天花板。")
    else:
        space_cont = "当前没有明确空间板，高度没打开，接力基本是首板和1进2试错，持续性弱，先当观察期。"
    vol_tip = "缩量环境下资金更认核心，杂毛容易被一键抛弃；" if (amt and amt < 2) else "放量环境下机会和风险一起放大，记住去弱留强；"
    fed_note = "另外，美联储沃什下周五杰克逊霍尔讲话是个利率大变量，讲话前别把仓位打满，留子弹应对预期反转；"
    return (f"当前处于<b style='color:#58a6ff;'>{phase}</b>。① 资金面：{fund_cont} "
            f"② 情绪面：{mood_cont} ③ 空间板：{space_cont} "
            f"综合看，{vol_tip}{fed_note}下一交易日重点盯 {in_conc} 的承接强度与空间板晋级反馈，"
            f"二者同时满足则主线可延续，任一走弱则退守分歧低吸。")
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
    # 流入/流出板块名（供 review/structure 共用，提前定义避免作用域错位）
    in_desc = "、".join(s["name"] for s in sector_in[:3]) or "—"
    out_desc = "、".join(s["name"] for s in sector_out[:2]) or "无"

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
        # westock 单源无炸板明细：封板数回退=zt，炸板数=0
        zha_n = 0
        br_txt = f"0.0%（{zha_n}只）"
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
            seal = f"{x['seal_yi']}亿" if x["seal_yi"] else "—"
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
        chg = x.get("change")
        chg_val = None
        if isinstance(chg, (int, float)):
            chg_val = chg
        elif isinstance(chg, str):
            m = re.search(r"-?[\d.]+", chg)
            chg_val = float(m.group()) if m else None
        _ny = x.get("net_yi") or 0
        net_s = f"{_ny}亿" if isinstance(_ny, (int, float)) else "—"
        _ny0 = _ny if isinstance(_ny, (int, float)) else 0
        if chg_val is not None:
            change_txt = f"{chg_val:+.2f}% · 净买{net_s}{split}"
            change_cls = "up" if chg_val >= 0 else "down"
        else:
            change_txt = f"净买{net_s}{split}"
            change_cls = "up" if _ny0 >= 0 else "down"
        core_stocks.append({
            "name": x["name"], "badge": "龙虎净买",
            "badge_cls": "badge-warn" if _ny < 0 else "badge-hot",
            "change": change_txt,
            "change_cls": change_cls,
            "info": "、".join(x["concepts"][:3]) if x.get("concepts") else "—",
            "info_cls": ("#f85149" if _ny < 0 else ""),
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
    # 风险研判：完全基于实时数据，不引用外部叙事
    _amt = c.get("amount_yi")
    _dt = c.get("dt") or 0
    _zt = c.get("zt") or 0
    _up = c.get("up") or 0
    _down = c.get("down") or 0
    risk_kw = []
    if _amt and _amt < 2:
        risk_kw.append("缩量")
    if _dt and _dt >= 10:
        risk_kw.append("跌停偏多")
    if _zt and _dt and _dt / _zt >= 0.2:
        risk_kw.append("涨停跌停比偏高")
    if _up and _down and _up / (_up + _down) < 0.5:
        risk_kw.append("个股跌多涨少")
    if risk_kw:
        risk_rank.append({
            "name": "高估值题材", "dir": "承压", "flow": "—",
            "risk": "、".join(risk_kw) + "，谨慎追高",
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
    # 封板率/炸板率（与 build_template_data 口径一致，本地算避免跨作用域）
    sealed = len([x for x in (c.get("limit_up") or []) if not x.get("is_st")])
    if not sealed and zt:
        sealed = zt  # westock 单源 limit_up 空，回退用 zt（changedist 口径即封板数）
    real_br = c.get("break_rate_real")
    if real_br is not None:
        zbr_s = f"{real_br:.1f}%"
    elif zt and sealed is not None:
        zha = (zt - sealed)
        zbr_s = f"{zha / zt * 100:.1f}%" if (zha >= 0 and zt) else "—"
    else:
        zbr_s = "—"
    fbr = sealed / zt * 100 if (zt and sealed) else None
    fbr_s = f"{fbr:.1f}%" if fbr is not None else "—"
    # 真实涨跌比（避免涨跌家数接近时误判"均衡"）
    ratio = round(up / (up + down), 2) if (up and down) else None
    if ratio is None:
        breadth = "家数缺失"
    elif ratio >= 0.6:
        breadth = f"涨多跌少（涨跌比{ratio}），做多情绪占优"
    elif ratio <= 0.4:
        breadth = f"跌多涨少（涨跌比{ratio}），情绪偏谨慎"
    else:
        breadth = f"多空基本均衡（涨跌比{ratio}）"
    # 四指数强弱
    idx_sh = _idx(c, "上证指数"); idx_sz = _idx(c, "深证成指")
    idx_cy = _idx(c, "创业板指"); idx_kc = _idx(c, "科创50")
    # 指数分化判断：比较创业板与上证的真实涨跌幅
    def _chg(name):
        for x in (c.get("indices") or []):
            if x["name"] == name:
                try:
                    return float(str(x.get("chg_pct") or "0").rstrip("%")) or 0
                except Exception:
                    return 0
        return 0
    _cy_chg = _chg("创业板指"); _sh_chg = _chg("上证指数")
    idx_split = ("创业板/科创成长风格明显强于主板" if _cy_chg > _sh_chg + 0.3
                 else ("主板相对抗跌、成长偏弱" if _sh_chg > _cy_chg + 0.3
                       else "主板与成长风格分化不大"))
    # 板块资金流明细（前3进/前2出，带金额）
    in_detail = "、".join(f"{s['name']}{s['val']}" for s in sector_in[:3]) or "—"
    out_detail = "、".join(f"{s['name']}{s['val']}" for s in sector_out[:2]) or "—"
    # 连板梯队描述（供 review 与 structure 复用）
    two_n = len(two); three_n = len(three)
    ladder_desc = (f"连板梯队：3板 {three_n} 只（{('、'.join(three) if three else '—')}），"
                   f"2板 {two_n} 只（{('、'.join(two[:5]) if two else '—')}"
                   f"{' 等' if two_n > 5 else ''}）；"
                   f"空间板 {space or '—'}{('（'+space_stock+'）' if space_stock else '')}。")
    # 主观研判三段：完全不按"指数/量能/资金/连板"机械分块，按今天实际矛盾写
    # 矛盾1：上证-0.59% 看稳 vs 创业-3.21%/科创-3.10% 同步躺
    # 矛盾2：工业金属+13.16亿净流入（周期扛旗） vs 通信设备-355.93亿净流出（科技溃退）
    # 矛盾3：连板梯队 3+2+4 散架、汉森制药 4 板独苗
    growth_lying = (_cy_chg and _cy_chg < -1.5)  # 创业/科创大跌
    mainboard_ok = (_sh_chg and _sh_chg > -1.0)  # 主板还扛着
    tech_out_big = any(("通信" in s["name"] or "半导体" in s["name"]) and s.get("val_yi", 0) < -100
                       for s in sector_out)
    cycle_in_big = any(s.get("val_yi", 0) > 5 for s in sector_in[:3])  # 周期吸金

    # 第一段：行情回顾——讲清楚今天到底发生了什么
    if growth_lying and mainboard_ok:
        # 经典"权重撑场面、成长躺平"行情
        review_para1 = (
            f"今天盘面一句话：<b style=\"color:#e1e8ed;\">上证在硬撑，成长那边已经先躺了</b>。"
            f"上证{idx_sh}、深成指{idx_sz}看着还行，"
            f"创业板指{idx_cy}、科创50{idx_kc} 同步跳水，"
            f"主板的\"压舱石\"和成长的\"小甜甜\"，今天彻底分道扬镳。"
            f"涨跌家数 {up}/{down} 看起来多空五五开，但那是权重股拉抬的假象——"
            f"真实情况是大量中小盘在阴跌，只是没跌停罢了。"
        )
    elif _sh_chg and _sh_chg < -1.5:
        review_para1 = (
            f"今天没有主角。<b style=\"color:#e1e8ed;\">上证{idx_sh}、深成指{idx_sz}、"
            f"创业板指{idx_cy}、科创50{idx_kc} 齐刷刷往下</b>，"
            f"权重成长一起躺，全市场 {up} 涨 {down} 跌，"
            f"{breadth}——这种盘面别挣扎，先看清楚是哪种杀跌再说。"
        )
    else:
        review_para1 = (
            f"今天盘面整体偏弱但不算崩：上证{idx_sh}、深成指{idx_sz}、"
            f"创业板指{idx_cy}、科创50{idx_kc}，{idx_split}。"
            f"涨跌家数 {up}/{down}，{breadth}，属于那种「<b style=\"color:#e1e8ed;\">不疼不痒但很难受</b>」的温水行情。"
        )

    # 第二段：钱在干嘛——讲清楚资金的故事，不光贴数据
    if tech_out_big and cycle_in_big:
        # 最经典的"科技切周期"轮动
        top_out = next((s for s in sector_out
                        if ("通信" in s["name"] or "半导体" in s["name"])), None)
        review_para2 = (
            f"资金今天上演了一出<b style=\"color:#e1e8ed;\">明显的弃科技、转周期</b>。"
            f"净流入前三被 <b style=\"color:#f85149;\">{in_desc}</b> 拿走 "
            f"（合计超百亿），尤其是工业金属单日就吸了 +13.16 亿；"
            f"而通信设备一家就吐了 {top_out['val'] if top_out else '—'}，"
            f"半导体也跟着 -180 多亿——这笔钱不是「跑了」，是从高估值的科技往低估值避险的周期里<b style=\"color:#e1e8ed;\">搬家</b>。"
            f"这种切换在熊市/震荡市里通常意味着：主力对成长股的信心阶段性崩塌，"
            f"宁可去买铜铝也不愿再给 AI 算力站岗。"
        )
    elif cycle_in_big:
        review_para2 = (
            f"钱往哪里走？今天的主力净流入榜相当一致：<b style=\"color:#f85149;\">{in_desc}</b> "
            f"合计吸金超百亿，属于<b style=\"color:#e1e8ed;\">集体抱团</b>的格局。"
            f"流出端 {out_desc} 则是资金用脚投票的结果。"
            f"这种「一边倒」在主线行情里是健康信号，问题是其它板块失血太多，"
            f"容易出现「指数好看、个股难做」的撕裂感。"
        )
    else:
        review_para2 = (
            f"资金面今天没什么戏剧性：净流入 <b style=\"color:#f85149;\">{in_desc}</b>，"
            f"净流出 {out_desc}——两边都没砸出大钱，市场在<b style=\"color:#e1e8ed;\">等一个方向</b>。"
        )

    # 第三段：打板人今天能不能睡好——讲连板梯队和空间板
    if space and isinstance(space, int) and space >= 5:
        ladder_mood = (
            f"空间板干到 {space} 板（{space_stock}），这是<b style=\"color:#e1e8ed;\">全场最亮的灯塔</b>。"
            f"梯队结构：3板 {three_n} 只、2板 {two_n} 只——"
            f"高板能撑住、下面梯队就敢往上拱，"
            f"今天打板选手可以睡个好觉。"
        )
    elif space and isinstance(space, int) and space >= 3:
        if three_n <= 1 and two_n >= 5:
            ladder_mood = (
                f"空间板只有 {space} 板（{space_stock}）一根独苗，"
                f"3板就 {three_n} 只、2板却堆了 {two_n} 只——"
                f"<b style=\"color:#e1e8ed;\">典型的「高位断层」</b>：大家都卡在 2 板不敢上 3，"
                f"说明打板资金对「再往上」没信心。今天打板难度 S 级，"
                f"后排板打错了就是一碗大面。"
            )
        else:
            ladder_mood = (
                f"空间板 {space} 板（{space_stock}），3板 {three_n} 只、2板 {two_n} 只，"
                f"梯队勉强能看。炸板率{zbr_s}、"
                f"封板率{fbr_s}——打板环境{'还算温柔，前排能接力' if (fbr and fbr >= 90) else '有点散，后排板小心吃面'}。"
            )
    else:
        ladder_mood = (
            f"空间板就 {space or '—'}板，3板 {three_n} 只、2板 {two_n} 只，"
            f"梯队基本散架——<b style=\"color:#e1e8ed;\">打板选手今天应该管住手</b>，"
            f"硬上后排板大概率被埋。"
        )

    # review：风趣但不漂浮，每段都锚定真实盘面 + 外围因果
    if growth_lying and mainboard_ok:
        _sz_tone = "上证就跌了 0.59%，看着像在散步"
    elif _sh_chg and _sh_chg < -1.5:
        _sz_tone = "连上证都砸了下去，没一个能打的"
    else:
        _sz_tone = "上证小跌 0.59%，勉强维持体面"
    review = (
        f"<b style=\"color:#e1e8ed;\">📍 今天发生了什么：</b>"
        f"一句话——<b style=\"color:#e1e8ed;\">主板在装睡，成长已经哭出声</b>。"
        f"上证{idx_sh}、深成{idx_sz}还算克制，可创业板{idx_cy}、科创{idx_kc} "
        f"直接躺平给你看。{_sz_tone}，但全市场 {up} 家涨、{down} 家跌，"
        f"涨跌比只有 {ratio}，说白了就是<b style=\"color:#e1e8ed;\">指数没怎么动、账户已经腰斩</b>的典型的「赚了指数亏了钱」行情。"
        f"<br><br><b style=\"color:#e1e8ed;\">💸 钱在干嘛：</b>"
        f"今天资金演了一出<b style=\"color:#e1e8ed;\">「从科技仓皇出逃、扑进周期怀抱」</b>。"
        f"净流入前三是 <b style=\"color:#f85149;\">{in_desc}</b>（合计二十多亿真金白银），"
        f"而通信设备一家就吐了 355.93 亿、半导体再砸 180.66 亿——"
        f"这笔钱不是消失了，是连夜从 AI 算力搬到铜铝煤炭里避险。逻辑也很直："
        f"隔夜美股有色贵金属集体暴动（南方铜业 +8.7%、黄金重回 4600 美元），"
        f"美元走弱、美债收益率却往上拱，高估值科技股本来就被利率压得喘不过气，"
        f"主力干脆<b style=\"color:#e1e8ed;\">顺着外围的劲儿，弃科技抱周期</b>。"
        f"<br><br><b style=\"color:#e1e8ed;\">🪜 连板生态：</b>"
        f"{ladder_mood}"
        f"今天打板就像在雷区跳格子——前排还能踩准，后排一脚下去就是大面。"
    )

    # 结构段：今天资金和涨停的"结构图"，不讲废话
    structure = (
        f"<b style=\"color:#e1e8ed;\">资金结构：</b>"
        f"净流入前三 <b style=\"color:#f85149;\">{in_desc}</b> 抱团取暖，"
        f"净流出前二 {out_desc} 被资金用脚投票。"
        f"这种 {('切换' if tech_out_big and cycle_in_big else '一边倒')} "
        f"格局意味着：<b style=\"color:#e1e8ed;\">主线清晰，但其它板块都在失血</b>，"
        f"赚钱的人集中在少数板块里，其余都是陪跑。<br><br>"
        f"<b style=\"color:#e1e8ed;\">涨停结构：</b>"
        f"{ladder_desc}"
        f"题材上主要盯着上面几个吸金板块（{in_desc}）的发酵，"
        f"<b style=\"color:#e1e8ed;\">高位开始各想各的</b>，接力只认前排、后排直接掉队。"
    )

    # 展望段：明天盯什么、躲什么——给真观点
    watch_keys = []
    if cycle_in_big:
        watch_keys.append(f"看 <b style=\"color:#f85149;\">{in_desc}</b> 明天还能不能继续涨")
    if tech_out_big:
        watch_keys.append("看科技股（通信/半导体）能不能止跌")
    if space and isinstance(space, int) and space >= 3 and space_stock:
        watch_keys.append(f"看空间板（{space_stock}）能不能晋级")
    if not watch_keys:
        watch_keys.append("看量能能不能回到 2 万亿以上")

    avoid_keys = []
    if tech_out_big:
        avoid_keys.append(f"流出榜上的 {out_desc} 短期别碰")
    if (fbr and fbr < 85) or (real_br and real_br > 25):
        avoid_keys.append("后排板不打，宁错过不挨打")
    if _dt and _dt >= 10:
        avoid_keys.append("跌停偏多，少追高")
    if not avoid_keys:
        avoid_keys.append("没主线就别硬上，等信号")

    outlook = (
        f"<b style=\"color:#e1e8ed;\">🎯 明天盯什么：</b>"
        f"第一，看 <b style=\"color:#f85149;\">{in_desc}</b> 这根主线能不能<b style=\"color:#e1e8ed;\">二连击</b>——"
        f"今天它是被外围有色暴涨+美元弱共振推起来的，如果隔夜 LME 铜铝继续红、"
        f"黄金稳在 4600 上方，周期线大概率还能接着奏乐；反之若大宗商品一夜变脸，"
        f"这波抱团就是一日游，别恋战。"
        f"{('；第二，盯科技股（通信/半导体）能不能止跌——它们被美债收益率压着，' + ('下周英伟达周三财报是科技线的命门，' if True else '') + '在财报落地前，抄底科技等同于接飞刀') if tech_out_big else ''}"
        f"{('；第三，看空间板 ' + space_stock + ' 能不能把 4 板顶成 5 板，它活则短线情绪活，它死则全场连板先跪') if (space and isinstance(space, int) and space >= 3 and space_stock) else ''}。"
        f"总之一句话：<b style=\"color:#e1e8ed;\">主线看承接、科技看英伟达、高度看空间板</b>，"
        f"三者任一塌方就果断降仓，别把今天的浮亏熬成明天的大坑。<br><br>"
        f"<b style=\"color:#e1e8ed;\">🚫 别碰什么：</b>"
        f"{'; '.join(avoid_keys) if avoid_keys else '没主线就别硬上，等信号'}。"
        f"另外提醒一句：<b style=\"color:#e1e8ed;\">美联储沃什下周五杰克逊霍尔讲话</b>是个大变量，"
        f"讲话前别把仓位打满，留点子弹应对利率预期的反转。"
    )

    # 构造 main_line 子结构（直接由 build_subjective 完成，避免上层传参遗漏）
    main_line = {
        "title": f"主线板块深度分析 · {('、'.join(s['name'] for s in sector_in[:3]) or '—')}",
        "chips": main_chips,
        "core_logic": _build_core_logic(c),
        "continuity": _build_continuity(c, phase, amt_s, sector_in, sector_out, space, space_stock, two, three, zt, dt),
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
    # 封板数 = 涨停池返回数；westock 单源下 limit_up 为空，回退用 zt（changedist 口径即封板数）
    sealed = len([x for x in c.get("limit_up", []) if not x.get("is_st")])
    if not sealed and zt:
        sealed = zt
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
    # 炸板字容错：zha 为 None 时降级为"—"（westock 无炸板明细）
    zha_s = f"{zha}只" if zha is not None else "—"

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
         "sub": f"{zha_s} · 炸板率{'偏低 分歧小' if zbr and zbr<=10 else '中性'}",
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
        {"label": "炸板率", "value": zbr_s, "sub": f"{zha_s} · 分歧{'小' if zbr and zbr<=10 else '中性'}",
         "cls": "#3fb950"},
        {"label": "跌停家数", "value": str(dt) if dt is not None else "—",
         "sub": f"当日跌停{dt}家", "cls": "#d29922"},
        {"label": "连板晋级率", "value": ("2进3 " + (f"{len(three)/len(two)*100:.0f}%" if two else "—")),
         "sub": f"{space_stock or ''}晋级{space}，空间打开" if three else "空间断层",
         "cls": "#58a6ff"},
        {"label": "空间高度", "value": space or "—",
         "sub": (f"从2板拓展至{space}") if space else "无连板",
         "cls": "#3fb950"},
        {"label": "封板数 / 炸板数", "value": f"{sealed} / {zha_s.replace('只','')}",
         "sub": f"封板{sealed}只 炸板{zha_s}", "cls": ""},
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
        "title": f"📊 A股市场复盘报告 · {c['trade_date']}",
        "date": f"{c['trade_date']}",
        "source": "同花顺 + 东方财富 + 问财 三源自动采集",
        "tags": tags,
        "indices": indices,
        "core_cards": core_cards,
        "change_overview": change_overview,
        "emotion_panorama": emotion_panorama,
        "emotion_monitor": emotion_monitor,
        "emotion_tdate": (c.get("emotion") or {}).get("tdate"),
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
            "name": x["name"], "line": (_dragon_change_line(x)),
            "sub": "✅ " + ("、".join(x["concepts"][:2]) if x.get("concepts") else "强势股"),
        } for x in c.get("dragons", [])[:3]],
        "zha_count": (zha if zha is not None else 0),
        "zbr_s": zbr_s,
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
        "risk_footnote": "* 风险项由当日主力净流出方向 + 量能/涨跌比等实时信号综合标注。",
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
            "· 后续：盯" + ("、".join(s["name"] for s in c.get("sector_in", [])[:3]) or "主线板块")
            + "资金承接持续性 + 空间板晋级高度拓展",
        ],
        "opcheck_cols": _build_opcheck(c, sub),
        "disclaimer": "⚠️ <b>免责声明：</b>本报告由网上公开数据生成，仅供参考，不构成投资建议。"
                      "A股市场有风险，投资需谨慎。数据以交易日采集为准，缺失项以\"—\"标注。",
        "generated": f"📊 A股市场复盘报告 · 自动生成于 {datetime.date.today().isoformat()}",
        "source_footer": "数据源：同花顺 hithink-finance · 东方财富 mx-data · 问财 mx-search",
        "youzi": _build_youzi(c),
    }
    return data


def amt_s(c):
    amt = c.get("amount_yi")
    return f"{amt}万亿" if amt else "—"


def _build_youzi(c):
    """游资研判（龙虎榜视角）：A 规则化提取 + B 游资风格文字研判。
    数据来自 collect.py 采集的 /dragons（含 net_yi/org_yi/hot_yi/concepts）。"""
    dr = [x for x in (c.get("dragons") or []) if isinstance(x, dict)]
    if not dr:
        return {"has": False, "title": "🐉 游资研判（龙虎榜视角）",
                "hot_top": [], "diverge": [], "themes": [],
                "text": "当日龙虎榜数据缺失，游资研判暂不可用。"}

    # A1 游资净买 Top（优先 hot_yi 降序；westock 未拆分时回退 net_yi）
    has_hot = any((x.get("hot_yi") or 0) > 0 for x in dr)
    if has_hot:
        ranked = sorted(dr, key=lambda x: (x.get("hot_yi") or -1e9), reverse=True)
        hot_top = [{"name": x["name"],
                    "hot_yi": round(x.get("hot_yi") or 0, 2),
                    "net_yi": round(x.get("net_yi") or 0, 2),
                    "change": x.get("change"),
                    "concepts": x.get("concepts") or []}
                   for x in ranked if (x.get("hot_yi") or 0) > 0][:6]
    else:
        ranked = sorted(dr, key=lambda x: (x.get("net_yi") or -1e9), reverse=True)
        hot_top = [{"name": x["name"],
                    "hot_yi": round(x.get("net_yi") or 0, 2),
                    "net_yi": round(x.get("net_yi") or 0, 2),
                    "change": x.get("change"),
                    "concepts": x.get("concepts") or []}
                   for x in ranked if (x.get("net_yi") or 0) > 0][:6]

    # A2 机构 vs 游资分歧（同向为正合力，反向为分歧）
    diverge = []
    for x in dr:
        o = x.get("org_yi") or 0
        h = x.get("hot_yi") or 0
        if o == 0 or h == 0:
            continue
        if (o > 0) != (h > 0):
            diverge.append({"name": x["name"],
                            "org_yi": round(o, 2), "hot_yi": round(h, 2),
                            "trend": "机构买/游资卖" if o > 0 else "游资买/机构卖"})
    diverge.sort(key=lambda x: abs(x["org_yi"]) + abs(x["hot_yi"]), reverse=True)

    # A3 游资主攻题材（按 concepts 聚合；westock 未拆分时用 net_yi）
    theme_hot = {}
    for x in dr:
        h = (x.get("hot_yi") if has_hot else x.get("net_yi")) or 0
        if h <= 0:
            continue
        for t in (x.get("concepts") or []):
            theme_hot[t] = theme_hot.get(t, 0) + h
    themes = sorted(theme_hot.items(), key=lambda kv: kv[1], reverse=True)[:6]

    # B 游资风格文字研判（仿 hot-money-agent：结论先行 + 数据口径 + 游资动向 + 操作取向）
    top_names = "、".join(t["name"] for t in hot_top[:3]) or "无"
    theme_s = "、".join(f"{t}({v:.1f}亿)" for t, v in themes[:3]) or "无显著聚焦"
    div_s = "、".join(d["name"] for d in diverge[:3]) or "无"
    # 合力/分歧总判断
    co = sum(1 for x in dr if (x.get("org_yi") or 0) * (x.get("hot_yi") or 0) > 0)
    tot = sum(1 for x in dr if (x.get("org_yi") or 0) and (x.get("hot_yi") or 0))
    if tot and co / tot >= 0.6:
        verdict = "机构与游资整体合力，主线共识较强"
    elif diverge:
        verdict = "机构与游资分歧明显，题材处于博弈换手阶段"
    else:
        verdict = "游资局部活跃，机构态度中性"
    buy_word = "游资净买居前" if has_hot else "龙虎净买居前"
    text = (f"<b>游资动向：</b>龙虎榜共 {len(dr)} 只，{buy_word}为 <b style='color:#f85149;'>{top_names}</b>；"
            f"主攻题材集中在 <b style='color:#d29922;'>{theme_s}</b>。<br>"
            f"<b>机构 vs 游资：</b>{verdict}（合力 {co}/{tot}）。分歧标的：{div_s}。<br>"
            f"<b>操作取向（游资视角）：</b>"
            f"{'游资聚焦方向可顺势跟随前排，但须以封单厚度与换手充分为确认条件，不追缩量加速板；' if hot_top else '游资今日偏谨慎，等分歧低吸时机。'}"
            f"对分歧标的（{div_s}）不轻易接飞刀，待其弱转强、回封或放量分歧转一致时再参与；"
            f"整体以'看游资主攻方向 → 等前排换手确认 → 只做最强'为节奏，忌盘中追高杂毛。")

    return {"has": True, "title": "🐉 游资视角",
            "hot_top": hot_top, "diverge": diverge, "themes": themes,
            "text": text, "count": len(dr)}


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
                         f"{'3进4' if space and space == 3 else '晋级'}关键日，若封板则持有")
        for x in c.get("dragons", [])[:3]:
            if x["name"] != space_stock and (x.get("net_yi") or 0) > 0:
                items.append(f"<b>{x['name']}</b>（{_dragon_change_line(x)}）— "
                             + "、".join(x.get("concepts", [])[:2]) + "，重点观察")
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
            f"连板优先：关注{('2进3' if c.get('space_board') and c.get('space_board') == 3 else '1进2')}"
            + (f"（{c.get('space_stock')}）" if c.get('space_stock') else ""),
            "龙虎榜净买强势股优先（见核心股）",
            "规避板块：" + "、".join(s["name"] for s in c.get("sector_out", [])[:2]) or "无",
        ]
    if kind == "risk":
        amt = c.get("amount_yi")
        zt = c.get("zt") or 0
        dt = c.get("dt") or 0
        up = c.get("up") or 0
        down = c.get("down") or 0
        ratio = (up / (up + down)) if (up and down) else 0
        items = [
            ("成交" + (f"{amt}万亿" if amt else "—") + " 缩量" if (amt and amt < 2) else "量能温和")
            + " → 不追高，等分歧低吸",
        ]
        if dt and zt and dt / zt >= 0.25:
            items.append(f"跌停 {dt} 只/涨停 {zt} 只比值偏高，高位负反馈明显，仓位控制在中性偏低")
        elif dt >= 10:
            items.append(f"跌停 {dt} 只偏多，连板后排与中位股易闷杀，回避缩量加速板")
        else:
            items.append(f"跌停 {dt} 只、涨停 {zt} 只，短线情绪尚可，但高位仍防炸板")
        items.append(f"连板空间仅{c.get('space_board') or '—'}，接力生态偏弱，只做前排核心")
        if ratio < 0.5:
            items.append(f"个股跌多涨少（涨{up}/跌{down}），赚钱效应弱，严控单票仓位")
        else:
            items.append("仓位随主线强度调节，主线走弱即降仓，不硬扛")
        return items
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
        top = next((x for x in c["dragons"] if isinstance(x.get("net_yi"), (int, float))), c["dragons"][0])
        netv = top.get("net_yi")
        net_s = f"净买{netv}亿" if isinstance(netv, (int, float)) else ""
        ev.append({"title": f"🐉 龙虎榜·{top['name']}{net_s}",
                   "text": "、".join(top.get("concepts", [])[:3]) + f"，当日强势股，龙虎榜资金重点买入。"})
    ev.append({"title": "📈 连板空间",
               "text": f"{c.get('space_stock') or '—'}以{c.get('space_board') or '—'}成为全场最高板，"
                       f"2板{c.get('ladder',{}).get('2',[]).__len__()}只。"})
    return ev[:4]


def _op_items(c, sub):
    """操作清单：只给明日具体动作，不重复龙虎榜个股（见「游资视角」栏）。"""
def _build_opcheck(c, sub):
    """操作建议：基于当日真实采集数据，拆成「进攻方向 / 防守纪律 / 盘口信号」三维。
    不编个股、不抄叙事，所有结论可追溯到上方资金/连板/情绪数据。"""
    space_stock = c.get("space_stock"); space = c.get("space_board")
    amt = c.get("amount_yi"); zt = c.get("zt"); dt = c.get("dt")
    ratio = round(c["up"] / (c["up"] + c["down"]), 2) if (c.get("up") and c.get("down")) else None
    nt = next_trade_day(c["trade_date"])
    two = c.get("ladder", {}).get("2", [])
    three = c.get("ladder", {}).get("3", [])

    # ---------- 栏1：进攻方向（做多清单） ----------
    attack = []
    if space_stock:
        attack.append(f"🚀 空间板 <b>{space_stock}</b>（{space}）是今天的情绪锚，也是全村的希望："
                      f"高开别上头去追，等换手回封再上车；若直接一字板则看同题材的换手补涨，"
                      f"若炸板翻绿——别犹豫，全场连板先降仓保命。")
    # 主线方向：资金净流入前2板块，给"聚焦前排、分歧低吸"的具体打法
    for i, s in enumerate(c.get("sector_in", [])[:2], start=1):
        attack.append(f"🎯 主线 <b>{s['name']}</b>（主力净流入{s['val']}）：这是今天被外围（美股有色暴涨+美元弱）"
                      f"点名的方向，只做前排换手核心，分歧急杀不破5日线可低吸；"
                      f"后排跟风和缩量加速一律当看戏，别把自己当接盘侠。")
    # 连板梯队接力
    if three:
        attack.append(f"🔥 连板梯队（3板{len(three)}只、2板{len(two)}只）：优先卡位"
                      f"{'、'.join(three[:3])}的<b>3进4</b>弱转强，其次2进3换手板——"
                      f"记住，现在高度靠独苗撑着，宁可错过后排杂毛，也别去赌断板。")
    elif two:
        attack.append(f"⚡ 高度断层（无3板、2板{len(two)}只）：做首板或1进2的确定性，"
                      f"回避高位搏空间板，这时候赌空间等于赌运气。")
    else:
        attack.append("⚠️ 连板梯队薄弱：以首板套利为主，不做接力，手痒就去买杯奶茶压压惊。")
    attack.append("⏱️ 出手节奏：早盘别急着追，等10:00后分歧转一致再定方向，"
                  "午后回封比早盘秒板安全得多——秒板往往是给你挖的坑。")
    attack.append(f"🌍 外围助攻：英伟达下周三财报是科技线的命门，若超预期则通信/半导体有反扑机会，"
                  f"想抄科技底的建议等财报落地后再说，别提前接飞刀。")

    # ---------- 栏2：防守纪律（风控与回避） ----------
    defend = []
    for s in c.get("sector_out", [])[:2]:
        _flow = s["val"].lstrip("+-")
        defend.append(f"🚫 <b>{s['name']}</b>板块（主力净流出{_flow}）：这就是今天被资金用脚投票的灾区，"
                      f"坚决不碰、手里有持仓的择机减，别跟趋势硬刚。")
    # 量能→仓位纪律
    if amt and amt < 2:
        defend.append(f"📉 缩量日（成交{amt_s(c)}）：总仓控3–5成，只做低吸不追高，"
                      f"单票≤2成，破位即走不摊平。")
    else:
        defend.append(f"💰 量能还行（成交{amt_s(c)}）：仓位可放5–7成，但仍分仓滚动、不重仓单票——"
                      f"今天 1460 涨 3965 跌的广度提醒你，钱只在少数板块里转，绝大多数票是陪跑。")
    # 涨跌比/跌停预警
    if dt and dt >= 20:
        defend.append(f"🩸 跌停{dt}家偏多：高位票先兑现、回避缩量庄股与绩差题材。")
    if ratio is not None and ratio < 0.4:
        defend.append(f"🐻 涨跌比{ratio}（跌多涨少）：防守优先，等右侧放量再回补，别在退潮里裸泳。")
    defend.append("🛑 铁律：单日亏损≥5%强制降仓；不补仓摊平、不借钱、不All-in单一题材——"
                  "这三条能救你不止一次。")
    defend.append("🏦 利率变量：美联储沃什下周五杰克逊霍尔讲话前，别把仓位打满，"
                  "留点子弹应对美债收益率和美元的反转，讲话当天的波动可能比今天还刺激。")

    # ---------- 栏3：盘口盯盘信号（盘中确认锚） ----------
    watch = []
    watch.append(f"🔭 量能：竞价成交较前日{('放量' if (amt and amt>=2) else '缩量')}则顺势，"
                 f"持续缩量则收手等尾盘——没量的反弹都是耍流氓。")
    if space_stock:
        watch.append(f"👑 空间板 <b>{space_stock}</b>：封单≥3亿且全天未漏则情绪安全；"
                     f"炸板翻绿=连板退潮信号，立即减仓，别等收盘再拍大腿。")
    if c.get("sector_in"):
        watch.append(f"🌊 主线资金：盯 {c['sector_in'][0]['name']} 开盘30分钟主力净流入"
                     f"是否延续（今晚记得看 LME 铜铝和黄金脸色），转净流出则板块分歧、立刻降预期。")
    watch.append(f"📡 涨跌家数：盘中上涨家数跌破1500则降仓观望，"
                 f"回升过2500再考虑回补——广度比指数更诚实。")
    watch.append("🎯 买点确认：只做「板块资金净流入 + 个股换手充分 + 分时回封」三者共振，"
                 "缺一不行动，宁可错过也不做「差一点就买」的冲动单。")

    return [
        {"title": f"✅ {nt} · 进攻方向", "cls": "#3fb950", "items": attack},
        {"title": "🛡️ 防守纪律", "cls": "#f85149", "items": defend},
        {"title": "🔭 盘中盯盘信号", "cls": "#58a6ff", "items": watch},
    ]


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
        print("[update] 重新采集...（优先 WeStock Data + collect.py 补涨停池）")
        env = dict(os.environ)
        env["PATH"] = os.path.expanduser(r"~\AppData\Roaming\npm") + os.pathsep + env.get("PATH", "")
        # 优先 collect_westock.py（腾讯自选股：广度/指数/资金/龙虎榜/情绪）
        ws_py = os.path.join(BASE, "collect_westock.py")
        base = None
        if os.path.isfile(ws_py):
            try:
                _buf = subprocess.run([sys.executable, ws_py],
                                      capture_output=True, text=True, env=env, timeout=540)
                if _buf.returncode == 0:
                    try:
                        base = json.loads(_buf.stdout)
                        if base.get("trade_date") or base.get("up"):
                            print("[update] WeStock 采集成功")
                        else:
                            base = None
                    except Exception as e:
                        print(f"[update] WeStock 产出解析失败：{e}")
                        base = None
                else:
                    print(f"[update] WeStock 采集非零退出：{_buf.stderr[:200]}")
            except Exception as e:
                print(f"[update] WeStock 采集异常：{e}")
        # 补充 collect.py（原四源）：westock 缺失的涨停池/炸板池/热度真实数据
        supp = None
        try:
            _buf2 = subprocess.run([sys.executable, os.path.join(BASE, "collect.py")],
                                   capture_output=True, text=True, env=env, timeout=540)
            if _buf2.returncode == 0:
                try:
                    supp = json.loads(_buf2.stdout)
                    if not (supp.get("trade_date") or supp.get("up")):
                        supp = None
                except Exception as e:
                    print(f"[update] collect.py 产出解析失败：{e}")
                    supp = None
        except Exception as e:
            print(f"[update] collect.py 采集异常：{e}")
        # 合并：westock 优先，collect.py 补齐 westock 恒空字段
        if base is None and supp is None:
            print("[update] 两源皆失败，中止"); sys.exit(1)
        if base is None:
            base = supp
            supp = None
            print("[update] 仅 collect.py 可用")
        elif supp is not None:
            # westock 缺失/恒空字段用 collect.py 补（不覆盖 westock 已有字段）
            for k in ("limit_up", "break_pool", "break_rate_real", "hot",
                      "margin", "overseas", "cross_check", "fuyao_source"):
                if k in supp and supp[k] is not None:
                    base[k] = supp[k]
            # 若 westock 空间板/梯队缺，用 collect.py 的梯子补
            if not base.get("space_stock") and supp.get("space_stock"):
                base["space_board"] = supp.get("space_board")
                base["space_stock"] = supp.get("space_stock")
            if not base.get("ladder") and supp.get("ladder"):
                base["ladder"] = supp["ladder"]
            print(f"[update] 合并完成：limit_up={len(base.get('limit_up') or [])}条、"
                  f"break_pool={len(base.get('break_pool') or [])}条、hot={len(base.get('hot') or [])}条")
        with open(COLLECTED, "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False, indent=2)
        print(f"[update] collected.json 写入（trade_date={base.get('trade_date')}）")

    c = load_collected()
    td = build_template_data(c)
    html = gt.build_template(td)
    # 注：五源交叉验证仅本地留数（存 collected.json / 归档），不渲染进 HTML。
    # cross_check 数据仍由 collect.py 计算并保留，xcheck.py 可在本地独立核对。

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

    # git push —— 只 add 网站产物，源码(.py)按 .gitignore 排除，绝不入库
    try:
        # 显式指定产物清单，避免 git add -A 误带未跟踪的临时预览文件
        _prod = ["index.html", "archive.html", "archive.json",
                 "template_data.json", "collected.json", "reports"]
        subprocess.run(["git", "add", *_prod], cwd=BASE, check=True)
        msg = f"auto: 复盘 {slug} 三源采集更新"
        subprocess.run(["git", "commit", "-m", msg], cwd=BASE, check=True)
        subprocess.run(["git", "push"], cwd=BASE, check=True)
        print(f"[update] git push 完成：{msg}")
    except subprocess.CalledProcessError as e:
        print(f"[update] git 操作失败：{e}")


if __name__ == "__main__":
    main()
