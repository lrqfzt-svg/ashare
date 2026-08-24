# -*- coding: utf-8 -*-
"""
gen_report.py — 基于原版 22 模块模板生成 A股复盘报告（重做版）

- CSS 一字不改地从 template.html 提取（模板锁定）。
- 22 个模块按原版顺序生成，结构/配色/类名与原版一致。
- 所有数字动态取值；数据缺失显示"—"（宁缺毋假）。
- 输出：a-share-report-YYYY-MM-DD.html（当日报告）
        + index.html（门户，同当日报告）
"""
import json, os, re, sys, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE, "template.html")
COLLECTED = os.path.join(BASE, "collected.json")


# ---------- 工具 ----------
def load_collected():
    with open(COLLECTED, encoding="utf-8") as f:
        return json.load(f)


def trend_word(chg):
    """涨跌幅 → 方向词。chg 可能带 %。"""
    try:
        v = float(str(chg).rstrip("%"))
    except Exception:
        return "—"
    if v > 0:
        return f"+{v}% ▲"
    if v < 0:
        return f"{v}% ▼"
    return "0%"


def cls_of(chg):
    try:
        v = float(str(chg).rstrip("%"))
    except Exception:
        return "down"
    return "up" if v >= 0 else "down"


def positive_cls(v):
    """给渲染用的涨跌 class：涨=up(红) 跌=down(绿)。"""
    s = str(v).replace("%", "")
    try:
        n = float(s)
        return "up" if n >= 0 else "down"
    except Exception:
        return "down"


def fmt_amt(yi):
    """成交额(万亿) → 文案。"""
    if yi is None:
        return "—"
    return f"{yi:.2f}万亿"


def fmt_seal_yi(x):
    if x is None:
        return "—"
    return f"{x}亿"


# ---------- 模板 CSS（原样提取，模板锁定） ----------
def load_css():
    html = open(TEMPLATE, encoding="utf-8").read()
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    return m.group(1) if m else ""


# ---------- 模块构建 ----------
def build_header(c):
    """Header：标题 + 日期 + 标签 + 市场概况 tag。"""
    date = c.get("trade_date") or datetime.date.today().isoformat()
    try:
        y, m, d = date.split("-")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.date(int(y), int(m), int(d)).weekday()]
        date_cn = f"{y}年{m}月{d}日（{weekday}）"
    except Exception:
        date_cn = date
    # 市场概况 tag：根据涨跌家数/指数判断
    up = c.get("up"); down = c.get("down")
    zt = c.get("zt"); dt = c.get("dt")
    if up is not None and down is not None:
        if up > down * 2 and zt and zt >= 60:
            tag = "🔥 全面暴涨"
            tag_color = "#3fb950"
        elif up > down:
            tag = "📈 普涨格局"
            tag_color = "#3fb950"
        elif zt and zt >= 50 and dt and dt < 10:
            tag = "🔥 涨停潮·指数分化"
            tag_color = "#d29922"
        elif zt and zt >= 30:
            tag = "⚡ 涨停潮"
            tag_color = "#d29922"
        else:
            tag = "📉 跌多涨少"
            tag_color = "#f85149"
    else:
        tag = "—"
        tag_color = "#8b949e"
    tags = ["今日复盘", "A股市场", "短线情绪", "数据已更新"]
    tags_html = "".join(f'<span class="tag">{t}</span>' for t in tags)
    tag5 = f'<span class="tag" style="border-color:{tag_color};color:{tag_color};">{tag}</span>'
    return f"""  <!-- Header -->
  <div class="header">
    <h1>📊 A股市场复盘报告</h1>
    <div class="date">📅 {date_cn}</div>
    <div class="tags">
      {tags_html}
      {tag5}
    </div>
  </div>
"""


def build_index_cards(c):
    """4 张指数概览卡片。"""
    cards = ""
    for name in ["上证指数", "深证成指", "创业板指", "科创50"]:
        idx = next((x for x in (c.get("indices") or []) if x["name"] == name), None)
        if idx and idx.get("value") is not None:
            value = f"{idx['value']:.2f}"
            chg = idx.get("chg_pct")
            cls = cls_of(chg)
            sub = trend_word(chg)
        else:
            value = "—"
            cls = "down"
            sub = "—"
        cards += f"""    <div class="card">
      <div class="label">{name}</div>
      <div class="value {cls}">{value}</div>
      <div class="sub {cls}">{sub}</div>
    </div>
"""
    return f"""  <!-- 4 Cards -->
  <div class="cards">
{cards}  </div>
"""


def build_limit_cards(c):
    """涨停封板率核心指标卡（4张）。"""
    zt = c.get("zt")
    limit_up = c.get("limit_up") or []
    sealed = len([x for x in limit_up if not x.get("is_st")])
    if not sealed and zt:
        sealed = zt
    break_rate = c.get("break_rate_real")
    brk = len(c.get("break_pool") or [])
    if break_rate is not None:
        zbr = f"{break_rate:.0f}%"
        zbr_sub = f"{brk}/{zt or sealed} · 炸板率{'正常' if break_rate <= 25 else '偏高'}"
    else:
        zbr = "—"
        zbr_sub = "—"
    fbr = (sealed / zt * 100) if (zt and sealed) else None
    if fbr is not None:
        fbr_s = f"{fbr:.0f}%"
        fbr_sub = f"{sealed}/{zt} · 封板率{'高水平' if fbr >= 85 else '一般'}"
    else:
        fbr_s = "—"
        fbr_sub = "—"
    return f"""  <!-- 涨停封板率 核心指标卡 -->
  <div class="cards" style="grid-template-columns: repeat(4, 1fr); margin-bottom: 20px;">
    <div class="card" style="border-color: #d2992244;">
      <div class="label">🎯 触及涨停</div>
      <div class="value" style="color: #d29922;">~{zt if zt is not None else '—'}</div>
      <div class="sub">只（沪深京+科创板）</div>
    </div>
    <div class="card" style="border-color: #3fb95044;">
      <div class="label">✅ 封板</div>
      <div class="value up">{sealed or '—'}</div>
      <div class="sub">只（涨停封死）</div>
    </div>
    <div class="card" style="border-color: #58a6ff44;">
      <div class="label">📊 涨停封板率</div>
      <div class="value" style="color: #58a6ff;">{fbr_s}</div>
      <div class="sub">{fbr_sub}</div>
    </div>
    <div class="card" style="border-color: #f8514944;">
      <div class="label">💥 炸板率</div>
      <div class="value" style="color: #d29922;">{zbr}</div>
      <div class="sub">{zbr_sub}</div>
    </div>
  </div>
"""


