# subpool — 免费订阅自动聚合

把几个免费节点源自动合并成**一条自己的订阅链接**，每 6 小时由 GitHub Actions 自动更新。
安卓 / iPhone / PC / 软路由 全部吃这一条链接。

## 订阅地址

| 格式 | 地址 | 给谁用 |
|---|---|---|
| 通用订阅 | `https://fastly.jsdelivr.net/gh/lorddidi/subpool@main/sub/all.txt` | v2rayNG、Streisand、Hiddify、Shadowrocket |
| Clash 配置 | `https://fastly.jsdelivr.net/gh/lorddidi/subpool@main/sub/clash.yaml` | Clash Verge Rev、FlClash、软路由 mihomo |

jsDelivr 在国内偶尔抽风，备用镜像：把 `fastly.jsdelivr.net` 换成 `cdn.jsdelivr.net` 或前面加 `https://gh-proxy.com/`。

## 各端怎么接

- **PC（Windows）**：Clash Verge Rev → 订阅 → 新建 → 填 Clash 配置地址，订阅设置里把"自动更新"设为 6 小时
- **安卓**：FlClash（填 Clash 配置地址）或 v2rayNG（填通用订阅地址）
- **iPhone**：Streisand / Hiddify（免费）或 Shadowrocket（付费），填通用订阅地址
- **软路由（iStoreOS mihomo/netflow）**：订阅设置里填 Clash 配置地址，更新间隔 6 小时

## 改源 / 加自己的节点

- 改 `sources.txt`（一行一个订阅 URL）
- 自己的节点（如 edgetunnel 自建）写进 `my_nodes.txt`，永远排最前
- 推上去就生效，不用手动跑

## 本地手动跑

```
python merge.py
```
