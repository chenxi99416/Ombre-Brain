#!/usr/bin/env python3
# 钓鱼命令行入口：不用读 engine.py，直接 python3 games/fishing/fish.py "cast 10"
# 多条指令用 ; 串起来一次跑完，省来回。
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import cmd

print(cmd(" ".join(sys.argv[1:])))