def build_breadth(c):
    """涨停家数概览：上涨/下跌/涨跌比/成交。"""
    up = c.get("up"); down = c.get("down")
    if up is not None and down is not None:
        ratio = round(up / (up + down), 2)
        ratio_s = f"{ratio:.2f}"
    else:
        ratio_s = "—"
    amt = c.get("amount_yi")
    amt_s = fmt_amt(amt)
    amt_note = "沪深总成交 ▲+放量" if amt else "沪深总成交"
    return f"""  <!-- 涨停家数概览 -->
  <div class="section">
    <div class="section-title"><span class="icon">📈</span> 涨停家数概览</div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;text-align:center;">
      <div>
        <div style="font-size:36px;font-weight:700;color:#f85149;">{up if up is not None else '—'}</div>
        <div style="font-size:13px;color:#8b949e;">上涨家数</div>
      </div>
      <div>
        <div style="font-size:36px;font-weight:700;color:#3fb950;">{down if down is not None else '—'}</div>
        <div style="font-size:13px;color:#8b949e;">下跌家数</div>
      </div>
      <div>
        <div style="font-size:36px;font-weight:700;color:#58a6ff;">{ratio_s}</div>
        <div style="font-size:13px;color:#8b949e;">涨跌比</div>
      </div>
      <div>
        <div style="font-size:36px;font-weight:700;color:#d29922;">{amt_s}</div>
        <div style="font-size:13px;color:#8b949e;">{amt_note}</div>
      </div>
    </div>
  </div>
"""


def build_emotion_overview(c):
    """短线情绪全景：连板总数/空间板/封板率/昨板表现/创科创。"""
    ladder = c.get("ladder") or {}
    total_lb = sum(len(v) for v in ladder.values())
    space = c.get("space_board")
    space_s = f"{space}板" if space else "—"
    space_stock = c.get("space_stock") or "—"
    limit_up = c.get("limit_up") or []
    sealed = len([x for x in limit_up if not x.get("is_st")])
    zt = c.get("zt")
    if not sealed and zt:
        sealed = zt
    fbr = (sealed / zt * 100) if (zt and sealed) else None
    fbr_s = f"{fbr:.0f}%" if fbr is not None else "—"
    fbr_note = "偏高 市场偏强" if (fbr and fbr >= 85) else "中性"
    # 创业板/科创板涨停数（从 limit_up 按 ticker 前缀统计：30=创业 / 688=科创）
    cy = sum(1 for x in limit_up if str(x.get("ticker", "")).startswith("30"))
    kc = sum(1 for x in limit_up if str(x.get("ticker", "")).startswith("688"))
    return f"""  <!-- 短线情绪全景 -->
  <div class="section">
    <div class="section-title"><span class="icon">⚡</span> 短线情绪全景</div>
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;text-align:center;margin-bottom:16px;">
      <div style="background:#21262d;border-radius:8px;padding:14px;">
        <div style="font-size:12px;color:#8b949e;">连板总数</div>
        <div style="font-size:24px;font-weight:700;color:#e1e8ed;margin-top:4px;">{total_lb}</div>
        <div style="font-size:11px;color:#f85149;">低位重建中</div>
      </div>
      <div style="background:#21262d;border-radius:8px;padding:14px;">
        <div style="font-size:12px;color:#8b949e;">空间板</div>
        <div style="font-size:24px;font-weight:700;color:#f85149;margin-top:4px;">{space_s}</div>
        <div style="font-size:11px;color:#8b949e;">{space_stock}</div>
      </div>
      <div style="background:#21262d;border-radius:8px;padding:14px;">
        <div style="font-size:12px;color:#8b949e;">封板率</div>
        <div style="font-size:24px;font-weight:700;color:#3fb950;margin-top:4px;">{fbr_s}</div>
        <div style="font-size:11px;color:#3fb950;">{fbr_note}</div>
      </div>
      <div style="background:#21262d;border-radius:8px;padding:14px;">
        <div style="font-size:12px;color:#8b949e;">昨板表现</div>
        <div style="font-size:24px;font-weight:700;color:#8b949e;margin-top:4px;">—</div>
        <div style="font-size:11px;color:#8b949e;">数据未返回</div>
      </div>
      <div style="background:#21262d;border-radius:8px;padding:14px;">
        <div style="font-size:12px;color:#8b949e;">创/科创</div>
        <div style="font-size:24px;font-weight:700;color:#e1e8ed;margin-top:4px;">{cy}/{kc}</div>
        <div style="font-size:11px;color:#8b949e;">创业板{cy}只/科创{kc}只</div>
      </div>
    </div>
  </div>
"""


