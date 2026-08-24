# -*- coding: utf-8 -*-
"""
gen_index.py — 门户首页生成（重做版）

index.html = 门户：Header + 最新报告摘要卡片 + ECharts 三图（涨跌/板块资金/连板梯队）+ 归档入口。
引用 reports/ 与 a-share-report-*.html 的最新报告。
"""
import json, os, re, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
COLLECTED = os.path.join(BASE, "collected.json")
ARCHIVE = os.path.join(BASE, "archive.json")


def load_json(p):
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def trend_word(chg):
    try:
        v = float(str(chg).rstrip("%"))
    except Exception:
        return "—"
    return f"+{v}% ▲" if v > 0 else (f"{v}% ▼" if v < 0 else "0%")


def cls_of(chg):
    try:
        return "up" if float(str(chg).rstrip("%")) >= 0 else "down"
    except Exception:
        return "down"


def build(c):
    date = c.get("trade_date") or datetime.date.today().isoformat()
    up = c.get("up"); down = c.get("down"); zt = c.get("zt")
    indices = c.get("indices") or []
    sector_in = c.get("sector_in") or []
    sector_out = c.get("sector_out") or []
    ladder = c.get("ladder") or {}
    amount = c.get("amount_yi")
    # Header 市场概况 tag
    if up is not None and down is not None:
        tag = "🔥 涨停潮" if (zt and zt >= 40) else ("📈 普涨" if up > down else "📉 跌多涨少")
    else:
        tag = "—"
    # 指数卡
    cards = ""
    for name in ["上证指数", "深证成指", "创业板指", "科创50"]:
        idx = next((x for x in indices if x["name"] == name), None)
        if idx and idx.get("value") is not None:
            cards += f'''    <div class="card"><div class="label">{name}</div><div class="value {cls_of(idx.get('chg_pct'))}">{idx['value']:.2f}</div><div class="sub {cls_of(idx.get('chg_pct'))}">{trend_word(idx.get('chg_pct'))}</div></div>
'''
        else:
            cards += f'''    <div class="card"><div class="label">{name}</div><div class="value">—</div><div class="sub">—</div></div>
'''
    # ECharts 数据
    fund_in = [{"name": s["name"], "val": s.get("val_yi", 0), "out": False} for s in sector_in[:5]]
    fund_out = [{"name": s["name"], "val": -abs(s.get("val_yi", 0)), "out": True} for s in sector_out[:5]]
    fund = fund_in + fund_out
    ladder_list = [{"tier": f"{k}进{int(k)+1}", "num": len(v)} for k, v in sorted(ladder.items(), key=lambda kv: int(kv[0]))]
    data_json = json.dumps({
        "up": up, "down": down, "zt": zt,
        "fund": fund,
        "ladder": ladder_list,
        "amount": f"{amount:.2f}万亿" if amount else "—",
    }, ensure_ascii=False)
    # 最新报告链接
    latest_link = f"reports/{date}.html"
    amt_txt = f"{amount:.2f}万亿" if amount else "—"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 A股市场复盘报告 · 门户</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0b0e11; color: #e1e8ed; font-family: 'PingFang SC','Microsoft YaHei',sans-serif; line-height: 1.6; padding: 0; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
  .header {{ background: linear-gradient(135deg, #1a1e24 0%, #0d1117 100%); border: 1px solid #2d333b; border-radius: 12px; padding: 32px; margin-bottom: 24px; text-align: center; }}
  .header h1 {{ font-size: 28px; color: #f85149; margin-bottom: 8px; }}
  .header .date {{ color: #8b949e; font-size: 15px; margin-bottom: 12px; }}
  .header .tags {{ display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; }}
  .header .tag {{ background: #161b22; border: 1px solid #2d333b; border-radius: 20px; padding: 4px 14px; font-size: 12px; color: #8b949e; }}
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: #161b22; border: 1px solid #2d333b; border-radius: 10px; padding: 20px; text-align: center; }}
  .card .label {{ font-size: 12px; color: #8b949e; margin-bottom: 8px; }}
  .card .value {{ font-size: 26px; font-weight: 700; }}
  .card .sub {{ font-size: 12px; color: #8b949e; margin-top: 6px; }}
  .up {{ color: #f85149; }}
  .down {{ color: #3fb950; }}
  .section {{ background: #161b22; border: 1px solid #2d333b; border-radius: 10px; padding: 24px; margin-bottom: 20px; }}
  .section-title {{ font-size: 17px; font-weight: 700; color: #e1e8ed; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid #21262d; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .chart-box {{ background: #161b22; border: 1px solid #2d333b; border-radius: 10px; padding: 16px; }}
  .cb-title {{ font-size: 13px; color: #8b949e; margin-bottom: 8px; }}
  .echart {{ width: 100%; height: 260px; }}
  .big {{ text-align: center; }}
  .big-num {{ font-size: 48px; font-weight: 700; }}
  .entry {{ display: block; background: #161b22; border: 1px solid #2d333b; border-radius: 10px; padding: 20px; text-align: center; color: #e1e8ed; text-decoration: none; transition: border-color .2s; }}
  .entry:hover {{ border-color: #f85149; }}
  .entry .btn {{ display: inline-block; margin-top: 8px; background: #f85149; color: #fff; border-radius: 6px; padding: 6px 24px; font-size: 14px; }}
  .arch-link {{ display: inline-block; margin-top: 12px; color: #58a6ff; text-decoration: none; font-size: 13px; }}
  @media (max-width: 768px) {{ .cards {{ grid-template-columns: repeat(2, 1fr); }} .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 A股市场复盘报告</h1>
    <div class="date">📅 {date} · 数据已更新</div>
    <div class="tags">
      <span class="tag">今日复盘</span>
      <span class="tag">A股市场</span>
      <span class="tag">短线情绪</span>
      <span class="tag" style="border-color:#d29922;color:#d29922;">{tag}</span>
    </div>
  </div>

  <div class="cards">
{cards}  </div>

  <div class="grid">
    <div class="chart-box"><div class="cb-title">涨跌分布（家数）</div><div class="echart" id="chartUpDown"></div></div>
    <div class="chart-box"><div class="cb-title">板块主力资金净流入(亿)</div><div class="echart" id="chartFund"></div></div>
    <div class="chart-box"><div class="cb-title">连板梯队（成功数）</div><div class="echart" id="chartLadder"></div></div>
    <div class="big" style="display:flex;flex-direction:column;justify-content:center;align-items:center;">
      <div class="big-num up">{up if up is not None else '—'} <span style="font-size:16px;color:#8b949e;">涨</span></div>
      <div class="big-num down" style="margin-top:8px;">{down if down is not None else '—'} <span style="font-size:16px;color:#8b949e;">跌</span></div>
      <div style="margin-top:12px;color:#8b949e;font-size:14px;">涨停 {zt if zt is not None else '—'} · 成交 {amt_txt}</div>
    </div>
  </div>

  <a class="entry" href="{latest_link}">
    📊 查看完整复盘报告（{date}）<br>
    <span class="btn">打开报告 →</span>
  </a>
  <div style="text-align:center;margin-top:16px;">
    <a class="arch-link" href="archive.html">📚 历史归档</a>
  </div>

  <div class="footer" style="text-align:center;padding:20px;color:#6e7681;font-size:12px;border-top:1px solid #21262d;margin-top:24px;">
    ⚠️ 本报告仅供参考，不构成投资建议。
  </div>
</div>
<script>
(function(){{
  var D = {data_json};
  var upC = new echarts.init(document.getElementById('chartUpDown'));
  upC.setOption({{
    tooltip: {{}},
    series: [{{ type:'pie', radius:['40%','70%'], label:{{color:'#e1e8ed'}},
      data: [
        {{value:D.up, name:'上涨', itemStyle:{{color:'#f85149'}}}},
        {{value:D.down, name:'下跌', itemStyle:{{color:'#3fb950'}}}},
      ] }}],
    legend: {{ textStyle:{{color:'#8b949e'}} }}
  }});
  var fC = new echarts.init(document.getElementById('chartFund'));
  fC.setOption({{
    tooltip: {{}},
    grid: {{ left:60, right:20, top:20, bottom:40 }},
    xAxis: {{ type:'value', axisLabel:{{color:'#8b949e'}} }},
    yAxis: {{ type:'category', data:D.fund.map(function(x){{return x.name;}}), axisLabel:{{color:'#8b949e'}} }},
    series: [{{ type:'bar', data:D.fund.map(function(x){{return {{value:x.val, itemStyle:{{color:x.out?'#3fb950':'#f85149'}}}};}}), barWidth:12 }}]
  }});
  var lC = new echarts.init(document.getElementById('chartLadder'));
  lC.setOption({{
    tooltip: {{}},
    grid: {{ left:50, right:20, top:20, bottom:40 }},
    xAxis: {{ type:'category', data:D.ladder.map(function(x){{return x.tier;}}), axisLabel:{{color:'#8b949e'}} }},
    yAxis: {{ type:'value', axisLabel:{{color:'#8b949e'}} }},
    series: [{{ type:'bar', data:D.ladder.map(function(x){{return x.num;}}), itemStyle:{{color:'#d29922'}}, barWidth:20 }}]
  }});
  window.addEventListener('resize', function(){{ upC.resize(); fC.resize(); lC.resize(); }});
}})();
</script>
</body>
</html>
"""


def main():
    c = load_json(COLLECTED)
    if not c:
        print("[gen_index] collected.json 不存在")
        return
    html = build(c)
    with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[gen_index] index.html ({len(html)} bytes)")


if __name__ == "__main__":
    main()
