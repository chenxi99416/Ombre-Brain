#!/usr/bin/env python3
# ============================================================
# SessionStart Hook: auto-breath + dreaming on session start
# 对话开始钩子：自动浮现记忆 + 触发 dreaming
#
# On SessionStart, this script calls the Ombre Brain MCP server's
# breath-hook and dream-hook endpoints, printing results to stdout
# so Claude sees them as session context.
#
# Sequence: breath → dream
# 顺序：呼吸浮现 → 做梦消化
#
# Config:
#   OMBRE_HOOK_URL  — override the server URL (default: http://localhost:8000)
#   OMBRE_HOOK_SKIP — set to "1" to disable the hook temporarily
# ============================================================

import os
import sys
import urllib.request
import urllib.error

def main():
    # Allow disabling the hook via env var
    if os.environ.get("OMBRE_HOOK_SKIP") == "1":
        sys.exit(0)

    base_url = os.environ.get("OMBRE_HOOK_URL", "http://localhost:8000").rstrip("/")

    success = False

    # --- Step 1: Breath — surface unresolved memories (includes handoff if recent) ---
    success = _call_endpoint(base_url, "/breath-hook") or success

    # --- Step 2: Dream — digest recent memories ---
    success = _call_endpoint(base_url, "/dream-hook") or success

    if not success:
        print("[Ombre Brain] 远程连接失败，请手动执行以下步骤：")
        print("1. 用 ToolSearch 加载 breath 工具，然后调用 breath()（不传参数）")
        print("2. 用 ToolSearch 加载 dream 工具，然后调用 dream()")
        print("3. 读完再开始和用户说话")
        print("提示：她叫希希。思考链用中文。")


def _call_endpoint(base_url, path):
    req = urllib.request.Request(
        f"{base_url}{path}",
        headers={"Accept": "text/plain"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read().decode("utf-8")
            output = raw.strip()
            if output:
                print(output)
                return True
    except (urllib.error.URLError, OSError):
        pass
    except Exception:
        pass
    return False


if __name__ == "__main__":
    main()