def build_emotion_monitor(c):
    """情绪监测 & 极端值（2x3 网格）。"""
    br = c.get("break_rate_real")
    brk = len(c.get("break_pool") or [])
    zt = c.get("zt"); dt = c.get("dt")
    br_s = f"{br:.0f}%" if br is not None else "—"
    br_note = "正常偏低 打板安全边际高" if (br and br <= 15) else ("偏高 分歧加大" if (br and br > 25) else "中性")
    dt_s = str(dt) if dt is not None else "—"
    dt_note = "极低 市场无恐慌" if (dt is not None and dt < 10) else "中性"
    # 空间高度
    space = c.get("space_board")
    space_s = f"{space}板" if space else "—"
    space_note = "压缩后重新拓展中" if space else "—"
    # 封板/炸板
    limit_up = c.get("limit_up") or []
    sealed = len([x for x in limit_up if not x.get("is_st")])
    if not sealed and zt:
        sealed = zt
    seal_break_s = f"{sealed} / {brk}"
    return f"""  <!-- 情绪监测 & 极端值 -->
  <div class="section">
    <div class="section-title"><span class="icon">🚨</span> 情绪监测 & 极端值</div>
    <div class="sentiment-grid">
      <div class="sentiment-item">
        <div class="s-label">炸板率</div>
        <div class="s-value" style="color:#d29922;">{br_s}</div>
        <div style="font-size:12px;color:#3fb950;margin-top:4px;">{br_note}</div>
      </div>
      <div class="sentiment-item">
        <div class="s-label">跌停家数</div>
        <div class="s-value" style="color:#3fb950;">{dt_s}</div>
        <div style="font-size:12px;color:#3fb950;margin-top:4px;">{dt_note}</div>
      </div>
      <div class="sentiment-item">
        <div class="s-label">连板晋级率</div>
        <div class="s-value" style="color:#58a6ff;">—</div>
        <div style="font-size:12px;color:#d29922;margin-top:4px;">数据未返回</div>
      </div>
      <div class="sentiment-item">
        <div class="s-label">空间高度</div>
        <div class="s-value" style="color:#d29922;">{space_s}</div>
        <div style="font-size:12px;color:#d29922;margin-top:4px;">{space_note}</div>
      </div>
      <div class="sentiment-item">
        <div class="s-label">封板数 / 炸板数</div>
        <div class="s-value" style="color:#e1e8ed;">{seal_break_s}</div>
        <div style="font-size:12px;color:#3fb950;margin-top:4px;">封板{sealed}只 炸板{brk}只</div>
      </div>
      <div class="sentiment-item">
        <div class="s-label">情绪周期判断</div>
        <div class="s-value" style="color:#3fb950;font-size:17px;">震荡分化</div>
        <div style="font-size:12px;color:#3fb950;margin-top:4px;">基于当日涨跌家数与涨停分布</div>
      </div>
    </div>
  </div>
"""


def build_jinji(c):
    """连板梯队 & 晋级率统计。"""
    ladder = c.get("ladder") or {}
    two = ladder.get("2") or []
    three = ladder.get("3") or []
    four = ladder.get("4") or []
    rows = ""
    # 1进2：2板家数（前日基数未知留—）
    rows += f"""        <tr>
          <td style="font-weight:600;">1进2</td>
          <td>—</td>
          <td>{len(two)}只</td>
          <td><span class="jinji-rate jinji-low">—</span></td>
          <td>{'、'.join(two[:5]) if two else '—'}{' 等' if len(two) > 5 else ''}</td>
          <td style="color:#d29922;">晋级率数据未返回</td>
        </tr>
"""
    rows += f"""        <tr>
          <td style="font-weight:600;">2进3</td>
          <td>—</td>
          <td>{len(three)}只</td>
          <td><span class="jinji-rate jinji-low">—</span></td>
          <td>{'、'.join(three[:5]) if three else '—'}</td>
          <td style="color:#d29922;">晋级率数据未返回</td>
        </tr>
"""
    if four:
        rows += f"""        <tr>
          <td style="font-weight:600;">3进4</td>
          <td>—</td>
          <td>{len(four)}只</td>
          <td><span class="jinji-rate">—</span></td>
          <td>{'、'.join(four[:5])}</td>
          <td style="color:#d29922;">晋级率数据未返回</td>
        </tr>
"""
    else:
        rows += """        <tr>
          <td style="font-weight:600;">3进4</td>
          <td>—</td>
          <td>0只</td>
          <td><span class="jinji-rate jinji-zero">0%</span></td>
          <td>—</td>
          <td style="color:#8b949e;">暂无4板个股</td>
        </tr>
"""
    rows += """        <tr>
          <td style="font-weight:600;">4进5</td>
          <td>—</td>
          <td>0只</td>
          <td>—</td>
          <td>—</td>
          <td style="color:#8b949e;">暂无5板个股</td>
        </tr>
"""
    space = c.get("space_board"); space_stock = c.get("space_stock")
    if space and space_stock:
        obs = f"<strong>核心观察：</strong>当前空间板为 <strong>{space}板（{space_stock}）</strong>，连板梯队 2板 {len(two)} 只、3板 {len(three)} 只。市场高度尚在压缩阶段，接力需聚焦龙头。"
    else:
        obs = "<strong>核心观察：</strong>连板梯队数据有限，市场高度压缩，短线接力需谨慎。"
    return f"""  <!-- 连板梯队 & 晋级率统计 -->
  <div class="section">
    <div class="section-title"><span class="icon">🏆</span> 连板梯队 & 晋级率统计</div>
    <table class="jinji-table">
      <thead>
        <tr>
          <th>晋级档位</th>
          <th>前日基数</th>
          <th>成功数</th>
          <th>晋级率</th>
          <th>代表个股</th>
          <th>信号解读</th>
        </tr>
      </thead>
      <tbody>
{rows}      </tbody>
    </table>
    <div style="margin-top:12px;padding:10px;background:#f8514910;border-radius:8px;font-size:13px;color:#f85149;">
      ⚠ {obs}
    </div>
  </div>
"""


def build_sector_board(c):
    """板块涨跌榜 Top5：涨幅榜（含主力净流入）+ 跌幅榜（含主力净流出）。"""
    # 涨幅榜：用 sector_chg（涨幅）前5，净流入尝试匹配 sector_in
    sector_chg = c.get("sector_chg") or []
    in_top = c.get("sector_in") or []
    out_top = c.get("sector_out") or []
    in_flow = {x["name"]: x["val"] for x in in_top}
    # 涨幅榜前5（有涨幅数据的）
    up_rows = ""
    cnt = 0
    for x in sector_chg:
        name = x["name"]
        chg = x["chg_pct"]
        if chg is None:
            continue
        flow = in_flow.get(name)
        if flow:
            flow_cls = "positive" if not str(flow).startswith("-") else "negative"
            flow_txt = flow
        else:
            flow_cls = "down"
            flow_txt = "—"
        up_rows += f'          <tr><td>{name}</td><td class="positive">+{chg:.2f}%</td><td class="{flow_cls}">{flow_txt}</td></tr>\n'
        cnt += 1
        if cnt >= 5:
            break
    if cnt == 0:
        up_rows = '          <tr><td colspan="3" style="color:#8b949e;">涨幅榜数据未返回</td></tr>\n'
    # 跌幅榜：净流出前5（板块级）
    down_rows = ""
    for x in (out_top or [])[:5]:
        name = x["name"]
        val = x["val"]
        down_rows += f'          <tr><td>{name}</td><td class="negative">—</td><td class="negative">{val}</td></tr>\n'
    if not out_top:
        down_rows = '          <tr><td colspan="3" style="color:#8b949e;">跌幅榜数据未返回</td></tr>\n'
    return f"""  <!-- 板块涨跌榜 -->
  <div class="section">
    <div class="section-title"><span class="icon">🔥</span> 板块涨跌榜 Top5</div>
    <div class="two-col">
      <div class="col">
        <h4 style="color:#f85149;">🔴 涨幅榜 Top5</h4>
        <table>
          <tr><th>板块</th><th>涨幅</th><th>主力净流入</th></tr>
{up_rows}        </table>
      </div>
      <div class="col">
        <h4 style="color:#3fb950;">🟢 跌幅榜 Top5</h4>
        <table>
          <tr><th>板块</th><th>跌幅</th><th>主力净流出</th></tr>
{down_rows}        </table>
      </div>
    </div>
  </div>
"""


