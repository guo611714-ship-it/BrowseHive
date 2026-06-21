#!/usr/bin/env python3
import sys, os, yaml, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trigger_v2 import process_user_prompt, _load_zh_en_map, load_clusters_config, _match_zh_en_map
from marketplace import get_installed_skills

# 获取已安装的技能
installed = get_installed_skills()
print(f"Installed skills count: {len(installed)}")
print("First 50 installed skills:", sorted(installed)[:50])

# 获取 clusters.yaml 配置的技能
clusters, settings, _ = load_clusters_config(cwd=os.getcwd())
configured = set()
for cid, cdef in clusters.items():
    configured.update(cdef.get("skills", []))
print(f"Configured skills count: {len(configured)}")
print("First 50 configured skills:", sorted(configured)[:50])

# 找出未配置的技能
missing_skills = installed - configured
print(f"Missing skills count: {len(missing_skills)}")
if missing_skills:
    print("Missing skills (first 20):", sorted(missing_skills)[:20])

# 测试 ZH_EN_MAP
zh_map = _load_zh_en_map()
print(f"ZH_EN_MAP size: {len(zh_map)}")
matches = _match_zh_en_map("生成图片", zh_map, clusters)
print(f"ZH_EN_MAP matches: {matches}")

# 测试单次调用（清除 state）
import shutil
state_file = os.path.join(os.path.dirname(__file__), "state.json")
if os.path.exists(state_file):
    shutil.copy(state_file, state_file + ".bak")
    os.remove(state_file)
try:
    result = process_user_prompt({"prompt": "生成图片", "cwd": os.getcwd()})
    print("Result keys:", list(result.keys()) if result else "empty")
finally:
    # 恢复 state 备份
    if os.path.exists(state_file + ".bak"):
        shutil.move(state_file + ".bak", state_file)
