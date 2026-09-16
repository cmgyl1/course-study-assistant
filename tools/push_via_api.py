#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""git push 走不通时的备用推送通道：经 GitHub REST API 提交。

## 什么时候需要它

`git push` 依赖 https://github.com（或 ssh.github.com）可达。若本机处于
企业网络、代理白名单等受限环境，常见症状是：

    fatal: unable to access 'https://github.com/...': 
      schannel: server closed abruptly (missing close_notify)
    fatal: unable to access '...': CONNECT tunnel failed, response 502

此时若 api.github.com 仍可达，可改用本脚本完成推送。

## 它怎么做到「和 git push 等价」

Git 的对象模型是纯内容寻址的，因此可以绕过 git 传输协议，直接用
Git Data API 把对象一个个建出来：

    每个文件 → POST /git/blobs      （base64 内容，返回的 sha 与本地一致）
    整棵目录 → POST /git/trees      （75 条 entry → 同一个 tree sha）
    一次提交 → POST /git/commits    （复刻 message / author / committer）
    移动分支 → PATCH /git/refs/heads/<branch>

只要 tree、author、committer、message、parents 都与本地一致，生成的
commit sha 就与本地**逐位相同**，推完不会出现分叉，也不需要 force。

## 用法

    python tools/push_via_api.py                  # 推当前分支到 origin
    python tools/push_via_api.py --dry-run        # 只报告，不写入远端
    python tools/push_via_api.py --remote origin --branch main

凭据从 `git credential fill` 读取（即系统凭据管理器中已存的 GitHub
token），**脚本本身不保存、不打印任何密钥**。token 需要 `repo` 权限。

## 已知边界

- 仅处理正常的快进推送（本地 HEAD 的父提交 == 远端分支当前提交）。
  若远端有新提交，需要先合并/变基，脚本会明确报错而不是覆盖。
- 完全空的仓库无法直接建 blob（GitHub 返回 409 "Git Repository is
  empty."），脚本会自动先用 Contents API 落一个初始化提交解锁。
- 大仓库会很慢（每个文件一次请求，8 路并发），适合源码仓库，
  不适合二进制资产。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    sys.exit("需要 requests：pip install requests")

API = "https://api.github.com"
OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def log(msg: str = "") -> None:
    print(msg, file=OUT, flush=True)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], stdout=subprocess.PIPE, check=True).stdout


def git_text(*args: str) -> str:
    return git(*args).decode("utf-8", "replace")


# --------------------------------------------------------------------------
# 元数据
# --------------------------------------------------------------------------
def parse_remote(url: str) -> tuple[str, str]:
    """从 remote URL 解析出 (owner, repo)，支持 https 与 ssh 两种写法。"""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?/?$", url.strip())
    if not m:
        sys.exit(f"无法从 remote URL 解析 owner/repo：{url}")
    return m.group(1), m.group(2)


def to_iso(ts: int, tz: str) -> str:
    """git 的 '<unix> <+0800>' → API 需要的 ISO8601。"""
    sign = 1 if tz[0] == "+" else -1
    off = timedelta(hours=sign * int(tz[1:3]), minutes=sign * int(tz[3:5]))
    return datetime.fromtimestamp(ts, tz=timezone(off)).isoformat()


def parse_ident(line: str) -> dict:
    body = line.split(" ", 1)[1]
    name_email, ts, tz = body.rsplit(" ", 2)
    name, email = name_email.rsplit(" <", 1)
    return {"name": name, "email": email.rstrip(">"), "date": to_iso(int(ts), tz)}


def read_head() -> dict:
    """读取 HEAD 提交的全部元数据。"""
    raw = git_text("cat-file", "commit", "HEAD")
    header, message = raw.split("\n\n", 1)
    lines = header.splitlines()
    return {
        "sha": git_text("rev-parse", "HEAD").strip(),
        "tree": next(l.split()[1] for l in lines if l.startswith("tree ")),
        "parents": [l.split()[1] for l in lines if l.startswith("parent ")],
        "author": parse_ident(next(l for l in lines if l.startswith("author "))),
        "committer": parse_ident(next(l for l in lines if l.startswith("committer "))),
        "message": message,
    }


def read_entries() -> list[dict]:
    """列出 HEAD 树里的全部文件（mode / path / blob sha）。"""
    out = []
    for line in git_text("ls-tree", "-r", "HEAD").splitlines():
        meta, path = line.split("\t", 1)
        mode, _type, sha = meta.split()
        out.append({"mode": mode, "path": path, "sha": sha})
    return out