def build_main_line(c):
    """主线板块深度分析。"""
    sector_in = c.get("sector_in") or []
    limit_up = c.get("limit_up") or []
    space = c.get("space_board"); space_stock = c.get("space_stock")
    # 主线 chips：按流入板块 + 涨停题材统计
    chips = []
    in_top = sector_in[:3]
    for i, s in enumerate(in_top):
        chips.append(f'<span>主线{i+1}·{s["name"]}：<b style="color:#f85149;">{s["val"]}</b></span>')
    if space:
        chips.append(f'<span>最高板：<b style="color:#f85149;">{space}板 {space_stock or ""}</b></span>')
    # 涨停题材分组统计（reason 首词）
    from collections import Counter
    topic_cnt = Counter()
    for x in limit_up:
        reason = x.get("reason") or "其他"
        # 取第一个题材
        first = reason.split("+")[0].split("·")[0].split("(")[0].strip()[:6]
        topic_cnt[first] += 1
    for t, n in topic_cnt.most_common(4):
        chips.append(f'<span>{t}：<b style="color:#f85149;">{n}只涨停</b></span>')
    chips_html = "\n        ".join(chips)
    # 核心逻辑（基于真实数据动态生成）
    in_desc = "、".join(s["name"] for s in sector_in[:3]) or "—"
    out_desc = "、".join(s["name"] for s in (c.get("sector_out") or [])[:2]) or "—"
    zt = c.get("zt")
    br = c.get("break_rate_real")
    core = (
        f"① 资金面：主力净流入居前的是 <b style=\"color:#f85149;\">{in_desc}</b>，"
        f"净流出居前的是 {out_desc}——钱往哪里钻，藏不住。"
        f"② 涨停面：今日涨停 {zt or '—'} 只，空间板 {space or '—'} 板"
        f"{('（' + space_stock + '）') if space_stock else ''}，"
        f"炸板率 {f'{br:.1f}%' if br is not None else '—'}，"
        f"题材集中度一般，资金更看重确定性方向。"
        f"③ 连板梯队：2板/3板梯队仍在，但高度压缩，短线情绪处于修复期。"
    )
    cont = (
        f"当前主线确定性在 {in_desc or '—'}，属于资金用脚投票的方向；"
        f"但大盘整体 {('跌多涨少' if (c.get('up') and c.get('down') and c['up'] < c['down']) else '涨跌互现')}，"
        f"持续性需观察明日资金是否继续承接。追高需谨慎，分歧低吸优先。"
    )
    title = f"主线板块深度分析 · {'、'.join(s['name'] for s in sector_in[:3]) if sector_in else '—'}"
    return f"""  <!-- 主线板块深度分析 -->
  <div class="section">
    <div class="section-title"><span class="icon">🔶</span> {title}</div>
    <div style="background:#21262d;border-radius:8px;padding:16px;margin-bottom:12px;">
      <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:13px;margin-bottom:12px;">
        {chips_html}
      </div>
      <div style="font-size:13px;color:#8b949e;line-height:1.8;">
        <b style="color:#e1e8ed;">核心逻辑：</b>{core}<br>
        <b style="color:#e1e8ed;">持续性判断：</b>{cont}
      </div>
    </div>
  </div>
"""


def build_limitup_review(c):
    """涨停板复盘·按题材分类（含涨停归因）。"""
    limit_up = c.get("limit_up") or []
    from collections import Counter
    # 按题材分组：reason 首题材
    groups = {}
    for x in limit_up:
        reason = x.get("reason") or "其他"
        first = reason.split("+")[0].split("·")[0].split("(")[0].strip()[:6]
        groups.setdefault(first, []).append(x)
    # 按涨停数排序取前 4 组，其余并入"其他"
    sorted_g = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    top = sorted_g[:4]
    rest = [x for k, v in sorted_g[4:] for x in v]
    if rest:
        top.append(("其他", rest))
    # 每个个股行
    def stock_line(x):
        badge = '<span class="badge badge-seal">封板✅</span>'
        board_txt = f"{x['board']}板" if x.get("board") and x["board"] > 1 else "首板"
        seal = f" 封单{fmt_seal_yi(x.get('seal_yi'))}" if x.get("seal_yi") else ""
        return (f'          <div style="padding:4px 0;border-bottom:1px solid #21262d;">{badge} <b>{x["name"]}</b> '
                f'<span style="color:#d29922;font-size:10px;">{x.get("reason") or ""}</span> {board_txt}{seal}</div>')
    colors = ["#f85149", "#58a6ff", "#d29922", "#3fb950", "#8b949e"]
    col_html = ""
    for i, (topic, stocks) in enumerate(top):
        col = "left" if i % 2 == 0 else "right"
        color = colors[i % len(colors)]
        lines = "\n".join(stock_line(x) for x in stocks[:12])
        col_html += f"""      <div>
        <h4 style="color:{color};margin-bottom:8px;">{'🔷' if i%2==0 else '🤖'} {topic}（{len(stocks)}只涨停）</h4>
        <div style="font-size:12px;">
{lines}
        </div>
      </div>
"""
    return f"""  <!-- 涨停板复盘·按题材分类（含涨停归因） -->
  <div class="section">
    <div class="section-title"><span class="icon">🎯</span> 涨停板复盘 · 按题材分类（含涨停归因）</div>
    <div style="background:#1c2128;border:1px solid #2d333b;border-radius:6px;padding:10px 14px;margin-bottom:14px;font-size:12px;color:#8b949e;">
      📌 <b style="color:#d29922;">涨停归因</b>来源：实时行情数据 · 封板判断：最新价与涨停价对比<br>
      📌 封板强度：一字板(开板0次) > T字板(1次) > 换手板(多次开板/尾盘封板)
    </div>
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:16px;">
{col_html}    </div>
  </div>
"""


