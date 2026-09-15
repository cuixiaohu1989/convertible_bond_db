# 可转债信息数据库（自建）

自建可转债行情数据库网站。每天收盘后自动从东方财富抓取全市场可转债比价表，
备份到 GitHub Pages，可按日期查询历史数据。与「交易所通知」站完全独立。

## 架构

```
GitHub Actions (UTC 09:00 周一至周五 + 手动刷新)
  → main.py：东财主源抓取；失败自动降级腾讯兜底
  → scripts/build_db.py：按交易日生成 data/<date>.json + 更新 index.json
  → git commit & push → GitHub Pages 自动发布 docs/
  → 浏览器访问站点，选日期查历史
```

- 主源：东方财富可转债比价表 `push2.eastmoney.com/api/qt/clist/get`（`fs=b:MK0354`）
- 兜底：腾讯行情 `qt.gtimg.cn`（主源失败时使用，仅基础价格字段）
- 手动刷新密码：`6690`

## 目录

```
convertible_bond_db/
├── .github/workflows/crawl.yml   # 定时采集 + 部署
├── core/                         # date_utils / logger
├── fetchers/                     # eastmoney_bond.py（主）/ tencent_bond.py（兜底）
├── scripts/build_db.py           # 生成索引与每日快照
├── docs/                         # GitHub Pages 站点（index.html + app.js + data/）
├── main.py                       # 采集入口
├── bond_universe.json            # 转债代码词典（东财成功时刷新）
├── results.json                  # 当日采集中间结果
├── holidays.json                 # A股休市日
└── requirements.txt
```

## 本地运行验证

```bash
python -m venv .venv && .venv\Scripts\activate   # 或你的隔离环境
pip install -r requirements.txt
python main.py                    # 产出 results.json
python scripts/build_db.py        # 生成 docs/data/<date>.json + docs/index.json
```

本地网络通常可直接访问东方财富，可验证字段完整性与涨跌幅降序。

## 部署到 GitHub Pages

1. 新建公开仓库 `convertible_bond_db`，推送本目录。
2. 仓库 Settings → Pages → Source 选 `main` 分支、`/docs` 目录。
3. Settings → Secrets → 新增 `GH_TOKEN`（PAT，需 `repo` + `workflow` 权限，scope 最小化）。
4. 在 `docs/app.js` 顶部 `CONFIG` 填入 `OWNER`、`REPO`、`GH_TOKEN`（PAT）。
5. Actions 页手动 `Run workflow` 触发一次首跑，验证端到端。
6. 站点地址：`https://<OWNER>.github.io/convertible_bond_db/`

## 字段说明

主源（东方财富）含 26 个核心字段：代码、名称、现价、涨跌幅、涨跌额、最高、最低、
今开、昨收、成交量、成交额、正股价格、正股涨跌幅、正股代码、正股名称、转股价、
转股价值、转股溢价率、纯债溢价率、纯债价值、回售触发价、强赎触发价、到期赎回价、
上市日期、转股起始日、申购日期，并派生「双低 = 价格 + 转股溢价率」。

兜底源（腾讯）仅含价格/涨跌幅/涨跌额/开收盘/量额等基础字段，比价字段显示为「—」。

## 安全提示

前端 `app.js` 绝不硬编码 `GH_TOKEN`，仅从 gitignored 的 `docs/config.js` 读取（本机私用，不进仓库）。仓库 Secrets 里的 `GH_TOKEN` 由 GitHub 服务端注入 workflow，不落库。请使用 scope 最小、可随时吊销的令牌。
手动刷新密码 `6690` 仅作简易闸门，并非强鉴权。
