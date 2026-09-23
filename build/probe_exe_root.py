"""探针：验证打包版 exe 放在「项目根」与「dist/」两种位置时，都能正确定位项目根。

背景：2026-09-23 起 exe 从 dist/ 挪到项目根（便于查找）。
`engine/config.py::_find_project_root` 在 frozen 环境下按 sys.executable 逐级向上找 data/，
本探针用「模拟 sys.frozen + 伪造 sys.executable」直接跑该函数，不启动任何进程、不写数据。

用法：
    "D:/atomcode/大学生软件/tools/Python/python.exe" build/probe_exe_root.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PY = ROOT / "src" / "engine" / "config.py"

# 待验证的 exe 位置（相对项目根）
LAYOUTS = [
    ("项目根（2026-09-23 起的新位置）", ROOT / "大学生软件.exe"),
    ("dist/（旧位置，需保持兼容）", ROOT / "dist" / "大学生软件.exe"),
    ("dist/ 的历史 .bak 版本", ROOT / "dist" / "大学生软件_v0.5_预拆chroma.exe.bak"),
]


def load_config_with_frozen_exe(exe_path: Path):
    """在「模拟打包环境」下加载 config 模块，返回其 PROJECT_ROOT。"""
    saved_frozen = getattr(sys, "frozen", None)
    saved_exe = sys.executable
    try:
        sys.frozen = True  # type: ignore[attr-defined]
        sys.executable = str(exe_path)
        spec = importlib.util.spec_from_file_location("_probe_cfg", CONFIG_PY)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.PROJECT_ROOT, mod.DATA_DIR
    finally:
        if saved_frozen is None:
            del sys.frozen  # type: ignore[attr-defined]
        else:
            sys.frozen = saved_frozen  # type: ignore[attr-defined]
        sys.executable = saved_exe
        sys.modules.pop("_probe_cfg", None)


def main() -> int:
    print(f"真实项目根（源码推导）= {ROOT}")
    print("=" * 72)
    ok = True
    for label, exe in LAYOUTS:
        if not exe.exists():
            print(f"[跳过] {label}\n        exe 不存在：{exe}")
            continue
        got_root, got_data = load_config_with_frozen_exe(exe)
        good = got_root == ROOT
        ok = ok and good
        print(f"[{'OK ' if good else 'FAIL'}] {label}")
        print(f"        exe          = {exe}")
        print(f"        PROJECT_ROOT = {got_root}")
        print(f"        DATA_DIR     = {got_data}  (存在={got_data.is_dir()})")
        print(f"        教材目录可见 = {(got_root / 'data' / 'textbooks_md').is_dir()}")
        print("-" * 72)
    print("结论：" + ("全部布局均能正确定位项目根 ✅" if ok else "存在定位错误的布局 ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