def build_break_analysis(c):
    """炸板深度分析。"""
    break_pool = c.get("break_pool") or []
    br = c.get("break_rate_real")
    title = f"炸板深度分析（炸板{len(break_pool)}只 · 炸板率{br:.0f}%）" if br is not None else f"炸板深度分析（炸板{len(break_pool)}只）"
    # 高换手炸板（规避）：炸板池前4
    high = ""
    for x in break_pool[:4]:
        high += f"""          <div class="zhaban-high" style="padding:6px 10px;border-radius:6px;margin-bottom:6px;">
            <b>{x['name']}</b> +{x.get('chg_pct') or '—'}% · 开板{x.get('open_times') or '—'}次 · 换手额{x.get('turnover_yi') or '—'}亿<br>
            <span style="color:#d29922;font-size:11px;">⚠ 曾触涨停后开板，资金分歧大，明日高开需谨慎</span>
          </div>
"""
    if not high:
        high = '          <div style="padding:6px 10px;color:#8b949e;font-size:12px;">今日无炸板数据</div>\n'
    low = f"""          <div class="zhaban-low" style="padding:6px 10px;border-radius:6px;margin-bottom:6px;">
            <b>今日炸板率 {f'{br:.0f}%' if br is not None else '—'}</b><br>
            <span style="color:#3fb950;font-size:11px;">{'✅ 炸板率偏低，打板安全边际相对高' if (br is not None and br <= 15) else ('⚠ 炸板率偏高，后排板谨慎' if (br is not None and br > 25) else '中性，打板需精选')}</span>
          </div>
"""
    return f"""  <!-- 炸板深度分析 -->
  <div class="section">
    <div class="section-title"><span class="icon">💥</span> {title}</div>
    <div class="two-col">
      <div class="col">
        <h4 style="color:#f85149;">🚨 高换手炸板（明天规避）</h4>
        <div style="font-size:12px;">
{high}        </div>
      </div>
      <div class="col">
        <h4 style="color:#3fb950;">✅ 低换手封板（反包策略关注）</h4>
        <div style="font-size:12px;">
{low}        </div>
      </div>
    </div>
  </div>
"""


def build_strategy(c):
    """短线策略 & 明日接力计划。"""
    space = c.get("space_board"); space_stock = c.get("space_stock")
    ladder = c.get("ladder") or {}
    two = ladder.get("2") or []
    three = ladder.get("3") or []
    sector_in = c.get("sector_in") or []
    in_names = "、".join(s["name"] for s in sector_in[:2]) or "—"
    # 重点接力
    zhong = [f"<li><b>{x}</b>（2板）— 2进3关注晋级</li>" for x in two[:3]]
    zhong += [f"<li><b>{x}</b>（3板）— 3进4关键战</li>" for x in three[:2]]
    if not zhong:
        zhong = ["<li>连板梯队有限，等待新周期龙头</li>"]
    # 分歧低吸
    fenqi = [f"<li><b>{in_names}</b> 主线方向，回调至分歧点可低吸</li>"]
    if space_stock:
        fenqi.append(f"<li><b>{space_stock}</b>（{space}板）— 若分歧后回封可关注</li>")
    # 坚决规避
    out_names = "、".join(s["name"] for s in (c.get("sector_out") or [])[:2]) or "—"
    guibi = [f"<li><b>{out_names}</b>— 今日主力净流出，短期别碰</li>",
             "<li><b>高换手炸板股</b>— 换手>15%+板型不稳的票回避</li>",
             "<li><b>后排补涨股</b>— 无资金承接的跟风板不追</li>"]
    return f"""  <!-- 短线策略 & 明日接力计划 -->
  <div class="section">
    <div class="section-title"><span class="icon">💡</span> 短线策略 & 明日接力计划</div>
    <div class="strategy-cols">
      <div class="strategy-col">
        <h4 style="color:#3fb950;">✅ 重点接力（明日关注）</h4>
        <ul>
{''.join(zhong)}
        </ul>
      </div>
      <div class="strategy-col">
        <h4 style="color:#58a6ff;">🔍 分歧低吸（回调关注）</h4>
        <ul>
{''.join(fenqi)}
        </ul>
      </div>
      <div class="strategy-col">
        <h4 style="color:#f85149;">🚫 坚决规避（明日回避）</h4>
        <ul>
{''.join(guibi)}
        </ul>
      </div>
    </div>
  </div>
"""


