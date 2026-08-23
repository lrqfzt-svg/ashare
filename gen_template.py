# -*- coding: utf-8 -*-
"""
gen_template.py — 模板版（22模块·涨停/连板情绪专项）生成器
A股市场复盘报告模板克隆版：CSS / HTML 结构完全不变，仅替换数据。

用法：
  python3 gen_template.py                 # 用内置样例(8/21)生成 收盘复盘模板版_YYYY-MM-DD.html
  python3 gen_template.py data.json       # 用外部数据 JSON 生成
  python3 gen_template.py data.json out.html

数据契约见底部 SAMPLE_TEMPLATE_DATA（即 8/21 全部字段）。换一天只需替换该 JSON。
"""
import json, sys, os

# ============== CSS（与分享模板逐字一致，勿改） ==============
TEMPLATE_CSS = """  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0b0e11; color: #e1e8ed; font-family: 'PingFang SC','Microsoft YaHei',sans-serif; line-height: 1.6; padding: 0; }
  .container { max-width: 1100px; margin: 0 auto; padding: 20px; }

  /* Header */
  .header { background: linear-gradient(135deg, #1a1e24 0%, #0d1117 100%); border: 1px solid #2d333b; border-radius: 12px; padding: 32px; margin-bottom: 24px; text-align: center; }
  .header h1 { font-size: 28px; color: #f85149; margin-bottom: 8px; }
  .header .date { color: #8b949e; font-size: 15px; margin-bottom: 12px; }
  .header .tags { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; }
  .header .tag { background: #161b22; border: 1px solid #2d333b; border-radius: 20px; padding: 4px 14px; font-size: 12px; color: #8b949e; }

  /* Cards */
  .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #2d333b; border-radius: 10px; padding: 20px; text-align: center; }
  .card .label { font-size: 12px; color: #8b949e; margin-bottom: 8px; }
  .card .value { font-size: 26px; font-weight: 700; }
  .card .sub { font-size: 12px; color: #8b949e; margin-top: 6px; }
  .up { color: #f85149; }
  .down { color: #3fb950; }

  /* Section */
  .section { background: #161b22; border: 1px solid #2d333b; border-radius: 10px; padding: 24px; margin-bottom: 20px; }
  .section-title { font-size: 17px; font-weight: 700; color: #e1e8ed; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid #21262d; display: flex; align-items: center; gap: 8px; }
  .section-title .icon { font-size: 20px; }

  /* 2-col */
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .col { }
  .col h4 { font-size: 14px; color: #8b949e; margin-bottom: 10px; }

  /* Table */
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { background: #21262d; color: #8b949e; padding: 8px 10px; text-align: left; font-weight: 500; }
  td { padding: 8px 10px; border-bottom: 1px solid #21262d; }
  tr:hover { background: #1c2128; }
  .positive { color: #f85149; }
  .negative { color: #3fb950; }

  /* Badge */
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-right: 4px; }
  .badge-hot { background: #f8514920; color: #f85149; border: 1px solid #f8514933; }
  .badge-cold { background: #3fb95020; color: #3fb950; border: 1px solid #3fb95033; }
  .badge-warn { background: #d2992220; color: #d29922; border: 1px solid #d2992233; }
  .badge-seal { background: #3fb95020; color: #3fb950; border: 1px solid #3fb95033; }
  .badge-broken { background: #f8514920; color: #f85149; border: 1px solid #f8514933; }
  .attribution { color: #d29922; font-size: 10px; }
  .seal-time { color: #8b949e; font-size: 10px; }
  .seal-strength { color: #58a6ff; font-size: 10px; }

  /* Stock grid */
  .stock-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
  .stock-item { background: #21262d; border-radius: 8px; padding: 12px; border-left: 3px solid #f85149; }
  .stock-item .name { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
  .stock-item .info { font-size: 12px; color: #8b949e; }
  .stock-item .change { font-weight: 700; font-size: 15px; }

  /* Strategy columns */
  .strategy-cols { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
  .strategy-col { background: #21262d; border-radius: 8px; padding: 16px; }
  .strategy-col h4 { font-size: 14px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #2d333b; }
  .strategy-col ul { list-style: none; padding: 0; }
  .strategy-col li { font-size: 13px; padding: 4px 0; padding-left: 14px; position: relative; }
  .strategy-col li::before { content: '·'; position: absolute; left: 0; color: #8b949e; }

  /* Sentiment bar */
  .sentiment-bar { display: flex; height: 24px; border-radius: 12px; overflow: hidden; margin: 10px 0; }
  .sentiment-bar .bull { background: #f85149; }
  .sentiment-bar .bear { background: #3fb950; }
  .sentiment-bar .neutral { background: #6e7681; }

  /* Footer */
  .footer { text-align: center; padding: 20px; color: #6e7681; font-size: 12px; border-top: 1px solid #21262d; margin-top: 20px; }
  .disclaimer { background: #161b22; border: 1px solid #2d333b; border-radius: 8px; padding: 12px; margin-bottom: 16px; font-size: 12px; color: #8b949e; }

  /* 晋级率表格 */
  .jinji-table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 10px 0; }
  .jinji-table th { background: #21262d; padding: 8px; text-align: center; }
  .jinji-table td { padding: 8px; text-align: center; border-bottom: 1px solid #21262d; }
  .jinji-rate { font-size: 16px; font-weight: 700; }
  .jinji-high { color: #3fb950; }
  .jinji-low { color: #f85149; }
  .jinji-zero { color: #d29922; font-weight: 700; }

  /* 情绪指标 */
  .sentiment-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .sentiment-item { background: #21262d; border-radius: 8px; padding: 12px; }
  .sentiment-item .s-label { font-size: 12px; color: #8b949e; }
  .sentiment-item .s-value { font-size: 22px; font-weight: 700; margin-top: 4px; }

  /* 资金风向 */
  .money-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #21262d; font-size: 13px; }
  .money-row .stock-name { font-weight: 600; }
  .money-plus { color: #3fb950; }
  .money-minus { color: #f85149; }

  /* 通用网格类（替代内联 grid，便于手机断点覆盖） */
  .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
  .grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
  .limitup-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
  .table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .table-scroll table { min-width: 520px; }

  @media (max-width: 768px) {
    .container { padding: 12px; }
    .header { padding: 20px 16px; }
    .header h1 { font-size: 22px; }
    .section { padding: 16px; }
    .cards { grid-template-columns: repeat(2, 1fr); }
    .grid-4 { grid-template-columns: repeat(2, 1fr); }
    .grid-5 { grid-template-columns: repeat(2, 1fr); }
    .limitup-grid { grid-template-columns: 1fr; }
    .two-col { grid-template-columns: 1fr; }
    .strategy-cols { grid-template-columns: 1fr; }
    .sentiment-grid { grid-template-columns: 1fr; }
    .card .value { font-size: 22px; }
    .table-scroll table { min-width: 480px; }
  }

  @media (max-width: 420px) {
    .grid-4 { grid-template-columns: 1fr; }
    .grid-5 { grid-template-columns: 1fr; }
    .card .value { font-size: 20px; }
  }

  /* 炸板高亮 */
  .zhaban-high { background: #f8514915; border-left: 3px solid #f85149; }
  .zhaban-low { background: #3fb95015; border-left: 3px solid #3fb950; }

  /* 门户区（首页概览 + 图表 + 历史入口） */
  .portal { background: linear-gradient(135deg, #161b22 0%, #0d1117 100%); border: 1px solid #2d333b; border-radius: 12px; padding: 24px; margin-bottom: 24px; }
  .portal-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
  .portal-head .ph-title { font-size: 16px; font-weight: 700; color: #e1e8ed; }
  .portal-head .ph-updated { font-size: 12px; color: #8b949e; }
  .portal-head .ph-updated b { color: #d29922; }
  .portal-links { display: flex; gap: 10px; flex-wrap: wrap; }
  .portal-links a { color: #58a6ff; text-decoration: none; font-size: 13px; padding: 4px 12px; border: 1px solid #2d333b; border-radius: 20px; background: #161b22; }
  .portal-links a:hover { border-color: #58a6ff; }
  .charts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
  .chart-box { background: #161b22; border: 1px solid #2d333b; border-radius: 10px; padding: 14px; }
  .chart-box .cb-title { font-size: 13px; color: #8b949e; margin-bottom: 8px; text-align: center; }
  .chart-box .echart { width: 100%; height: 220px; }
  @media (max-width: 768px) {
    .charts { grid-template-columns: 1fr; }
    .chart-box .echart { height: 200px; }
  }"""

