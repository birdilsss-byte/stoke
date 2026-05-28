# 🔥 Stoke — 免费 A 股数据层

<p align="center">
  <b>零 API Key · 零注册 · 零付费 · 开箱即用</b>
</p>

<p align="center">
  <a href="https://github.com/birdilsss-byte/stoke"><img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python"></a>
  <a href="https://github.com/birdilsss-byte/stoke/blob/master/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License"></a>
  <a href="https://github.com/birdilsss-byte/stoke/releases"><img src="https://img.shields.io/badge/version-1.3.0-brightgreen.svg" alt="Version"></a>
  <img src="https://img.shields.io/badge/API%20Key-不需要-orange.svg" alt="No API Key">
</p>

---

## 为什么要做这个？

市面上几乎所有 A 股数据方案都需要你去注册、付费、拿 API Key：
- Tushare 要积分、要付费
- Wind/Choice 动辄上万
- 免费 API 三天两头改接口

**Stoke 不一样。** 它直接基于通达信 TCP 协议和公开财经数据，**不用注册、不用付费、不用 API Key**。你装上就能用。

## 能做什么？

| 层面 | 数据 | 来源 |
|------|------|------|
| 📈 行情 | 实时行情（5 档盘口）、历史 K 线、PE/PB 估值 | 通达信 TCP + 腾讯直连 + 乐咕乐股 |
| 📊 基础数据 | F10 财务快照 | 通达信 |
| 📰 新闻 | 个股新闻、财联社电报（分钟级） | 东财 + 财联社 |
| 📋 研报 | 机构研报（含 PDF 下载 + 盈利预测） | 东财 |
| 🚀 信号 | **涨停板 + 强势涨停题材归因** + 概念/行业板块 | 同花顺 |
| 📑 公告 | 巨潮资讯网公告 | 巨潮 |

**40+ 个接口，6 大层面，6 源备份，覆盖量化投研的核心数据需求。**

## 3 秒开始

```bash
# 1. 安装 uv（如果还没有）
#    macOS: brew install uv
#    Windows: winget install astral.uv
#    或官方脚本: https://docs.astral.sh/uv/getting-started/installation/

# 2. 克隆
git clone https://github.com/birdilsss-byte/stoke.git && cd stoke

# 3. 安装依赖（需要 Python 3.11+）
uv sync

# 4. 查实时行情
uv run python3 -c "
from stoke import Stoke
s = Stoke()
df = s.realtime(['000001', '600000', '000858'])
print(df[['code', 'price', 'high', 'low', 'vol']].to_string())
"
```

**不需要 API Key。不需要注册。不需要付费。**

## 作为 Skill 使用（Claude Code · OpenClaw · Hermes）

Stoke 遵循 `agentskills.io` 开放标准，可在 **27+** 个 AI Agent 平台中直接安装：

```bash
# 先安装 uv（如果还没有）：brew install uv 或 winget install astral.uv
# 然后：
git clone https://github.com/birdilsss-byte/stoke.git ~/stoke
cd ~/stoke && uv sync
```

安装后设置环境变量 `STOKE_HOME` 指向克隆目录。然后在 Claude Code、OpenClaw 或 Hermes 中直接说 **"看看今天的涨停板"** 或 **"查一下平安银行行情"**，Skill 自动触发。

`SKILL.md` 同时兼容 **Claude Code** · **OpenClaw** · **Hermes**，一套文件，三平台通用。

## 项目结构

```
stoke/
├── stoke/                        # Python 包
│   ├── __init__.py               # 导出 Stoke 统一入口
│   ├── client.py                 # Stoke 门面类（自动路由数据源）
│   ├── config.py                 # 配置
│   ├── rate_limiter.py           # 限流器（带随机抖动+日志）
│   ├── utils.py                  # 自动重试装饰器
│   └── sources/                  # 6 源适配
│       ├── mootdx_source.py          # 通达信：K线、实时行情、股票列表
│       ├── akshare_source.py         # 新闻、电报、研报、公告、涨停、概念
│       ├── legulegu_source.py        # PE / PB 估值（纯 requests）
│       ├── tencent_direct_source.py  # 腾讯直连：实时行情 + K 线
│       ├── baostock_source.py        # 复权K线 + 财报 + 估值字段
│       └── efinance_source.py        # 极速K线 + 龙虎榜 + 资金流 + 股东
├── tests/                        # 测试
├── SKILL.md                      # Claude Code Skill 定义
└── pyproject.toml                # uv 依赖管理
```

## 设计原则

- **限流是铁律** — 每个数据源内置限流器，遵守平台调用间隔，不被封 IP
- **保持简单** — 不做缓存、不过度抽象、三个 Source 各自独立
- **health_check() 必实现** — 每个 Source 都能 1 秒验证连通性
- **返回 DataFrame** — 直接对接 pandas 生态

## 限流规则

| 数据源 | 间隔 | 说明 |
|--------|------|------|
| 通达信 (mootdx) | 不限流 | 原生 TCP 协议，本地解析 |
| 东财系 (akshare) | **5 秒** | 必须遵守，否则封 IP |
| 腾讯财经 | 3 秒 | 较为宽松 |

## 谁适合用？

- 🤖 **量化开发者** — 免费的数据管道，接上就能用
- 🧠 **AI Agent 开发者** — 作为工具层接入你的 AI 应用
- 📊 **个人投资者** — 在终端里快速查数据，不依赖任何付费工具
- 🎓 **学习研究** — 了解 A 股数据获取的技术方案

## 许可证

MIT — 拿去用，随便改，随便商用。

---

<p align="center">
  <sub>Built with ❤️ by <a href="https://github.com/birdilsss-byte">birdilsss-byte</a> · 
  Powered by <a href="https://github.com/mootdx/mootdx">mootdx</a> + <a href="https://github.com/akfamily/akshare">akshare</a></sub>
</p>