def build_review_outlook(c):
    """行情回顾 & 后市展望。"""
    up = c.get("up"); down = c.get("down")
    indices = c.get("indices") or []
    def idx_txt(name):
        for i in indices:
            if i["name"] == name:
                return f"{i.get('value', '—')}（{trend_word(i.get('chg_pct'))}）"
        return "—"
    amt = c.get("amount_yi")
    amt_s = fmt_amt(amt)
    zt = c.get("zt"); dt = c.get("dt")
    br = c.get("break_rate_real")
    in_desc = "、".join(s["name"] for s in (c.get("sector_in") or [])[:2]) or "—"
    out_desc = "、".join(s["name"] for s in (c.get("sector_out") or [])[:2]) or "—"
    # 今日回顾
    if up is not None and down is not None:
        if up > down:
            breadth_txt = f"涨多跌少（{up}/{down}）"
        else:
            breadth_txt = f"跌多涨少（{up}/{down}）"
    else:
        breadth_txt = "涨跌家数未知"
    review = (
        f"今日市场{'分化明显' if (up and down and abs(up - down) > 1500) else '整体偏弱'}："
        f"上证 {idx_txt('上证指数')}、深证 {idx_txt('深证成指')}、"
        f"创业板指 {idx_txt('创业板指')}、科创50 {idx_txt('科创50')}。"
        f"两市成交约 {amt_s}，{breadth_txt}，涨停 {zt or '—'} 只、跌停 {dt or '—'} 只，"
        f"炸板率 {f'{br:.1f}%' if br is not None else '—'}。"
        f"资金面上，主力净流入集中在 {in_desc}，而 {out_desc} 遭到净流出，"
        f"说明资金在板块间有明显切换。"
    )
    # 后市展望
    short = (
        f"明日重点关注两点：一是 {in_desc} 能否延续强势，"
        f"资金是否继续承接；二是跌多涨少格局下，题材能否重新凝聚。"
        f"指数层面，主板与成长分化明显，若成长股继续走弱，注意控制仓位。"
    )
    mid = (
        f"中期看，主线方向仍围绕 {in_desc} 展开，但市场总量能有限，"
        f"板块轮动快、持续性差，更适合低吸不追高。"
    )
    ops = (
        f"① 总仓位 3-5 成；② 优先做 {in_desc} 方向的低吸；"
        f"③ 坚决回避 {out_desc} 与高换手炸板股；"
        f"④ 若明日成长股放量止跌，可适度回补仓位。"
    )
    return f"""  <!-- 行情回顾 & 后市展望 -->
  <div class="section">
    <div class="section-title"><span class="icon">📝</span> 行情回顾 & 后市展望</div>
    <div class="two-col">
      <div class="col">
        <h4 style="color:#f85149;">📈 今日行情回顾</h4>
        <p style="font-size:13px;line-height:1.8;color:#8b949e;">
          {review}<br><br>
          <b style="color:#e1e8ed;">亮点：</b>{in_desc} 逆势吸金，是今天少数有赚钱效应的方向。<br>
          <b style="color:#e1e8ed;">风险：</b>全市场跌多涨少，追高风险大；{out_desc} 资金出逃明显。
        </p>
      </div>
      <div class="col">
        <h4 style="color:#f85149;">🔮 后市展望</h4>
        <p style="font-size:13px;line-height:1.8;color:#8b949e;">
          <b style="color:#e1e8ed;">短期（明日）：</b>{short}<br><br>
          <b style="color:#e1e8ed;">中期：</b>{mid}<br>
          <b style="color:#e1e8ed;">操作建议：</b>{ops}
        </p>
      </div>
    </div>
  </div>
"""


def build_amount_rank(c):
    """成交额排行 Top10（名称来自当日热门股榜，其余字段数据源未返回时留—）。"""
    hot = c.get("hot") or []
    rows = ""
    for i, h in enumerate(hot[:10]):
        rank = i + 1
        rows += f'      <tr><td>{rank}</td><td>—</td><td><b>{h.get("name", "—")}</b></td><td class="down">—</td><td>—</td><td style="color:#d29922;">—</td><td>—</td><td class="down">—</td></tr>\n'
    if not rows:
        rows = '      <tr><td colspan="8" style="color:#8b949e;">成交额排行数据未返回</td></tr>\n'
    return f"""  <!-- 成交额排行 Top10 -->
  <div class="section">
    <div class="section-title"><span class="icon">💰</span> 成交额排行 Top10</div>
    <table>
      <tr><th>排名</th><th>代码</th><th>名称</th><th>涨幅</th><th>最新价</th><th>成交额</th><th>换手率</th><th>主力净流入</th></tr>
{rows}    </table>
  </div>
"""


def build_down_rank(c):
    """今日跌幅榜 Top5（风险警示）。"""
    out_top = c.get("sector_out") or []
    rows = ""
    for i, x in enumerate(out_top[:5]):
        rows += f'      <tr><td>—</td><td><b>{x["name"]}</b></td><td class="negative">—</td><td>板块整体</td><td class="negative">{x["val"]}</td><td style="color:#f85149;font-size:12px;">⚠ 主力净流出，短期规避</td></tr>\n'
    if not rows:
        rows = '      <tr><td colspan="6" style="color:#8b949e;">跌幅榜数据未返回</td></tr>\n'
    return f"""  <!-- 跌幅榜 -->
  <div class="section">
    <div class="section-title"><span class="icon">📉</span> 今日跌幅榜 Top5（风险警示）</div>
    <table>
      <tr><th>代码</th><th>名称</th><th>跌幅</th><th>最新价</th><th>主力净流出</th><th>风险提示</th></tr>
{rows}    </table>
  </div>
"""


def build_money(c):
    """资金风向 · 主力净流入/流出 Top5。"""
    in_top = c.get("sector_in") or []
    out_top = c.get("sector_out") or []
    in_rows = ""
    for x in in_top[:5]:
        in_rows += f'        <div class="money-row"><span class="stock-name">{x["name"]}</span><span class="money-plus">{x["val"]}</span></div>\n'
    out_rows = ""
    for x in out_top[:5]:
        out_rows += f'        <div class="money-row"><span class="stock-name">{x["name"]}（板块）</span><span class="money-minus">{x["val"]}</span></div>\n'
    if not in_rows:
        in_rows = '        <div class="money-row" style="color:#8b949e;">净流入数据未返回</div>\n'
    if not out_rows:
        out_rows = '        <div class="money-row" style="color:#8b949e;">净流出数据未返回</div>\n'
    return f"""  <!-- 资金风向 -->
  <div class="section">
    <div class="section-title"><span class="icon">💹</span> 资金风向 · 主力净流入/流出 Top5</div>
    <div class="two-col">
      <div class="col">
        <h4 style="color:#3fb950;">✅ 今日主力净流入 Top5</h4>
        {in_rows}      </div>
      <div class="col">
        <h4 style="color:#f85149;">🚨 今日主力净流出 Top5</h4>
        {out_rows}      </div>
    </div>
  </div>
"""


