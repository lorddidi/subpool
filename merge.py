#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
subpool — 免费订阅聚合器（零依赖，只用 Python 标准库）

读取 sources.txt 里的免费订阅（base64 或明文分享链接均可），
合并 my_nodes.txt（你自己的节点，永远排最前、不会被去重挤掉），
去重、限量后输出两种通用格式：

  sub/all.txt     base64 通用订阅 → v2rayNG / Shadowrocket / Streisand / Hiddify
  sub/clash.yaml  Clash Meta 配置 → Clash Verge / FlClash / 软路由 mihomo

用法：python merge.py
"""
import base64
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).parent
MAX_NODES = 400          # 总节点上限（免费源动辄几千个，客户端吃不下）
SUPPORTED = ("ss://", "vmess://", "vless://", "trojan://", "hysteria2://")

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}


# ---------- 抓取 ----------

def fetch(url):
    """raw.githubusercontent 优先，失败换 jsDelivr / gh-proxy 镜像。"""
    cands = [url]
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)", url)
    if m:
        owner, repo, ref, path = m.groups()
        cands.append(f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{ref}/{path}")
        cands.append(f"https://gh-proxy.com/{url}")
    last_err = None
    for u in cands:
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last_err = e
    print(f"[warn] 抓取失败 {url}: {last_err}", file=sys.stderr)
    return ""


def b64d(s):
    s = s.strip().rstrip("=")
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "replace")


def parse_source(text):
    """返回分享链接行列表；先尝试整文件 base64（标准订阅），失败按明文逐行。"""
    text = text.strip()
    if not text:
        return []
    lines = []
    try:
        dec = b64d(text.replace("\n", ""))
        if "://" in dec:
            lines = dec.splitlines()
    except Exception:  # noqa: BLE001
        pass
    if not lines:
        lines = text.splitlines()
    return [l.strip() for l in lines if l.strip().startswith(SUPPORTED)]


# ---------- 解析分享链接 → clash dict ----------

def qs(s):
    d = {}
    for kv in s.split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            d[k.lower()] = urllib.parse.unquote(v)
    return d


def split_hostport(hp):
    if ":" not in hp:
        return None, None
    host, port = hp.rsplit(":", 1)
    try:
        port = int(port)
    except ValueError:
        return None, None
    if not re.match(r"^[A-Za-z0-9._\-]+$", host) or not 0 < port < 65536:
        return None, None
    return host, port


def node_name(frag, prefix, host):
    name = urllib.parse.unquote(frag).strip() if frag else ""
    return name or f"{prefix} {host}"


def parse_ss(line):
    body = line[6:]
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
    try:
        if "@" in body:
            userinfo, hostport = body.rsplit("@", 1)
            if ":" in userinfo:
                method, pwd = userinfo.split(":", 1)
                pwd = b64d(pwd)
            else:
                method, pwd = b64d(userinfo).split(":", 1)
        else:
            userinfo, hostport = b64d(body).rsplit("@", 1)
            method, pwd = userinfo.split(":", 1)
    except Exception:  # noqa: BLE001
        return None
    host, port = split_hostport(hostport)
    if not host:
        return None
    p = {"name": node_name(frag, "SS", host), "type": "ss", "server": host,
         "port": port, "cipher": method, "password": pwd}
    plug = qs(query).get("plugin", "")
    if plug.startswith("obfs"):
        opts = dict(kv.split("=", 1) for kv in plug.split(";") if "=" in kv)
        p["plugin"] = "obfs"
        p["plugin-opts"] = {"mode": opts.get("obfs", "http"),
                            "host": opts.get("obfs-host", "")}
    elif plug.startswith("v2ray-plugin"):
        opts = dict(kv.split("=", 1) for kv in plug[len("v2ray-plugin"):].strip(";=").split(";") if "=" in kv)
        p["plugin"] = "v2ray-plugin"
        p["plugin-opts"] = {"mode": "websocket", "host": opts.get("host", ""),
                            "path": opts.get("path", "/"), "tls": bool(opts.get("host"))}
    return p


def parse_vmess(line):
    body = line[7:]
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
    try:
        j = json.loads(b64d(body))
    except Exception:  # noqa: BLE001
        return None
    host, port = split_hostport(f"{j.get('add','')}:{j.get('port','')}")
    if not host or not j.get("id"):
        return None
    p = {"name": node_name(frag, "VMess", host), "type": "vmess", "server": host,
         "port": port, "uuid": j["id"], "alterId": int(j.get("aid") or 0),
         "cipher": "auto", "udp": True}
    net = j.get("net", "tcp")
    if net != "tcp":
        p["network"] = net
    if net == "ws":
        p["ws-opts"] = {"path": j.get("path", "/"),
                        "headers": ({"Host": j["host"]} if j.get("host") else {})}
    if j.get("tls") in ("tls", "https"):
        p["tls"] = True
        p["servername"] = j.get("sni") or j.get("host", "")
        p["skip-cert-verify"] = True
    return p


def parse_vless(line):
    body = line[7:]
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
    if "@" not in body:
        return None
    uuid, hostport = body.rsplit("@", 1)
    host, port = split_hostport(hostport)
    if not host or not uuid:
        return None
    q = qs(query)
    p = {"name": node_name(frag, "VLESS", host), "type": "vless", "server": host,
         "port": port, "uuid": urllib.parse.unquote(uuid), "udp": True}
    net = q.get("type") or q.get("network", "tcp")
    if net != "tcp":
        p["network"] = net
        if net == "ws":
            p["ws-opts"] = {"path": q.get("path", "/"),
                            "headers": ({"Host": q["host"]} if q.get("host") else {})}
        elif net == "grpc":
            p["grpc-opts"] = {"grpc-service-name": q.get("servicename", "")}
    sec = q.get("security", "")
    if sec == "tls":
        p["tls"] = True
        p["servername"] = q.get("sni", "")
        p["skip-cert-verify"] = True
        if q.get("fingerprint"):
            p["client-fingerprint"] = q["fingerprint"]
        if q.get("flow"):
            p["flow"] = q["flow"]
    elif sec == "reality":
        p["reality"] = True
        p["tls"] = True
        p["servername"] = q.get("sni", "")
        p["public-key"] = q.get("pbk", "")
        p["short-id"] = q.get("sid", "")
        p["skip-cert-verify"] = True
        if q.get("fingerprint"):
            p["client-fingerprint"] = q["fingerprint"]
        if q.get("flow"):
            p["flow"] = q["flow"]
    return p


def parse_trojan(line):
    body = line[8:]
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
    if "@" not in body:
        return None
    pwd, hostport = body.rsplit("@", 1)
    host, port = split_hostport(hostport)
    if not host:
        return None
    q = qs(query)
    p = {"name": node_name(frag, "Trojan", host), "type": "trojan", "server": host,
         "port": port, "password": urllib.parse.unquote(pwd),
         "sni": q.get("sni", ""), "skip-cert-verify": True, "udp": True}
    if q.get("type") == "ws":
        p["network"] = "ws"
        p["ws-opts"] = {"path": q.get("path", "/"),
                        "headers": ({"Host": q["host"]} if q.get("host") else {})}
    return p


def parse_hysteria2(line):
    body = line[12:]
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
    pwd, hostport = (body.rsplit("@", 1) if "@" in body else ("", body))
    host, port = split_hostport(hostport)
    if not host:
        return None
    q = qs(query)
    p = {"name": node_name(frag, "Hy2", host), "type": "hysteria2", "server": host,
         "port": port, "password": urllib.parse.unquote(pwd), "sni": q.get("sni", ""),
         "skip-cert-verify": True, "udp": True}
    if q.get("obfs"):
        p["obfs"] = q["obfs"]
        p["obfs-password"] = q.get("obfs-password", "")
    return p


PARSERS = {"ss://": parse_ss, "vmess://": parse_vmess, "vless://": parse_vless,
           "trojan://": parse_trojan, "hysteria2://": parse_hysteria2}


def parse_line(line):
    for prefix, fn in PARSERS.items():
        if line.startswith(prefix):
            try:
                return fn(line)
            except Exception:  # noqa: BLE001
                return None
    return None


def dedup_key(clash):
    cred = clash.get("uuid") or clash.get("password") or ""
    return (clash["type"], clash["server"], clash["port"], cred)


# ---------- YAML 输出（手写 emitter，避免第三方依赖） ----------

def yq(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return '"' + s + '"'


def ydump(obj, ind=0):
    sp = "  " * ind
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and v:
                out.append(f"{sp}{k}:")
                out.append(ydump(v, ind + 1))
            elif isinstance(v, list) and v:
                out.append(f"{sp}{k}:")
                out.append(ydump(v, ind + 1))
            elif isinstance(v, dict):
                out.append(f"{sp}{k}: {{}}")
            elif isinstance(v, list):
                out.append(f"{sp}{k}: []")
            else:
                out.append(f"{sp}{k}: {yq(v)}")
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, (dict, list)) and it:
                sub = ydump(it, ind + 1)
                first, _, rest = sub.partition("\n")
                out.append(f"{sp}- {first.strip()}")
                if rest:
                    out.append(rest)
            else:
                out.append(f"{sp}- {yq(it)}")
    return "\n".join(out)


# ---------- 主流程 ----------

def read_list_file(path):
    if not path.exists():
        return []
    lines = []
    for l in path.read_text("utf-8").splitlines():
        l = l.strip()
        if l and not l.startswith("#"):
            lines.append(l)
    return lines


def main():
    sources = read_list_file(ROOT / "sources.txt")
    my_lines = [l for l in read_list_file(ROOT / "my_nodes.txt") if l.startswith(SUPPORTED)]

    nodes = []           # [{raw, clash}]
    seen = set()

    def add(raw, mine=False):
        if len(nodes) >= MAX_NODES:
            return False
        clash = parse_line(raw)
        if not clash:
            return False
        k = dedup_key(clash)
        if k in seen and not mine:
            return False
        seen.add(k)
        nodes.append({"raw": raw, "clash": clash, "mine": mine})
        return True

    # 自己的节点优先
    for l in my_lines:
        add(l, mine=True)

    # 免费源
    for url in sources:
        text = fetch(url)
        got = 0
        for l in parse_source(text):
            if add(l):
                got += 1
            if len(nodes) >= MAX_NODES:
                break
        print(f"[ok] {url} -> 新增 {got}（累计 {len(nodes)}）")

    # 名字去重（clash 里重名会互相覆盖）
    names = {}
    for n in nodes:
        nm = n["clash"]["name"]
        if nm in names:
            names[nm] += 1
            n["clash"]["name"] = f"{nm} #{names[nm]}"
        else:
            names[nm] = 0

    outdir = ROOT / "sub"
    outdir.mkdir(exist_ok=True)

    # 通用订阅（保留原始分享链接，无损）
    blob = "\n".join(n["raw"] for n in nodes)
    (outdir / "all.txt").write_text(
        base64.b64encode(blob.encode("utf-8")).decode("ascii") + "\n", "utf-8")

    # Clash Meta 配置（照抄免费订阅项目的通用模板：自动选择 + 手动选择 + 国内直连）
    proxy_names = [n["clash"]["name"] for n in nodes]
    cfg = {
        "mixed-port": 7890,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "proxies": [n["clash"] for n in nodes],
        "proxy-groups": [
            {"name": "自动选择", "type": "url-test", "proxies": proxy_names,
             "url": "https://www.gstatic.com/generate_204", "interval": 300},
            {"name": "节点选择", "type": "select",
             "proxies": ["自动选择"] + proxy_names + ["DIRECT"]},
        ],
        "rules": [
            "GEOSITE,private,DIRECT",
            "GEOIP,LAN,DIRECT,no-resolve",
            "GEOIP,CN,DIRECT",
            "MATCH,节点选择",
        ],
    }
    (outdir / "clash.yaml").write_text(ydump(cfg) + "\n", "utf-8")

    print(f"[done] 共 {len(nodes)} 个节点 -> sub/all.txt, sub/clash.yaml")


if __name__ == "__main__":
    main()