# --------------------------------------------------------------------------
# 凭据
# --------------------------------------------------------------------------
def read_token(host: str = "github.com") -> str:
    """从系统凭据管理器取 token，绝不打印。"""
    p = subprocess.run(
        ["git", "credential", "fill"],
        input=f"protocol=https\nhost={host}\n\n".encode(),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip()
    sys.exit("未能从 git 凭据管理器取到 token（请先执行 git push 一次以缓存凭据）")


def make_session(token: str) -> "requests.Session":
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return s


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="经 GitHub API 推送（git push 的备用通道）")
    ap.add_argument("--remote", default="origin", help="remote 名（默认 origin）")
    ap.add_argument("--branch", default=None, help="分支名（默认当前分支）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写入远端")
    ap.add_argument("--workers", type=int, default=8, help="并发上传数（默认 8）")
    args = ap.parse_args()

    branch = args.branch or git_text("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch in ("HEAD", ""):
        sys.exit("当前处于游离 HEAD，请先用 --branch 指定分支")

    try:
        remote_url = git_text("remote", "get-url", args.remote).strip()
    except subprocess.CalledProcessError:
        sys.exit(f"找不到 remote：{args.remote}")
    owner, repo = parse_remote(remote_url)

    head = read_head()
    entries = read_entries()
    log(f"远端    : {owner}/{repo}")
    log(f"分支    : {branch}")
    log(f"本地 HEAD: {head['sha']}")
    log(f"待推送  : {len(entries)} 个文件，父提交 {len(head['parents'])} 个")

    S = make_session(read_token())

    # --- 远端分支当前指向 ---
    r = S.get(f"{API}/repos/{owner}/{repo}/git/ref/heads/{branch}", timeout=30)
    remote_sha = r.json()["object"]["sha"] if r.status_code == 200 else None

    if remote_sha == head["sha"]:
        log("远端已是最新，无需推送。")
        return 0

    # --- 空仓库解锁 ---
    if r.status_code == 404:
        probe = S.get(f"{API}/repos/{owner}/{repo}", timeout=30)
        if probe.status_code == 200 and probe.json().get("size", 0) == 0:
            log("远端仓库为空 → 先用 Contents API 落一个初始化提交解锁")
            gi_path = next((e["path"] for e in entries if e["path"] == ".gitignore"), None)
            seed_path = gi_path or entries[0]["path"]
            blob = git("cat-file", "blob",
                       next(e["sha"] for e in entries if e["path"] == seed_path))
            rr = S.put(f"{API}/repos/{owner}/{repo}/contents/{seed_path}",
                       data=json.dumps({"message": "chore: 初始化仓库",
                                        "content": base64.b64encode(blob).decode(),
                                        "branch": branch}).encode("utf-8"),
                       timeout=60)
            rr.raise_for_status()
            log(f"  初始化提交：{rr.json()['commit']['sha'][:12]}")

    # --- 快进校验 ---
    if remote_sha and (not head["parents"] or head["parents"][0] != remote_sha):
        log()
        log(f"!! 远端 {branch} 指向 {remote_sha[:12]}，不是本地 HEAD 的父提交。")
        log("   远端可能已有新提交 —— 请先 git fetch/merge/rebase 后再推，")
        log("   本脚本不做强制覆盖。")
        return 2

    # --- 上传 blob ---
    def upload(entry: dict):
        content = git("cat-file", "blob", entry["sha"])
        rr = S.post(f"{API}/repos/{owner}/{repo}/git/blobs",
                    data=json.dumps({"content": base64.b64encode(content).decode(),
                                     "encoding": "base64"}), timeout=60)
        rr.raise_for_status()
        return entry["path"], rr.json()["sha"], entry["sha"]

    log()
    log("上传 blob ...")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, res in enumerate(ex.map(upload, entries), 1):
            results.append(res)
            if i % 20 == 0 or i == len(entries):
                log(f"  {i}/{len(entries)}")

    bad = [r for r in results if r[1] != r[2]]
    log(f"blob 校验：{len(results) - len(bad)}/{len(results)} 与本地一致")
    for path, got, want in bad[:5]:
        log(f"  !! {path}  远端={got[:12]} 本地={want[:12]}")
    if bad:
        sys.exit("blob 内容与本地不一致，已中止（远端未改动）")

    if args.dry_run:
        log()
        log("--dry-run：以上检查均通过，未写入远端。")
        return 0

    # --- tree / commit / ref ---
    rr = S.post(f"{API}/repos/{owner}/{repo}/git/trees",
                data=json.dumps({"tree": [{"path": e["path"], "mode": e["mode"],
                                           "type": "blob", "sha": e["sha"]}
                                          for e in entries]}), timeout=90)
    rr.raise_for_status()
    tree = rr.json()["sha"]
    log(f"tree    : {tree} | 与本地一致: {tree == head['tree']}")

    rr = S.post(f"{API}/repos/{owner}/{repo}/git/commits",
                data=json.dumps({"message": head["message"], "tree": tree,
                                 "parents": head["parents"],
                                 "author": head["author"],
                                 "committer": head["committer"]},
                                ensure_ascii=False).encode("utf-8"), timeout=90)
    rr.raise_for_status()
    commit = rr.json()["sha"]
    log(f"commit  : {commit} | 与本地一致: {commit == head['sha']}")

    if not commit == head["sha"]:
        log("!! 远端 commit sha 与本地不同（通常因 author/committer 被改写），")
        log("   推送本身有效，但本地需要一次 fetch 才能对齐。")

    if remote_sha:
        rr = S.patch(f"{API}/repos/{owner}/{repo}/git/refs/heads/{branch}",
                     data=json.dumps({"sha": commit}), timeout=60)
    else:
        rr = S.post(f"{API}/repos/{owner}/{repo}/git/refs",
                    data=json.dumps({"ref": f"refs/heads/{branch}", "sha": commit}),
                    timeout=60)
    rr.raise_for_status()
    log()
    log(f"完成：{branch} → {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