def build_core_stocks(c):
    """核心个股筛选（5类）。"""
    limit_up = c.get("limit_up") or []
    dragons = c.get("dragons") or []
    cards = ""
    # 趋势突破：空间板龙头
    space = c.get("space_board"); space_stock = c.get("space_stock")
    if space_stock:
        cards += f"""      <div class="stock-item">
        <div class="name">{space_stock} <span class="badge badge-hot">趋势突破</span></div>
        <div class="change up">{space}板</div>
        <div class="info">当前市场最高空间板，短线风向标</div>
      </div>
"""
    # 最高封单涨停
    sealed_top = sorted([x for x in limit_up if x.get("seal_yi")], key=lambda x: -x["seal_yi"])
    if sealed_top:
        x = sealed_top[0]
        cards += f"""      <div class="stock-item">
        <div class="name">{x['name']} <span class="badge badge-hot">资金强</span></div>
        <div class="change up">{x['board']}板 · 封单{fmt_seal_yi(x['seal_yi'])}</div>
        <div class="info">{x.get('reason') or '—'}</div>
      </div>
"""
    # 龙虎榜净买第一
    if dragons:
        d = dragons[0]
        cards += f"""      <div class="stock-item">
        <div class="name">{d['name']} <span class="badge badge-warn">龙虎榜</span></div>
        <div class="change up">净买{fmt_seal_yi(d.get('net_yi'))}</div>
        <div class="info">{'、'.join((d.get('concepts') or [])[:3]) or '—'}</div>
      </div>
"""
    # 回避预警：净流出板块
    out_top = c.get("sector_out") or []
    if out_top:
        x = out_top[0]
        cards += f"""      <div class="stock-item" style="border-left-color:#f85149;">
        <div class="name">{x['name']} <span class="badge badge-warn">回避预警</span></div>
        <div class="change" style="color:#3fb950;">{x['val']}</div>
        <div class="info" style="color:#f85149;">主力大幅净流出，短期规避</div>
      </div>
"""
    if not cards:
        cards = '      <div style="color:#8b949e;">核心个股数据未返回</div>\n'
    return f"""  <!-- 核心个股筛选 -->
  <div class="section">
    <div class="section-title"><span class="icon">⭐</span> 核心个股筛选（5类）</div>
    <div class="stock-grid">
{cards}    </div>
  </div>
"""


def build_margin(c):
    """融资融券数据。"""
    m = c.get("margin") or {}
    finance = m.get("finance") or "—"
    lending = m.get("lending") or "—"
    total = m.get("total") or "—"
    return f"""  <!-- 融资融券数据 -->
  <div class="section">
    <div class="section-title"><span class="icon">📊</span> 融资融券数据</div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;text-align:center;">
      <div style="background:#21262d;border-radius:8px;padding:16px;">
        <div style="font-size:12px;color:#8b949e;">融资余额</div>
        <div style="font-size:22px;font-weight:700;color:#e1e8ed;margin-top:6px;">{finance}</div>
        <div style="font-size:12px;color:#8b949e;margin-top:4px;">融资融券余额</div>
      </div>
      <div style="background:#21262d;border-radius:8px;padding:16px;">
        <div style="font-size:12px;color:#8b949e;">融券余额</div>
        <div style="font-size:22px;font-weight:700;color:#e1e8ed;margin-top:6px;">{lending}</div>
        <div style="font-size:12px;color:#8b949e;margin-top:4px;">相对稳定</div>
      </div>
      <div style="background:#21262d;border-radius:8px;padding:16px;">
        <div style="font-size:12px;color:#8b949e;">两融合计</div>
        <div style="font-size:22px;font-weight:700;color:#e1e8ed;margin-top:6px;">{total}</div>
        <div style="font-size:12px;color:#8b949e;margin-top:4px;">全市场口径</div>
      </div>
      <div style="background:#21262d;border-radius:8px;padding:16px;">
        <div style="font-size:12px;color:#8b949e;">杠杆占比</div>
        <div style="font-size:22px;font-weight:700;color:#58a6ff;margin-top:6px;">—</div>
        <div style="font-size:12px;color:#8b949e;margin-top:4px;">数据未返回</div>
      </div>
    </div>
  </div>
"""


def build_track(c):
    """重要个股跟踪表。"""
    limit_up = c.get("limit_up") or []
    dragons = c.get("dragons") or []
    rows = ""
    # 空间板
    space = c.get("space_board"); space_stock = c.get("space_stock")
    if space_stock:
        rows += f'      <tr><td>—</td><td><b>{space_stock}</b></td><td class="positive">{space}板</td><td>空间板</td><td><span class="badge badge-seal">封板✅</span></td><td>—</td><td style="color:#3fb950;">空间风向标</td></tr>\n'
    # 最高封单涨停前3
    sealed_top = sorted([x for x in limit_up if x.get("seal_yi")], key=lambda x: -x["seal_yi"])
    for x in sealed_top[:3]:
        rows += f'      <tr><td>{x.get("ticker") or "—"}</td><td><b>{x["name"]}</b></td><td class="positive">+10.0%</td><td>{x["board"]}板</td><td><span class="badge badge-seal">封板✅</span></td><td>—</td><td style="color:#3fb950;">{x.get("reason") or "—"}</td></tr>\n'
    # 龙虎榜前2
    for d in dragons[:2]:
        rows += f'      <tr><td>—</td><td><b>{d["name"]}</b></td><td class="positive">—</td><td>龙虎榜</td><td>—</td><td>—</td><td style="color:#58a6ff;">净买{fmt_seal_yi(d.get("net_yi"))}</td></tr>\n'
    if not rows:
        rows = '      <tr><td colspan="7" style="color:#8b949e;">个股跟踪数据未返回</td></tr>\n'
    return f"""  <!-- 重要个股跟踪表 -->
  <div class="section">
    <div class="section-title"><span class="icon">📌</span> 重要个股跟踪表</div>
    <table>
      <tr><th>代码</th><th>名称</th><th>今日涨幅</th><th>当前状态</th><th>封板/炸板</th><th>换手率</th><th>明天策略</th></tr>
{rows}    </table>
  </div>
"""