# ============== 样例数据（8/21 收盘，全部字段） ==============
SAMPLE_TEMPLATE_DATA = {
  "title": "A股市场复盘报告 · 2026-08-21",
  "date": "2026年08月21日（周五）",
  "source": "同花顺(涨停池/龙虎榜/指数) / 东方财富·妙想(资金流·融资融券·行业)",
  "tags": ["今日复盘","A股市场","短线情绪","数据已更新","⚡ 股指期货交割日·缩量1.88万亿·观望平衡"],
  "indices": [
    {"name":"上证指数","value":"3905.20","sub":"+0.04% ▲","cls":"up"},
    {"name":"深证成指","value":"14094.17","sub":"+0.87% ▲","cls":"up"},
    {"name":"创业板指","value":"3545.58","sub":"+1.43% ▲","cls":"up"},
    {"name":"科创50","value":"1653.56","sub":"+0.04% ▲","cls":"up"},
  ],
  "core_cards": [
    {"label":"🎯 触及涨停","value":"58","sub":"只（沪深京，东财全A涨停家数）","style":"#d2992244","vcolor":"#d29922"},
    {"label":"✅ 封板","value":"54","sub":"只（涨停封死·含题材标注）","style":"#3fb95044","vcolor":"#f85149"},
    {"label":"📊 涨停封板率","value":"93.1%","sub":"54/58 · 封板率偏高 打板友好","style":"#58a6ff44","vcolor":"#58a6ff"},
    {"label":"💥 炸板率","value":"6.9%","sub":"4/58 · 炸板率偏低 分歧小","style":"#f8514944","vcolor":"#3fb950"},
  ],
  "change_overview": {"up":"2431","down":"~2520","ratio":"0.96","amount":"1.88万亿","amount_sub":"沪深总成交 ▼-2000亿缩量","amount_cls":"#3fb950"},
  "emotion_panorama": [
    {"label":"连板总数","value":"11","sub":"2板10只+3板1只 非ST","cls":""},
    {"label":"空间板","value":"3板","sub":"汉森制药 创新药+中药","cls":"#f85149"},
    {"label":"封板率","value":"93.1%","sub":"偏高 打板环境温和","cls":"#58a6ff"},
    {"label":"昨板表现","value":"待披露","sub":"连板晋级率见下方统计","cls":"#d29922"},
    {"label":"涨停/跌停","value":"54 / —","sub":"跌停家数当日接口未返回","cls":""},
  ],
  "emotion_monitor": [
    {"label":"炸板率","value":"6.9%","sub":"偏低！仅4只炸板，打板风险小","cls":"#3fb950"},
    {"label":"跌停家数","value":"—","sub":"当日跌停家数接口未返回","cls":"#d29922"},
    {"label":"连板晋级率","value":"3进4成功","sub":"汉森制药成功晋级3板，空间打开","cls":"#58a6ff"},
    {"label":"空间高度","value":"3板","sub":"从2板拓展至3板，趋势温和向上","cls":"#3fb950"},
    {"label":"封板数 / 炸板数","value":"54 / 4","sub":"炸板仅4只 分歧极小 精选即可","cls":""},
    {"label":"情绪周期判断","value":"缩量观望 · 结构分化","sub":"⚠ 股指期货交割日平静，多空平衡，资金观望","cls":"#d29922"},
  ],
  "jinji_rows": [
    {"tier":"1进2","base":"—","success":"10只","rate":"—","rate_cls":"jinji-low","rep":"通鼎互联/科森科技/宇环数控/双鹭药业/键凯科技/中关村等","signal":"首板基数大，2板质量尚可"},
    {"tier":"2进3","base":"—","success":"1只","rate":"—","rate_cls":"jinji-low","rep":"汉森制药(创新药+中药+中报预增)","signal":"唯一3板，主线+业绩逻辑"},
    {"tier":"3进4","base":"1只","success":"0只","rate":"0%","rate_cls":"jinji-zero","rep":"—","signal":"暂无4板个股，空间待拓展"},
    {"tier":"4进5","base":"0只","success":"0只","rate":"—","rate_cls":"","rep":"—","signal":"暂无更高连板"},
  ],
  "jinji_note": "⚠ <strong>核心观察：</strong>汉森制药以创新药+中药+中报预增逻辑晋级3板，成为全场最高板，打破前期2板压制。连板家数11只（2板10、3板1），首板43只，市场以首板套利为主、连板接力偏谨慎。炸板率仅6.9%（4只），封板率93.1%，打板环境温和。封单最强为士兰微（4.83亿，SiC功率半导体）、键凯科技（4.72亿，mRNA创新药2板）。主线呈\"半年报增长+科技(CPO/半导体/AI算力)+创新药+机器人\"多点开花，但整体缩量，资金偏观望。",
  "sector_top_in": [
    {"name":"通信设备","dir":"资金强","flow":"+76.34亿 🔥"},
    {"name":"半导体","dir":"资金强","flow":"+15.19亿"},
    {"name":"黄金","dir":"避险强","flow":"+5.39亿"},
    {"name":"有色金属（用户复盘领涨）","dir":"领涨","flow":"待披露"},
    {"name":"能源（用户复盘领涨）","dir":"领涨","flow":"待披露"},
  ],
  "sector_top_out": [
    {"name":"医药生物","dir":"领跌","flow":"-39.33亿 🚨"},
    {"name":"医疗服务/化学制药（用户复盘领跌）","dir":"领跌","flow":"待披露"},
    {"name":"—","dir":"—","flow":"—"},
    {"name":"—","dir":"—","flow":"—"},
    {"name":"—","dir":"—","flow":"—"},
  ],
  "sector_footnote": "* 板块涨跌幅逐板精确值当日接口未返回，此处以\"主力净流入/流出方向\"标注强弱（东财实测）；用户盘后复盘提及领涨贵金属/有色/能源、领跌医疗服务/化学制药，已并列标注。",
  "overseas": [
    {"region":"日本","name":"日经225","close":"66016.36","chg":"-0.3027%","cls":"negative"},
    {"region":"韩国","name":"韩国综合","close":"6912.95","chg":"0.881%","cls":"positive"},
    {"region":"美国","name":"道琼斯","close":"53277.01","chg":"0.9814%","cls":"positive"},
    {"region":"美国","name":"纳斯达克","close":"26180.46","chg":"0.4346%","cls":"positive"},
    {"region":"美国","name":"标普500","close":"7674.37","chg":"0.4346%","cls":"positive"},
  ],
  "overseas_note": "外围主要股指（数据截至 2026-08-21 收盘）：美三大指数集体收涨，亚太分化——日经小幅收跌、韩国KOSPI上涨。",
  "main_line": {
    "title": "主线板块深度分析 · 半年报增长 + 科技(CPO/半导体/AI算力) + 创新药 + 机器人",
    "chips": [
      "主线1·半年报增长：<b style=\"color:#f85149;\">6只涨停（汉森/星网锐捷/诺德等）</b>",
      "主线2·科技(CPO/半导体/AI算力)：<b style=\"color:#f85149;\">士兰微/可川/中瓷/共达等</b>",
      "主线3·创新药：<b style=\"color:#f85149;\">键凯/双鹭/北陆/中关村 2板集中</b>",
      "主线4·机器人/有色：<b style=\"color:#f85149;\">飞龙/精达/宇环/白银有色</b>",
      "最高板：<b style=\"color:#f85149;\">3板 汉森制药</b>",
      "炸板率：<b style=\"color:#d29922;\">6.9%</b>",
    ],
    "core_logic": "① 半年报增长线成为当日最强暗线——汉森制药（创新药+中药+中报预增）晋级3板全场最高，星网锐捷（数据中心交换机+CPO+半年报增长）、诺德股份（AI服务器铜箔+半年报扭亏）、科森科技（折叠屏+机器人+中报扭亏）等批量首板/2板。② 科技线资金强势：通信设备板块主力净流入+76.34亿、半导体+15.19亿，士兰微（SiC功率半导体，封单4.83亿）领涨。③ 创新药线2板集中（键凯科技/双鹭药业/中关村均2连板），mRNA+GLP-1催化。④ 机器人/有色贵金属受避险与事件驱动，白银有色、深中华A（黄金涨价）2板。",
    "continuity": "缩量1.88万亿、股指期货交割日，多空平衡观望。半年报密集披露期，\"业绩+题材\"双驱动更受资金青睐；科技（CPO/半导体）获主力大幅净流入，中期持续性较好。但整体缩量下追高需谨慎，炸板率虽低，连板高度仅3板，空间仍待打开。",
  },
  "limit_up_groups": [
    {"title":"科技线（CPO/通信设备/半导体/AI算力）","cls":"#d29922","stocks":[
      {"name":"士兰微","reason":"SiC+功率半导体+IDM","board":"首板","seal":"4.83亿"},
      {"name":"可川科技","reason":"硅光芯片+CPO+功能性器件","board":"首板","seal":"1.57亿"},
      {"name":"中瓷电子","reason":"CPO+电子陶瓷+央企","board":"首板","seal":"1.35亿"},
      {"name":"高新发展","reason":"功率半导体+成都国资","board":"首板","seal":"1.16亿"},
      {"name":"共达电声","reason":"AI算力+电声元器件","board":"首板","seal":"1.13亿"},
      {"name":"国光电器","reason":"AI眼镜+智能音箱+PCB","board":"首板","seal":"1.11亿"},
    ]},
    {"title":"业绩/半年报增长线","cls":"#58a6ff","stocks":[
      {"name":"汉森制药","reason":"创新药+中药+中报预增","board":"3连板","seal":"1.50亿"},
      {"name":"星网锐捷","reason":"数据中心交换机+CPO+半年报增长","board":"首板","seal":"2.39亿"},
      {"name":"诺德股份","reason":"铜箔+AI服务器+半年报扭亏","board":"首板","seal":"1.86亿"},
      {"name":"通鼎互联","reason":"中报扭亏+光纤光缆","board":"2连板","seal":"1.51亿"},
      {"name":"科森科技","reason":"折叠屏+机器人+中报扭亏","board":"2连板","seal":"1.45亿"},
      {"name":"湖南白银","reason":"半年报增长+白银","board":"首板","seal":"1.63亿"},
    ]},
    {"title":"创新药/医药线","cls":"#f85149","stocks":[
      {"name":"键凯科技","reason":"mRNA疫苗+LNP+聚乙二醇+创新药","board":"2连板","seal":"4.72亿"},
      {"name":"双鹭药业","reason":"mRNA平台+GLP-1+创新药","board":"2连板","seal":"1.27亿"},
      {"name":"北陆药业","reason":"集采拟中选+化药+中药","board":"首板","seal":"0.56亿"},
      {"name":"中关村","reason":"mRNA疫苗平台+创新药+药品获批","board":"2连板","seal":"0.28亿"},
    ]},
    {"title":"机器人/有色贵金属线","cls":"#3fb950","stocks":[
      {"name":"飞龙股份","reason":"液冷服务器+汽车热管理+机器人","board":"首板","seal":"2.41亿"},
      {"name":"精达股份","reason":"电磁线+人形机器人+数据中心","board":"首板","seal":"1.39亿"},
      {"name":"宇环数控","reason":"机器人+消费电子+数控机床","board":"2连板","seal":"0.51亿"},
      {"name":"白银有色","reason":"白银+黄金+多金属综合","board":"首板","seal":"1.39亿"},
      {"name":"深中华A","reason":"黄金珠宝+黄金涨价","board":"2连板","seal":"0.40亿"},
      {"name":"江钨装备","reason":"钨钽铌资产注入+江西国资","board":"首板","seal":"1.15亿"},
    ]},
  ],
  "zhaban_high": [
    {"title":"当日仅4只炸板","line":"炸板率6.9%","sub":"✅ 打板环境温和，无显著高换手炸板标的，分歧极小"},
    {"title":"缩量观望","line":"股指期货交割日","sub":"⚠ 指数小阳但成交缩量2000亿，追高标的需防回落"},
  ],
  "zhaban_low": [
    {"name":"士兰微","line":"+10.0% · 封单4.83亿 · SiC功率半导体","sub":"✅ 全场封单最强，大单锁仓，趋势关注"},
    {"name":"键凯科技","line":"2连板 · 封单4.72亿","sub":"✅ 创新药2板，大封单低换手，1进2强势"},
    {"name":"汉森制药","line":"3连板 · 全场最高板","sub":"✅ 创新药+中报预增，空间板持有观察"},
  ],
  "strategy_title": "短线策略 & 明日接力计划（2026-08-24周一预判）",
  "strategy_cols": [
    {"title":"✅ 重点接力（明日关注）","cls":"#3fb950","items":[
      "<b>汉森制药</b>（3板）— 全场最高板，创新药+中药+中报预增，3进4关键日。若一字封板则持有",
      "<b>士兰微</b>（首板 封单4.83亿）— SiC功率半导体，封单最强，1进2重点关注",
      "<b>键凯科技/双鹭药业/中关村</b>（2板）— 创新药线，2进3观察强度",
      "<b>通鼎互联/科森科技</b>（2板）— 中报扭亏+科技，换手承接",
    ]},
    {"title":"🔍 分歧低吸（回调关注）","cls":"#58a6ff","items":[
      "<b>中际旭创</b>（热度第8·中报净利+241.7%）— AI核心资产，逢低配置（注：现金流-44%需警惕）",
      "<b>东山精密</b>（中报+290%·追加5亿扩建）— 科技权重，趋势不破持有",
      "<b>通信设备/半导体板块</b> — 主力净流入+76.34/+15.19亿，中期持续",
      "<b>白银有色/深中华A</b> — 黄金涨价+避险，回踩低吸",
    ]},
    {"title":"🚫 坚决规避（明日回避）","cls":"#f85149","items":[
      "<b>医药生物板块</b>— 主力净流出-39.33亿，医疗服务/化学制药领跌",
      "<b>追高缩量日后排</b>— 成交缩量2000亿，后排接力风险大",
      "<b>高位无业绩支撑题材</b>— 美债30年5.25%高压制高估值，去弱留强",
      "<b>股指期货交割日遗留仓位</b>— 交割日已过，周一注意波动",
    ]},
  ],
  "review_title": "行情回顾 & 后市展望",
  "review_text": "今日两市股指全天小幅波段，收盘以小阳线报收，全天成交1.88万亿，2431家上涨。股指期货交割日，盘面出奇平静——昨日2.08万亿、今日1.88万亿，再缩2000亿，多空双方处于平衡，大部分资金处于观望状态。<br><br><b style=\"color:#e1e8ed;\">板块：</b>贵金属、有色、能源涨幅靠前；医疗服务、化学制药跌幅居前。从涨跌幅榜看，涨幅&gt;3%的459家、跌幅&gt;10%的27家、跌幅&gt;3%的521家，前二十位成交股17家上涨——指数红但个股赚钱效应一般。<br><b style=\"color:#e1e8ed;\">科技：</b>通信设备板块主力净流入+76.34亿、半导体+15.19亿，CPO/半导体/AI算力线涨停活跃；创新药线2板集中。涨停54只，封板率93.1%，炸板仅4只。",
  "outlook_text": "<b style=\"color:#e1e8ed;\">外部变量：</b>美国30年期国债利率达5.25%，创2007年以来新高（仅次于次贷危机），这是悬在全球资产上的\"炸弹\"——无风险收益抬升压制高估值成长股（科技），而美国为化解债务压力被迫放水，中长期利好实物类资产（有色周期资源）。<br><br><b style=\"color:#e1e8ed;\">操作取向：</b>现阶段轻仓跟随市场晃，没有特别把握不出手。交易重点方向应是有色周期+高股息，以大科技为首的题材股能减仓的尽量减仓。中长期看多科技，但短期回避风险——仓位持续压缩至35%，其中大部分为有色、周期，后期有机会考虑买入一部分银行股对冲不确定性。<br><b style=\"color:#e1e8ed;\">节奏：</b>缩量观望期不追高，等分歧低吸；周一关注汉森制药3进4能否打开空间。",
  "amount_rank": [
    {"rank":1,"code":"688836","name":"宇树科技","heat":"1142.7万","note":"机器人人气龙头"},
    {"rank":2,"code":"600664","name":"哈药股份","heat":"581.5万","note":"医药人气"},
    {"rank":3,"code":"688825","name":"长鑫科技","heat":"426.6万","note":"存储芯片"},
    {"rank":4,"code":"002491","name":"通鼎互联","heat":"343.3万","note":"中报扭亏+光纤 2板"},
    {"rank":5,"code":"600613","name":"神奇制药","heat":"317.0万","note":"医药"},
    {"rank":6,"code":"600127","name":"金健米业","heat":"289.3万","note":"农业"},
    {"rank":7,"code":"600487","name":"亨通光电","heat":"272.0万","note":"通信"},
    {"rank":8,"code":"300308","name":"中际旭创","heat":"250.5万","note":"AI算力核心·中报+241.7%"},
    {"rank":9,"code":"000636","name":"风华高科","heat":"237.2万","note":"元件"},
    {"rank":10,"code":"300142","name":"沃森生物","heat":"233.0万","note":"疫苗"},
  ],
  "amount_footnote": "* 当日个股精确成交额接口未返回，此处以同花顺\"市场活跃度(热度)\"排名替代，反映资金关注度而非精确成交额。",
  "risk_rank": [
    {"name":"医药生物","dir":"领跌","flow":"-39.33亿","risk":"🚨 主力大幅流出，医疗服务/化学制药跌幅居前，坚决规避"},
    {"name":"医疗服务/化学制药","dir":"领跌","flow":"待披露","risk":"⚠ 用户复盘明确提及跌幅居前"},
    {"name":"高位无业绩题材","dir":"承压","flow":"—","risk":"美债高压下高估值承压"},
  ],
  "risk_footnote": "* 当日精确个股跌幅榜接口未返回，以\"主力净流出方向+用户复盘领跌板块\"标注风险。",
  "money_in": [
    {"name":"通信设备（板块）","val":"+76.34亿"},
    {"name":"半导体（板块）","val":"+15.19亿"},
    {"name":"黄金（板块）","val":"+5.39亿"},
    {"name":"全A合计","val":"+167.8亿"},
    {"name":"有色金属（用户复盘领涨）","val":"方向强"},
  ],
  "money_out": [
    {"name":"医药生物（板块）","val":"-39.33亿"},
    {"name":"医疗服务/化学制药","val":"方向弱"},
    {"name":"—","val":"—"},
    {"name":"—","val":"—"},
    {"name":"—","val":"—"},
  ],
  "core_stocks": [
    {"name":"汉森制药","badge":"空间板","badge_cls":"badge-hot","change":"+10.0% · 3连板","change_cls":"up","info":"全场最高板，创新药+中药+中报预增，3进4关键战","info_cls":""},
    {"name":"士兰微","badge":"封单最强","badge_cls":"badge-hot","change":"+10.0% · 首板 封单4.83亿","change_cls":"up","info":"SiC功率半导体+IDM，封单全场第一，1进2重点","info_cls":""},
    {"name":"中际旭创","badge":"价值回归","badge_cls":"badge-warn","change":"AI核心·中报+241.7%","change_cls":"up","info":"算力核心资产，趋势不破则持有，逢低加仓（现金流-44%警惕）","info_cls":""},
    {"name":"东山精密","badge":"价值回归","badge_cls":"badge-warn","change":"中报+290%·追加5亿扩建","change_cls":"up","info":"科技权重，扩建扩产，趋势持有","info_cls":""},
    {"name":"医药生物板块","badge":"回避预警","badge_cls":"badge-warn","change":"-39.33亿净流出","change_cls":"","info":"主力大幅流出，医疗服务/化学制药领跌，坚决规避","info_cls":"#f85149"},
  ],
  "margin_items": [
    {"label":"融资余额","value":"1.271万亿","sub":"杠杆资金小幅回落","sub_cls":"#f85149"},
    {"label":"融券余额","value":"100.1亿","sub":"融券规模低位","sub_cls":""},
    {"label":"两融合计","value":"1.381万亿","sub":"缩量日两融平稳","sub_cls":""},
    {"label":"杠杆占比","value":"~2.3%","sub":"中性区间 风控可控","sub_cls":"#d29922"},
  ],
  "track_rows": [
    {"code":"002412","name":"汉森制药","chg":"+10.0%","chg_cls":"positive","status":"3连板 全场最高","badge":"封板✅","badge_cls":"badge-seal","turnover":"—","strategy":"3进4关键战 持有","strategy_cls":"#3fb950"},
    {"code":"600460","name":"士兰微","chg":"+10.0%","chg_cls":"positive","status":"首板 封单4.83亿","badge":"封板✅","badge_cls":"badge-seal","turnover":"—","strategy":"封单最强 1进2关注","strategy_cls":"#3fb950"},
    {"code":"688356","name":"键凯科技","chg":"+10.0%","chg_cls":"positive","status":"2连板 封单4.72亿","badge":"封板✅","badge_cls":"badge-seal","turnover":"—","strategy":"创新药2板 2进3观察","strategy_cls":"#d29922"},
    {"code":"300308","name":"中际旭创","chg":"活跃","chg_cls":"positive","status":"中报+241.7%","badge":"—","badge_cls":"","turnover":"—","strategy":"AI核心 逢低配置","strategy_cls":"#58a6ff"},
    {"code":"002491","name":"通鼎互联","chg":"+10.0%","chg_cls":"positive","status":"2连板 中报扭亏","badge":"封板✅","badge_cls":"badge-seal","turnover":"—","strategy":"2进3关注","strategy_cls":"#3fb950"},
    {"code":"002536","name":"飞龙股份","chg":"+10.0%","chg_cls":"positive","status":"首板 封单2.41亿","badge":"封板✅","badge_cls":"badge-seal","turnover":"—","strategy":"液冷+机器人 观察","strategy_cls":"#d29922"},
    {"code":"002396","name":"星网锐捷","chg":"+10.0%","chg_cls":"positive","status":"首板 封单2.39亿","badge":"封板✅","badge_cls":"badge-seal","turnover":"—","strategy":"CPO+半年报 观察","strategy_cls":"#d29922"},
    {"code":"600487","name":"亨通光电","chg":"活跃","chg_cls":"positive","status":"热度第7 通信","badge":"—","badge_cls":"","turnover":"—","strategy":"通信设备主线 趋势关注","strategy_cls":"#58a6ff"},
  ],
  "invest_cols": [
    {"title":"🎯 选股策略","cls":"#58a6ff","items":[
      "主线优先：半年报增长（业绩）&gt; 科技(CPO/半导体/AI算力) &gt; 创新药 &gt; 机器人/有色",
      "连板优先：关注3进4（汉森制药）；2进3（键凯/双鹭/中关村）；1进2（士兰微/星网锐捷）",
      "首板低吸：大封单+低换手首板（士兰微/飞龙/精达）",
      "规避板块：医药生物（净流出-39.33亿）/ 无业绩高位题材",
    ]},
    {"title":"🛡️ 风控策略","cls":"#d29922","items":[
      "美债30年5.25%高压 → 高估值科技承压，仓位压缩至35%",
      "缩量1.88万亿 → 不追高，等分歧低吸",
      "轻仓跟随市场晃，无特别把握不出手",
      "科技能减则减，主体配有色周期+高股息，后期银行对冲",
    ]},
    {"title":"💪 心态管理","cls":"#3fb950","items":[
      "交割日平静 → 不焦虑，缩量观望是常态",
      "主线清晰（业绩+科技+创新药）→ 集中仓位，不撒网",
      "汉森3进4是关键 → 过了空间打开，不过则等下一轮",
      "美债无法预判 → 用仓位管理应对，而非押方向",
    ]},
  ],
  "special_events": [
    {"title":"⚡ 中际旭创中报净利+241.7%","text":"AI算力需求爆发，但经营现金流同比-44%，高增下需警惕回款质量。"},
    {"title":"🔬 东山精密中报+290%并追加5亿扩建","text":"科技权重扩产，强化中期成长逻辑。"},
    {"title":"💰 美债30年收益率升至5.25%","text":"创2007年以来新高，无风险收益抬升压制高估值成长股，是悬在全球资产上的\"炸弹\"。"},
    {"title":"📈 股指期货交割日平静","text":"成交缩量2000亿至多空平衡，资金观望，无极端波动。"},
  ],
  "calendar": [
    "· 周五（08-21）：股指期货交割日·缩量1.88万亿·涨停54只封板率93.1%",
    "· 周一（08-24）：汉森制药3进4关键日 + 观察缩量后方向选择",
    "· 下周关注：半年报密集披露持续性、通信设备/半导体资金流入延续性、美债利率走向",
  ],
  "opcheck_cols": [
    {"title":"✅ 下周一（08-24）操作清单","cls":"#3fb950","items":[
      "1️⃣ 观察汉森制药3进4 → 缩量一字持有，炸板则减仓",
      "2️⃣ 士兰微/星网锐捷 1进2 → 大封单低换手，高开2-3%可轻仓试错",
      "3️⃣ 键凯/双鹭/中关村 2进3 → 观察竞价强度，强则留弱则减",
      "4️⃣ 中际旭创/东山精密 → 5日线附近低吸，趋势不破持有",
      "5️⃣ 医药生物板块 → 坚决不碰，等资金回流",
    ]},
    {"title":"📚 盘后推荐阅读","cls":"#58a6ff","items":[
      "📄 中际旭创2026中报：净利+241.7%，现金流-44%质量提示",
      "📄 东山精密中报：+290%并追加5亿扩建产能",
      "📄 美债30年5.25%：无风险利率新高对估值的影响框架",
      "📄 同花顺涨停池复盘：54只涨停·汉森制药3板·封板率93.1%",
    ]},
  ],
  "disclaimer": "⚠️ <b>免责声明：</b>本报告仅供参考，不构成投资建议。A股市场有风险，投资需谨慎。部分板块涨跌幅、个股精确成交额、跌停家数及前日连板基数当日接口未返回，已以\"—\"或方向性口径标注并加脚注说明。",
  "generated": "📊 A股市场复盘报告 · 2026-08-22",
  "source_footer": "数据源：同花顺（涨停池/指数/龙虎榜/热度）· 东方财富·妙想（资金流/融资融券/行业）· 用户盘后复盘（外围/仓位观点）",
}

