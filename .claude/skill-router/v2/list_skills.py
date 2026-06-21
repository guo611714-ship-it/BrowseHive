#!/usr/bin/env python3
import json
from pathlib import Path

# 尝试导入 yaml
try:
    import yaml
except ImportError:
    yaml = None

def load_configured_skills():
    """从 clusters.yaml 加载已配置的技能列表（去除插件前缀）"""
    configured = set()
    clusters_yaml = Path.home() / ".claude" / "skill-router" / "v2" / "clusters.yaml"
    if clusters_yaml.exists() and yaml:
        try:
            data = yaml.safe_load(clusters_yaml.read_text(encoding='utf-8'))
            clusters = data.get("clusters", {})
            for cdef in clusters.values():
                for skill in cdef.get("skills", []):
                    # 去除可能的插件前缀，如 "superpowers:dispatching-parallel-agents"
                    if ":" in skill:
                        skill = skill.split(":", 1)[1]
                    configured.add(skill)
        except Exception:
            pass
    return configured

def scan_all_skills():
    skills_info = {}  # name -> info
    configured = load_configured_skills()
    # 定义扫描目录
    scan_dirs = [
        Path.home() / ".agents" / "skills",
        Path.home() / ".claude" / "skills",
    ]
    for base_dir in scan_dirs:
        if not base_dir.exists():
            continue
        for skill_md in base_dir.rglob("SKILL.md"):
            try:
                if skill_md.stat().st_size > 0:
                    text = skill_md.read_text(encoding="utf-8", errors="ignore").strip()
                    if not text:
                        continue
                    name = skill_md.parent.name
                    # 已经记录过的 skill 跳过（去重）
                    if name in skills_info:
                        continue
                    # 提取 frontmatter 中的 description
                    description = ""
                    if text.startswith("---"):
                        end = text.find("---", 3)
                        if end != -1:
                            front = text[3:end]
                            for line in front.splitlines():
                                line = line.strip()
                                if line.lower().startswith("description:"):
                                    description = line.split(":", 1)[1].strip().strip('"').strip("'")
                                    break
                    # 若无描述，取第一行非空内容
                    if not description:
                        for line in text.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                description = line[:80] + ("..." if len(line) > 80 else "")
                                break
                    # 判断是否已在 clusters.yaml 中配置
                    status = "已配置" if name in configured else "未配置"
                    skills_info[name] = {
                        "name": name,
                        "path": str(skill_md.parent),
                        "description": description,
                        "status": status,
                    }
            except (OSError, ValueError) as e:
                continue
    return list(skills_info.values())

if __name__ == "__main__":
    skills = scan_all_skills()
    # 生成 Markdown 表格内容（UTF-8 编码直接写入文件）
    table_lines = []
    table_lines.append(f"# 已安装技能清单 (共 {len(skills)} 个)\n")
    table_lines.append("| 技能名称 | 状态 | 简要描述 |")
    table_lines.append("|----------|------|-----------|")
    for s in sorted(skills, key=lambda x: (x["status"] != "已配置", x["name"].lower())):
        desc = s["description"].replace("|", "｜") if s["description"] else ""
        table_lines.append(f"| {s['name']} | {s['status']} | {desc} |")
    # 写入文件
    output_dir = Path(__file__).parent
    md_path = output_dir / "skills_table.md"
    json_path = output_dir / "skills_inventory.json"
    md_path.write_text("\n".join(table_lines), encoding="utf-8")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(skills, f, ensure_ascii=False, indent=2)
    print(f"已生成清单: {md_path}")
    print(f"已保存JSON: {json_path}")
    print(f"总技能数: {len(skills)}")