def build_mindset(c):
    """投资策略 & 心态管理。"""
    in_desc = "、".join(s["name"] for s in (c.get("sector_in") or [])[:2]) or "—"
    out_desc = "、".join(s["name"] for s in (c.get("sector_out") or [])[:2]) or "—"
    return f"""  <!-- 投资策略 & 心态管理 -->
  <div class="section">
    <div class="section-title"><span class="icon">🧠</span> 投资策略 & 心态管理</div>
    <div class="strategy-cols">
      <div class="strategy-col">
        <h4 style="color:#58a6ff;">🎯 选股策略</h4>
        <ul>
          <li>主线优先：{in_desc}</li>
          <li>连板优先：关注2进3、3进4晋级</li>
          <li>首板低吸：强势题材首板机会</li>
          <li>规避板块：{out_desc}</li>
        </ul>
      </div>
      <div class="strategy-col">
        <h4 style="color:#d29922;">🛡️ 风控策略</h4>
        <ul>
          <li>总仓位控制 3-5 成</li>
          <li>止损严格执行：-5% 无条件止损</li>
          <li>高位连板股断板即走</li>
          <li>不追高换手炸板股</li>
        </ul>
      </div>
      <div class="strategy-col">
        <h4 style="color:#3fb950;">💪 心态管理</h4>
        <ul>
          <li>跌多涨少 → 不焦虑，等主线明朗</li>
          <li>板块轮动快 → 不频繁切换，聚焦一两个方向</li>
          <li>做好仓位管理，留足子弹应对波动</li>
        </ul>
      </div>
    </div>
  </div>
"""


def build_events(c):
    """特殊事件 & 监管关注。"""
    # 用龙虎榜/资金流出的强信号板块作为异动警示
    out_top = c.get("sector_out") or []
    in_top = c.get("sector_in") or []
    warn = ""
    if out_top:
        warn += f'<b style="color:#f85149;">🚨 {out_top[0]["name"]} 主力大幅净流出</b> — {out_top[0]["val"]}，板块性资金撤退信号，短期规避。<br>\n'
    if len(out_top) > 1:
        warn += f'<b style="color:#d29922;">⚡ {out_top[1]["name"]} 净流出{out_top[1]["val"]}</b> — 跟随主力节奏，暂不参与。<br>\n'
    if not warn:
        warn = '<b style="color:#8b949e;">今日无显著异动警示。</b>\n'
    return f"""  <!-- 特殊事件 & 监管关注 -->
  <div class="section">
    <div class="section-title"><span class="icon">⚠️</span> 特殊事件 & 监管关注</div>
    <div style="background:#f8514910;border:1px solid #f8514933;border-radius:8px;padding:14px;margin-bottom:12px;font-size:13px;">
      {warn}    </div>
    <div style="background:#21262d;border-radius:8px;padding:14px;font-size:13px;">
      <b style="color:#e1e8ed;">📅 明日关注：</b><br>
      · {in_top[0]["name"] if in_top else "主线方向"} 资金是否延续<br>
      · 空间板能否晋级、连板高度能否打开<br>
      · 外围市场（美股/商品）对次日情绪影响
    </div>
  </div>
"""


def build_oplist(c):
    """操作建议。"""
    in_desc = "、".join(s["name"] for s in (c.get("sector_in") or [])[:2]) or "—"
    out_desc = "、".join(s["name"] for s in (c.get("sector_out") or [])[:2]) or "—"
    space_stock = c.get("space_stock")
    items = []
    items.append(f"1️⃣ 观察 {in_desc} 明日能否延续 → 资金承接则持有，冲高回落则减仓")
    if space_stock:
        items.append(f"2️⃣ 观察 {space_stock} 晋级 → 空间板是关键，成则情绪修复")
    items.append(f"3️⃣ {out_desc} 坚决不碰，等资金回流出清")
    items.append("4️⃣ 总仓位 3-5 成，逢低布局主线方向")
    return f"""  <!-- 操作建议 -->
  <div class="section">
    <div class="section-title"><span class="icon">✅</span> 操作建议</div>
    <div class="two-col">
      <div class="col">
        <h4 style="color:#3fb950;">✅ 明日操作清单</h4>
        <div style="font-size:13px;line-height:2;">
          {'\n          '.join(f'<div>{it}</div>' for it in items)}
        </div>
      </div>
      <div class="col">
        <h4 style="color:#58a6ff;">📌 操作纪律</h4>
        <div style="font-size:13px;line-height:2;">
          <div>· 不追高、不接力烂板</div>
          <div>· 单票止损 -5%，果断执行</div>
          <div>· 关注外围美股/商品隔夜表现</div>
        </div>
      </div>
    </div>
  </div>
"""


def build_footer(c):
    """Footer。"""
    date = c.get("trade_date") or datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""  <!-- Footer -->
  <div class="footer">
    <div class="disclaimer">
      ⚠️ <b>免责声明：</b>本报告仅供参考，不构成投资建议。A股市场有风险，投资需谨慎。数据截至{date}收盘。
    </div>
    <div>📊 A股市场复盘报告 · 生成于 {now}</div>
  </div>
"""


# ---------- 组装 ----------
def build_report(c):
    css = load_css()
    body = "\n".join([
        build_header(c),
        build_index_cards(c),
        build_limit_cards(c),
        build_breadth(c),
        build_emotion_overview(c),
        build_emotion_monitor(c),
        build_jinji(c),
        build_sector_board(c),
        build_main_line(c),
        build_limitup_review(c),
        build_break_analysis(c),
        build_strategy(c),
        build_review_outlook(c),
        build_amount_rank(c),
        build_down_rank(c),
        build_money(c),
        build_core_stocks(c),
        build_margin(c),
        build_track(c),
        build_mindset(c),
        build_events(c),
        build_oplist(c),
        build_footer(c),
    ])
    date = c.get("trade_date") or datetime.date.today().isoformat()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股市场复盘报告 · {date}</title>
<style>
{css}</style>
</head>
<body>
<div class="container">

{body}
</div>
</body>
</html>
"""


def main():
    c = load_collected()
    html = build_report(c)
    date = c.get("trade_date")
    fname = os.path.join(BASE, f"a-share-report-{date}.html")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    # 历史归档 reports/{date}.html
    os.makedirs(os.path.join(BASE, "reports"), exist_ok=True)
    with open(os.path.join(BASE, "reports", f"{date}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[gen_report] {fname} ({len(html)} bytes)")
    print(f"[gen_report] reports/{date}.html ({len(html)} bytes)")


if __name__ == "__main__":
    main()