# ============== 构建函数 ==============
def _badge(cls, text):
    return f'<span class="badge {cls}">{text}</span>'

def build_template(d):
    """根据数据字典 d 生成完整模板克隆版 HTML（CSS/结构不变，仅替换数据）。"""
    L = []
    # head（含 CSP 与平滑滚动/存储脚本，与模板一致）
    L.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta http-equiv="Content-Security-Policy" content="default-src 'self' https: data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: blob:; style-src 'self' 'unsafe-inline' https: data:; img-src 'self' https: data: blob:; font-src 'self' https: data:; media-src 'self' https: data: blob:; connect-src 'self' https: data: blob:; frame-src 'self' https: data:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'self';"><script>(function(){{try{{void sessionStorage}}catch(e){{var n={{getItem:function(){{return null}},setItem:function(){{}},removeItem:function(){{}},clear:function(){{}},key:function(){{return null}},length:0}};try{{Object.defineProperties(window,{{localStorage:{{value:n,writable:false,configurable:false}},sessionStorage:{{value:n,writable:false,configurable:false}}}})}}catch(e2){{window.localStorage=n;window.sessionStorage=n}}}}}})();</script><script>(function(){{document.addEventListener("click",function(e){{var t=e.target;if(!t)return;var a=t.closest&&t.closest("a");if(!a)return;var h=a.getAttribute("href");if(!h||h.charAt(0)!="#"||h=="#")return;e.preventDefault();e.stopPropagation();var el=document.querySelector(h);if(el)el.scrollIntoView({{behavior:"smooth",block:"start"}});try{{history.replaceState(null,"",h);}}catch(_){{}}}});}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{d['title']}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
{TEMPLATE_CSS}
</style>
</head>
<body>
<div class="container">""")

    # Header
    tags = "".join(f'<span class="tag">{t}</span>' for t in d["tags"])
    L.append(f"""  <div class="header">
    <h1>晚睡协会 · 📊 A股市场复盘报告</h1>
    <div class="date">📅 {d['date']}</div>
    <div class="tags">{tags}</div>
  </div>""")

    # 门户区（首页概览 + 图表 + 历史入口）
    L.append(_portal_section(d))

    # 4 index cards
    cards = []
    for c in d["indices"]:
        cards.append(f"""    <div class="card">
      <div class="label">{c['name']}</div>
      <div class="value {c['cls']}">{c['value']}</div>
      <div class="sub {c['cls']}">{c['sub']}</div>
    </div>""")
    L.append('  <div class="cards">\n' + "\n".join(cards) + '\n  </div>')

    # core cards
    cards = []
    for c in d["core_cards"]:
        cards.append(f"""    <div class="card" style="border-color: {c['style']};">
      <div class="label">{c['label']}</div>
      <div class="value" style="color: {c['vcolor']};">{c['value']}</div>
      <div class="sub">{c['sub']}</div>
    </div>""")
    L.append('  <div class="cards" style="margin-bottom: 20px;">\n' + "\n".join(cards) + '\n  </div>')

    # 涨跌家数概览
    co = d["change_overview"]
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">📈</span> 涨跌家数概览</div>
    <div class="grid-4" style="text-align:center;">
      <div><div style="font-size:36px;font-weight:700;color:#f85149;">{co['up']}</div><div style="font-size:13px;color:#8b949e;">上涨家数</div></div>
      <div><div style="font-size:36px;font-weight:700;color:#3fb950;">{co['down']}</div><div style="font-size:13px;color:#8b949e;">下跌家数（估算）</div></div>
      <div><div style="font-size:36px;font-weight:700;color:#d29922;">{co['ratio']}</div><div style="font-size:13px;color:#8b949e;">涨跌比</div></div>
      <div><div style="font-size:36px;font-weight:700;color:#d29922;">{co['amount']}</div><div style="font-size:13px;color:{co['amount_cls']};">{co['amount_sub']}</div></div>
    </div>
  </div>""")

    # 短线情绪全景
    emo = "".join(
        f'<div style="background:#21262d;border-radius:8px;padding:14px;"><div style="font-size:12px;color:#8b949e;">{x["label"]}</div><div style="font-size:24px;font-weight:700;color:{x["cls"] or "#e1e8ed"};margin-top:4px;">{x["value"]}</div><div style="font-size:11px;color:#8b949e;">{x["sub"]}</div></div>'
        for x in d["emotion_panorama"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">⚡</span> 短线情绪全景</div>
    <div class="grid-5" style="text-align:center;margin-bottom:16px;">
      {emo}
    </div>
  </div>""")

    # 情绪监测
    mon = "".join(
        f'<div class="sentiment-item"><div class="s-label">{x["label"]}</div><div class="s-value" style="color:{x["cls"] or "#e1e8ed"};">{x["value"]}</div><div style="font-size:12px;color:#8b949e;margin-top:4px;">{x["sub"]}</div></div>'
        for x in d["emotion_monitor"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">🚨</span> 情绪监测 & 极端值</div>
    <div class="sentiment-grid">{mon}</div>
  </div>""")

    # 连板梯队
    rows = []
    for r in d["jinji_rows"]:
        rows.append(f"""        <tr>
          <td style="font-weight:600;">{r['tier']}</td>
          <td>{r['base']}</td>
          <td>{r['success']}</td>
          <td><span class="jinji-rate {r['rate_cls']}">{r['rate']}</span></td>
          <td>{r['rep']}</td>
          <td style="color:#d29922;">{r['signal']}</td>
        </tr>""")
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">🏆</span> 连板梯队 & 晋级率统计</div>
    <div class="table-scroll"><table class="jinji-table">
      <thead><tr><th>晋级档位</th><th>前日基数</th><th>成功数</th><th>晋级率</th><th>代表个股</th><th>信号解读</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
    <div style="margin-top:12px;padding:10px;background:#f8514910;border-radius:8px;font-size:13px;color:#d29922;">{d['jinji_note']}</div>
  </div>""")

    # 外围股指速览（日/韩/美）——置于板块涨跌榜上方
    ovrows = ""
    for x in d.get("overseas", []):
        disp = x["chg"]
        if disp and not disp.startswith(("-", "+")):
            disp = "+" + disp
        ovrows += f'<tr><td>{x["region"]}</td><td><b>{x["name"]}</b></td><td style="text-align:right;">{x["close"]}</td><td class="{x["cls"]}" style="text-align:right;">{disp}</td></tr>\n'
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">🌐</span> 外围股指速览（日 / 韩 / 美）</div>
    <div class="table-scroll"><table><tr><th>地区</th><th>指数</th><th style="text-align:right;">最新收盘</th><th style="text-align:right;">涨跌幅</th></tr>
{ovrows}    </table></div>
    <div style="font-size:11px;color:#8b949e;margin-top:8px;">{d.get('overseas_note','')}</div>
  </div>""")

    # 板块涨跌榜
    inrows = "".join(f'<tr><td>{x["name"]}</td><td class="positive">{x["dir"]}</td><td class="positive">{x["flow"]}</td></tr>' for x in d["sector_top_in"])
    outrows = "".join(f'<tr><td>{x["name"]}</td><td class="negative">{x["dir"]}</td><td class="negative">{x["flow"]}</td></tr>' for x in d["sector_top_out"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">🔥</span> 板块涨跌榜 Top5（按主力资金净流入）</div>
    <div class="two-col">
      <div class="col"><h4 style="color:#f85149;">🔴 主力净流入 Top5（板块）</h4><div class="table-scroll"><table>
        <tr><th>板块</th><th>方向</th><th>主力净流入</th></tr>{inrows}</table></div></div>
      <div class="col"><h4 style="color:#3fb950;">🟢 主力净流出 Top5（板块）</h4><div class="table-scroll"><table>
        <tr><th>板块</th><th>方向</th><th>主力净流出</th></tr>{outrows}</table></div></div>
    </div>
    <div style="font-size:11px;color:#8b949e;margin-top:8px;">{d['sector_footnote']}</div>
  </div>""")

    # 主线深度
    chips = "".join(f'<span>{c}</span>' for c in d["main_line"]["chips"])
    L.append(f"""  <div class="section" id="sec-mainline">
    <div class="section-title"><span class="icon">🔶</span> {d['main_line']['title']}</div>
    <div style="background:#21262d;border-radius:8px;padding:16px;margin-bottom:12px;">
      <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:13px;margin-bottom:12px;">{chips}</div>
      <div style="font-size:13px;color:#8b949e;line-height:1.8;">
        <b style="color:#e1e8ed;">核心逻辑：</b>{d['main_line']['core_logic']}<br>
        <b style="color:#e1e8ed;">持续性判断：</b>{d['main_line']['continuity']}
      </div>
    </div>
  </div>""")

    # 涨停分类
    groups = []
    for g in d["limit_up_groups"]:
        items = "".join(
            f'<div style="padding:4px 0;border-bottom:1px solid #21262d;">{_badge("badge-seal","封板✅")} <b>{s["name"]}</b> <span style="color:#d29922;font-size:10px;">{s["reason"]}</span> {s["board"]} 封单{s["seal"]}</div>'
            for s in g["stocks"])
        groups.append(f"""      <div>
        <h4 style="color:{g['cls']};margin-bottom:8px;">{g['title']}</h4>
        <div style="font-size:12px;">{items}</div>
      </div>""")
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">🎯</span> 涨停板复盘 · 按题材分类（含涨停归因）</div>
    <div style="background:#1c2128;border:1px solid #2d333b;border-radius:6px;padding:10px 14px;margin-bottom:14px;font-size:12px;color:#8b949e;">
      📌 <b style="color:#d29922;">涨停归因</b>来源：同花顺涨停池（limit_up_reason）· 封板判断：涨停价封单
    </div>
    <div class="limitup-grid">
{chr(10).join(groups)}
    </div>
  </div>""")

    # 炸板分析
    high = "".join(f'<div class="zhaban-high" style="padding:6px 10px;border-radius:6px;margin-bottom:6px;"><b>{x["title"]}</b> · {x["line"]}<br><span style="color:#3fb950;font-size:11px;">{x["sub"]}</span></div>' for x in d["zhaban_high"])
    low = "".join(f'<div class="zhaban-low" style="padding:6px 10px;border-radius:6px;margin-bottom:6px;"><b>{x["name"]}</b> {x["line"]}<br><span style="color:#3fb950;font-size:11px;">{x["sub"]}</span></div>' for x in d["zhaban_low"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">💥</span> 炸板深度分析（炸板4只 · 炸板率6.9% ✅偏低）</div>
    <div class="two-col">
      <div class="col"><h4 style="color:#f85149;">🚨 高换手炸板（明日规避）</h4><div style="font-size:12px;">{high}</div></div>
      <div class="col"><h4 style="color:#3fb950;">✅ 低换手封板（反包策略关注）</h4><div style="font-size:12px;">{low}</div></div>
    </div>
  </div>""")

    # 短线策略
    L.append(_strategy_section(d["strategy_title"], d["strategy_cols"], secid="sec-strategy"))

    # 行情回顾
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">📝</span> {d['review_title']}</div>
    <div class="two-col">
      <div class="col"><h4 style="color:#f85149;">📈 今日行情回顾</h4><p style="font-size:13px;line-height:1.8;color:#8b949e;">{d['review_text']}</p></div>
      <div class="col"><h4 style="color:#f85149;">🔮 后市展望</h4><p style="font-size:13px;line-height:1.8;color:#8b949e;">{d['outlook_text']}</p></div>
    </div>
  </div>""")

    # 成交额排行
    arows = "".join(f'<tr><td>{x["rank"]}</td><td>{x["code"]}</td><td><b>{x["name"]}</b></td><td style="color:#d29922;">{x["heat"]}</td><td>{x["note"]}</td></tr>' for x in d["amount_rank"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">💰</span> 市场活跃度排行 Top10（热度）</div>
    <div class="table-scroll"><table><tr><th>排名</th><th>代码</th><th>名称</th><th>热度</th><th>备注</th></tr>{arows}</table></div>
    <div style="font-size:11px;color:#8b949e;margin-top:8px;">{d['amount_footnote']}</div>
  </div>""")

    # 跌幅榜
    rrows = "".join(f'<tr><td><b>{x["name"]}</b></td><td class="negative">{x["dir"]}</td><td class="negative">{x["flow"]}</td><td style="color:#f85149;font-size:12px;">{x["risk"]}</td></tr>' for x in d["risk_rank"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">📉</span> 今日风险警示 Top（资金净流出/领跌）</div>
    <div class="table-scroll"><table><tr><th>板块/标的</th><th>方向</th><th>主力净流出</th><th>风险提示</th></tr>{rrows}</table></div>
    <div style="font-size:11px;color:#8b949e;margin-top:8px;">{d['risk_footnote']}</div>
  </div>""")

    # 资金风向
    inrows = "".join(f'<div class="money-row"><span class="stock-name">{x["name"]}</span><span class="money-plus">{x["val"]}</span></div>' for x in d["money_in"])
    outrows = "".join(f'<div class="money-row"><span class="stock-name">{x["name"]}</span><span class="money-minus">{x["val"]}</span></div>' for x in d["money_out"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">💹</span> 资金风向 · 主力净流入/流出 Top（板块）</div>
    <div class="two-col">
      <div class="col"><h4 style="color:#3fb950;">✅ 今日主力净流入 Top</h4>{inrows}</div>
      <div class="col"><h4 style="color:#f85149;">🚨 今日主力净流出 Top</h4>{outrows}</div>
    </div>
  </div>""")

    # 核心个股
    items = []
    for s in d["core_stocks"]:
        items.append(f"""      <div class="stock-item" style="border-left-color:{s.get('info_cls') or '#f85149'};">
        <div class="name">{s['name']} {_badge(s['badge_cls'], s['badge'])}</div>
        <div class="change {s['change_cls']}">{s['change']}</div>
        <div class="info" style="color:{s.get('info_cls') or '#8b949e'};">{s['info']}</div>
      </div>""")
    L.append('  <div class="section">\n    <div class="section-title"><span class="icon">⭐</span> 核心个股筛选（5类）</div>\n    <div class="stock-grid">\n' + "\n".join(items) + '\n    </div>\n  </div>')

    # 融资融券
    mitems = "".join(
        f'<div style="background:#21262d;border-radius:8px;padding:16px;"><div style="font-size:12px;color:#8b949e;">{x["label"]}</div><div style="font-size:22px;font-weight:700;color:#e1e8ed;margin-top:6px;">{x["value"]}</div><div style="font-size:12px;color:{x["sub_cls"] or "#8b949e"};margin-top:4px;">{x["sub"]}</div></div>'
        for x in d["margin_items"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">📊</span> 融资融券数据</div>
    <div class="grid-4" style="text-align:center;">{mitems}</div>
  </div>""")

    # 个股跟踪
    trows = []
    for r in d["track_rows"]:
        trows.append(f"""        <tr>
          <td>{r['code']}</td><td><b>{r['name']}</b></td><td class="{r['chg_cls']}">{r['chg']}</td><td>{r['status']}</td><td>{_badge(r['badge_cls'], r['badge']) if r['badge_cls'] else '—'}</td><td>{r['turnover']}</td><td style="color:{r['strategy_cls']};">{r['strategy']}</td>
        </tr>""")
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">📌</span> 重要个股跟踪表（8只核心标的）</div>
    <div class="table-scroll"><table><tr><th>代码</th><th>名称</th><th>今日涨幅</th><th>当前状态</th><th>封板/炸板</th><th>换手率</th><th>明天策略</th></tr>
{chr(10).join(trows)}
    </table></div>
  </div>""")

    # 投资策略
    L.append(_strategy_section("投资策略 & 心态管理", d["invest_cols"]))

    # 特殊事件
    ev = "".join(f'<b style="color:{("f85149" if "⚡" in e["title"] or "💰" in e["title"] else ("d29922" if "🔬" in e["title"] else "3fb950"))};">{e["title"]}</b> — {e["text"]}<br>' for e in d["special_events"])
    cal = "".join(f'{c}<br>' for c in d["calendar"])
    L.append(f"""  <div class="section">
    <div class="section-title"><span class="icon">⚠️</span> 特殊事件 & 监管关注</div>
    <div style="background:#f8514910;border:1px solid #f8514933;border-radius:8px;padding:14px;margin-bottom:12px;font-size:13px;">{ev}</div>
    <div style="background:#21262d;border-radius:8px;padding:14px;font-size:13px;">
      <b style="color:#e1e8ed;">📅 本周重点事件日历：</b><br>{cal}
    </div>
  </div>""")

    # 操作建议
    L.append(_strategy_section("操作建议 & 盘后资料", d["opcheck_cols"]))

    # footer
    L.append(f"""  <div class="footer">
    <div class="disclaimer">{d['disclaimer']}</div>
    <div>{d['generated']}</div>
  </div>
</div>
</body>
</html>""")
    return "\n".join(L)

def _portal_section(d):
    """首页门户区：最新摘要 + 三张 ECharts 图（涨跌饼图/板块资金/连板梯队）+ 历史入口。"""
    co = d.get("change_overview", {})
    up = co.get("up", "0") or "0"
    down = co.get("down", "0") or "0"
    try:
        up_n = float(str(up).replace(",", "").replace("~", "").replace("约", ""))
    except Exception:
        up_n = 0
    try:
        down_n = float(str(down).replace(",", "").replace("~", "").replace("约", ""))
    except Exception:
        down_n = 0

    # 板块资金（从 money_in/money_out 解析数值，单位亿）
    def _parse_yi(v):
        if not v:
            return 0
        v = str(v).replace("亿", "").replace("+", "").replace(",", "").strip()
        try:
            return float(v)
        except Exception:
            return 0
    min_rows = [{"name": x.get("name", ""), "val": _parse_yi(x.get("val", ""))}
                for x in d.get("money_in", []) if x.get("name") not in ("—", "", None)]
    mout_rows = [{"name": x.get("name", ""), "val": _parse_yi(x.get("val", ""))}
                 for x in d.get("money_out", []) if x.get("name") not in ("—", "", None)]
    fund_rows = [{"name": r["name"], "val": r["val"], "out": False} for r in min_rows[:5]]
    fund_rows += [{"name": r["name"], "val": -r["val"], "out": True} for r in mout_rows[:5]]
    fund_rows = [r for r in fund_rows if r["name"]]

    # 连板梯队（从 jinji_rows 取档位与成功数）
    ladder = [{"tier": r.get("tier", ""), "succ": r.get("success", "0")}
              for r in d.get("jinji_rows", [])]
    def _succ_num(s):
        import re
        m = re.search(r"(\d+)", str(s))
        return int(m.group(1)) if m else 0
    ladder = [{"tier": r["tier"], "succ": _succ_num(r["succ"])} for r in ladder]

    js = json.dumps({
        "up": up_n, "down": down_n,
        "fund": fund_rows,
        "ladder": ladder,
    }, ensure_ascii=False)

    return f"""  <div class="portal">
    <div class="portal-head">
      <div class="ph-title">📡 实时概览 · 数据来源：本地实采（同花顺 / 东方财富）</div>
      <div class="portal-links">
        <a href="archive.html">📚 历史报告</a>
        <a href="#sec-mainline">🔶 主线分析</a>
        <a href="#sec-strategy">💡 策略</a>
      </div>
    </div>
    <div class="charts">
      <div class="chart-box"><div class="cb-title">涨跌家数分布</div><div class="echart" id="chartUpDown"></div></div>
      <div class="chart-box"><div class="cb-title">板块主力资金净流入(亿)</div><div class="echart" id="chartFund"></div></div>
      <div class="chart-box"><div class="cb-title">连板梯队（成功数）</div><div class="echart" id="chartLadder"></div></div>
    </div>
  </div>
  <script>
  (function(){{
    var D = {js};
    var TXT = '#e1e8ed', SUB='#8b949e', GRID='#21262d';
    function render(){{
      try{{
        var c1 = echarts.init(document.getElementById('chartUpDown'));
        var total = (D.up||0)+(D.down||0);
        c1.setOption({{ tooltip:{{trigger:'item',formatter:'{{b}}: {{c}}<br/>占比 {{d}}%'}},
          title:{{text:'总 '+total+' 只',left:'center',top:6,textStyle:{{color:SUB,fontSize:11,fontWeight:'normal'}}}},
          series:[{{ type:'pie', radius:['38%','62%'], avoidLabelOverlap:false,
            data:[{{name:'上涨',value:D.up,itemStyle:{{color:'#f85149'}}}},{{name:'下跌',value:D.down,itemStyle:{{color:'#3fb950'}}}}],
            label:{{color:TXT,fontSize:14,fontWeight:'bold',formatter:'{{b}}\\n{{c}}'}},
            labelLine:{{lineStyle:{{color:SUB}},length:8,length2:6}},
            emphasis:{{label:{{fontSize:16}}}} }}] }});
        var c2 = echarts.init(document.getElementById('chartFund'));
        var fdata = D.fund.slice().sort(function(a,b){{return a.val-b.val;}});
        c2.setOption({{ grid:{{left:8,right:36,top:10,bottom:10,containLabel:true}},
          tooltip:{{trigger:'axis',axisPointer:{{type:'shadow'}}}},
          xAxis:{{type:'value',axisLabel:{{color:SUB,fontSize:11}},splitLine:{{lineStyle:{{color:GRID}}}}}},
          yAxis:{{type:'category',data:fdata.map(function(r){{return r.name;}}),axisLabel:{{color:TXT,fontSize:11}}}},
          series:[{{type:'bar',barMaxWidth:18,
            data:fdata.map(function(r){{return {{value:r.val,itemStyle:{{color:r.out?'#f85149':'#3fb950'}}}};}}),
            label:{{show:true,position:function(p){{return p.value<0?'left':'right';}},color:TXT,fontSize:11,fontWeight:'bold',formatter:'{{c}}'}}}}] }});
        var c3 = echarts.init(document.getElementById('chartLadder'));
        c3.setOption({{ grid:{{left:8,right:24,top:30,bottom:10,containLabel:true}},
          tooltip:{{trigger:'axis',axisPointer:{{type:'shadow'}}}},
          xAxis:{{type:'category',data:D.ladder.map(function(r){{return r.tier;}}),axisLabel:{{color:TXT,fontSize:11}}}},
          yAxis:{{type:'value',axisLabel:{{color:SUB,fontSize:11}},splitLine:{{lineStyle:{{color:GRID}}}},minInterval:1}},
          series:[{{type:'bar',barMaxWidth:32,
            data:D.ladder.map(function(r){{return {{value:r.succ,itemStyle:{{color:'#58a6ff'}}}};}}),
            label:{{show:true,position:'insideTop',color:'#ffffff',fontSize:13,fontWeight:'bold',formatter:'{{c}}'}}}}] }});
        window.addEventListener('resize',function(){{c1.resize();c2.resize();c3.resize();}});
      }}catch(e){{console.warn('chart err',e);}}
    }}
    if(window.echarts){{ render(); }} else {{ var t=setInterval(function(){{ if(window.echarts){{clearInterval(t);render();}} }},300); }}
  }})();
  </script>"""

def _strategy_section(title, cols, secid=None):
    parts = []
    for c in cols:
        items = "".join(f"<li>{it}</li>" for it in c["items"])
        parts.append(f"""      <div class="strategy-col">
        <h4 style="color:{c['cls']};">{c['title']}</h4>
        <ul>{items}</ul>
      </div>""")
    sec_attr = f' id="{secid}"' if secid else ""
    return f"""  <div class="section"{sec_attr}>
    <div class="section-title"><span class="icon">💡</span> {title}</div>
    <div class="strategy-cols">
{chr(10).join(parts)}
    </div>
  </div>"""

# ============== CLI ==============
def main():
    args = sys.argv[1:]
    if args and args[0].endswith(".json"):
        with open(args[0], encoding="utf-8") as f:
            data = json.load(f)
        out = args[1] if len(args) > 1 else None
    else:
        data = SAMPLE_TEMPLATE_DATA
        out = args[0] if args else None
    html = build_template(data)
    if not out:
        date = data.get("title", "").split("·")[-1].strip() or "sample"
        out = f"收盘复盘模板版_{date}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK -> {out} ({len(html)} bytes)")

if __name__ == "__main__":
    main()
