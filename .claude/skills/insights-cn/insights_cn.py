#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中文 Insights 报告生成器（优化版）
基于 lakon、facets 和使用数据生成全面中文洞察报告
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict

# 设置标准输出编码为 UTF-8 (兼容 Windows)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_lakon_gain():
    """运行 lakon gain 获取 token 节省统计"""
    try:
        result = subprocess.run(['lakon', 'gain'], capture_output=True, text=False)
        output = result.stdout.decode('utf-8', errors='replace')
        return output
    except FileNotFoundError:
        return "[错误] 未找到 lakon 命令，请确保 lakon 已安装并在 PATH 中"
    except Exception as e:
        return f"[错误] 无法获取 lakon 数据: {e}"

def load_facets_data():
    """加载并聚合所有 facets JSON 数据"""
    facets_path = Path.home() / '.claude' / 'usage-data' / 'facets'
    if not facets_path.exists():
        return None

    facets_files = list(facets_path.glob('*.json'))
    if not facets_files:
        return None

    data = []
    for f in facets_files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
                data.append(json.load(fp))
        except Exception:
            continue

    return data

def aggregate_facets(data):
    """聚合 facets 统计数据"""
    if not data:
        return None

    total = len(data)

    # 会话类型分布
    session_types = Counter(d.get('session_type', 'unknown') for d in data)

    # 结果分布
    outcomes = Counter(d.get('outcome', 'unknown') for d in data)

    # 目标类别分布
    goal_categories = Counter()
    for d in data:
        for cat in d.get('goal_categories', {}).keys():
            goal_categories[cat] += d['goal_categories'][cat]

    # 摩擦类型统计
    friction_counts = Counter()
    for d in data:
        for fric, count in d.get('friction_counts', {}).items():
            friction_counts[fric] += count

    # Claude帮助程度
    helpfulness = Counter(d.get('claude_helpfulness', 'unknown') for d in data)

    # 用户满意度
    satisfaction = {'likely_satisfied': 0, 'neutral': 0, 'likely_dissatisfied': 0}
    for d in data:
        ls = d.get('user_satisfaction_counts', {})
        satisfaction['likely_satisfied'] += ls.get('likely_satisfied', 0)
        satisfaction['neutral'] += ls.get('neutral', 0)
        satisfaction['likely_dissatisfied'] += ls.get('likely_dissatisfied', 0)

    # 成功案例摘要 (用 Counter 存储 primary_success)
    primary_success_counts = Counter(d.get('primary_success', 'unknown') for d in data)
    success_details = defaultdict(list)
    for d in data:
        if d.get('brief_summary'):
            success_details[d.get('primary_success', 'unknown')].append(d['brief_summary'])

    # 失败案例分析
    friction_details = []
    for d in data:
        if d.get('friction_detail'):
            friction_details.append({
                'type': max(d.get('friction_counts', {}).items(), key=lambda x: x[1])[0] if d.get('friction_counts') else 'unknown',
                'detail': d['friction_detail'],
                'session_type': d.get('session_type', 'unknown')
            })

    # 日期范围
    dates = [d.get('date', '') for d in data if d.get('date')]
    date_range = f"{min(dates)} 至 {max(dates)}" if dates else "未知"

    return {
        'total': total,
        'date_range': date_range,
        'session_types': session_types,  # 保持为 Counter
        'outcomes': outcomes,  # 保持为 Counter
        'goal_categories': goal_categories,  # 保持为 Counter
        'friction_counts': friction_counts,  # 保持为 Counter
        'helpfulness': helpfulness,  # 保持为 Counter
        'satisfaction': satisfaction,
        'primary_success_counts': primary_success_counts,  # 保持为 Counter
        'success_details': dict(success_details),
        'friction_details': friction_details[:10]  # 只保留前10个案例
    }

def map_goal_to_work_type(goal_name):
    """将目标类别映射为工作类型描述"""
    mapping = {
        'bug_fix': 'Bug 修复',
        'configuration': '配置管理',
        'configuration_change': '配置变更',
        'feature_implementation': '功能开发',
        'testing_verification': '测试验证',
        'testing': '测试工作',
        'debugging_and_fixing': '调试修复',
        'warmup_minimal': '系统预热',
        'system_configuration': '系统配置',
        'exploration': '代码探索',
        'multi_task': '多任务处理',
        'documentation': '文档编写',
    }
    return mapping.get(goal_name, goal_name.replace('_', ' ').title())

def translate_outcome(outcome):
    """翻译结果状态"""
    mapping = {
        'fully_achieved': '完全达成',
        'mostly_achieved': '基本达成',
        'partially_achieved': '部分达成',
        'not_achieved': '未达成',
        'unclear_from_transcript': '状态不明',
        'unknown': '未知'
    }
    return mapping.get(outcome, outcome)

def translate_session_type(stype):
    """翻译会话类型"""
    mapping = {
        'iterative_refinement': '迭代优化',
        'multi_task': '多任务',
        'single_task': '单任务',
        'exploration': '探索',
        'quick_question': '快速问题',
        'unknown': '未知'
    }
    return mapping.get(stype, stype)

def translate_friction(fric):
    """翻译摩擦类型"""
    mapping = {
        'wrong_approach': '错误方法',
        'buggy_code': '代码错误',
        'misunderstood_request': '误解请求',
        'user_rejected_action': '用户拒绝',
        'excessive_changes': '过度修改',
        'network_auth_issues': '网络认证问题',
        'unknown': '其他'
    }
    return mapping.get(fric, fric)

def generate_report():
    """生成中文洞察报告"""
    print("=" * 70)
    print("Claude Code 中文洞察报告")
    print("=" * 70)
    print()

    # Token 节省统计
    print("## Token 效率")
    print("-" * 70)
    lakon_output = run_lakon_gain()
    print(lakon_output)
    print()

    # 聚合 facets 数据
    facets_data = load_facets_data()
    stats = aggregate_facets(facets_data) if facets_data else None

    if not stats:
        print("## 会话概览")
        print("-" * 70)
        print("[提示] 未找到使用统计 facets 数据")
        print("运行 `/insights` 生成完整英文分析报告")
        print()
        print("=" * 70)
        print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        return

    # 概览
    print("## 会话概览")
    print("-" * 70)
    print(f"总会话数: **{stats['total']}** 个会话")
    print(f"时间范围: {stats['date_range']}")
    print(f"会话类型分布:")
    for stype, count in sorted(stats['session_types'].items(), key=lambda x: -x[1])[:5]:
        print(f"  - {translate_session_type(stype)}: {count} 次 ({count/stats['total']*100:.1f}%)")

    print()
    print("## 核心指标")
    print("-" * 70)
    # 结果分布
    print("**任务完成情况:**")
    for outcome, count in sorted(stats['outcomes'].items(), key=lambda x: -x[1]):
        pct = count / stats['total'] * 100
        marker = "✅" if outcome in ['fully_achieved', 'mostly_achieved'] else "⚠️" if outcome == 'partially_achieved' else "❌"
        print(f"  {marker} {translate_outcome(outcome)}: {count} 次 ({pct:.1f}%)")

    print()
    print("**用户满意度:**")
    total_sat = sum(stats['satisfaction'].values())
    for label, count in [('满意', stats['satisfaction']['likely_satisfied']),
                         ('中性', stats['satisfaction']['neutral']),
                         ('不满意', stats['satisfaction']['likely_dissatisfied'])]:
        if total_sat > 0:
            pct = count / total_sat * 100
            emoji = "😊" if label == '满意' else "😟" if label == '不满意' else "😐"
            print(f"  {emoji} {label}: {count} 次 ({pct:.1f}%)")

    print()
    print("**Claude 帮助程度:**")
    for level, count in sorted(stats['helpfulness'].items(), key=lambda x: -x[1]):
        pct = count / stats['total'] * 100
        marker = "👍" if level == 'very_helpful' else "👌" if level == 'moderately_helpful' else "👎"
        print(f"  {marker} {level.replace('_', ' ').title()}: {count} 次 ({pct:.1f}%)")

    print()
    print("## 工作重点 (What You Work On)")
    print("-" * 70)
    print("从目标类别分析你的主要工作方向:")
    for i, (goal, count) in enumerate(stats['goal_categories'].most_common(8), 1):
        work_type = map_goal_to_work_type(goal)
        pct = count / stats['total'] * 100
        marker = "🔧" if 'bug' in goal else "⚙️" if 'config' in goal else "✨" if 'feature' in goal else "🧪"
        print(f"{marker} **{work_type}**: {count} 次 ({pct:.1f}%)")

    print()
    print("## 使用模式分析 (How You Use CC)")
    print("-" * 70)
    print("你的交互特征:")
    print(f"  - 主要会话类型: **{translate_session_type(max(stats['session_types'], key=stats['session_types'].get))}**")
    iterative_count = stats['session_types'].get('iterative_refinement', 0)
    if iterative_count > stats['total'] * 0.3:
        print(f"  - 高频使用迭代优化模式 ({iterative_count} 次)")

    multi_count = stats['session_types'].get('multi_task', 0)
    if multi_count > 0:
        print(f"  - 擅长多任务并行处理 ({multi_count} 次)")

    print(f"  - 整体任务成功率: {(stats['outcomes'].get('fully_achieved', 0) + stats['outcomes'].get('mostly_achieved', 0)) / stats['total'] * 100:.1f}%")

    print()
    print("## 做得好的 (Impressive Things You Did)")
    print("-" * 70)
    print("高频成功模式:")

    # 从 primary_success 提取
    for success_type, count in sorted(stats['primary_success_counts'].items(), key=lambda x: -x[1])[:5]:
        if success_type != 'unknown' and count >= 2:
            marker = {"good_debugging": "🐛", "multi_file_changes": "📁", "correct_code_edits": "✅", "good_explanation": "📚", "proactive_help": "🤝", "fast_search": "🔍"}.get(success_type, "⭐")
            print(f"  {marker} **{success_type.replace('_', ' ').title()}**: {count} 次")
            if success_type in stats['success_details'] and stats['success_details'][success_type]:
                example = stats['success_details'][success_type][0][:100] + "..."
                print(f"     示例: {example}")

    print()
    print("## 问题所在 (Where Things Go Wrong)")
    print("-" * 70)

    # 摩擦类型
    print("**主要摩擦源:**")
    total_friction = sum(stats['friction_counts'].values())
    for fric, count in sorted(stats['friction_counts'].items(), key=lambda x: -x[1])[:6]:
        pct = count / total_friction * 100 if total_friction > 0 else 0
        marker = {"wrong_approach": "⚠️", "buggy_code": "🐛", "misunderstood_request": "❓", "user_rejected_action": "🚫", "excessive_changes": "📈", "network_auth_issues": "🔐"}.get(fric, "•")
        print(f"  {marker} {translate_friction(fric)}: {count} 次 ({pct:.1f}%)")

    print()
    print("**典型案例分析:**")
    for i, case in enumerate(stats['friction_details'][:3], 1):
        print(f"  {i}. [{translate_friction(case['type'])}] {case['detail'][:120]}...")

    print()
    print("## 值得尝试的功能 (Existing CC Features to Try)")
    print("-" * 70)
    print("根据你的使用模式，建议尝试以下配置优化:")

    # 基于摩擦类型给出建议
    if 'wrong_approach' in stats['friction_counts'] and stats['friction_counts']['wrong_approach'] > 30:
        print("  - **优先检查重启**: 在调试 MCP/工具问题时，首先尝试重启服务而非修改代码")
        print("  - **CLAUE.md 指导**: 添加'先重启后调试'规则，避免过度复杂化")

    if 'misunderstood_request' in stats['friction_counts'] and stats['friction_counts']['misunderstood_request'] > 15:
        print("  - **使用确认步骤**: 复杂任务前让Claude复述理解，确保对齐")

    if 'excessive_changes' in stats['friction_counts'] and stats['friction_counts']['excessive_changes'] > 5:
        print("  - **明确边界**: 配置 Stop Hook 限制自主执行范围")

    print()
    print("  - **自定义技能**: 为重复性任务（MCP检查、配置迁移）创建 /技能")
    print("  - **Hooks 自动化**: 配置 PostEdit Hook 自动验证JSON/YAML语法")
    print("  - **Headless模式**: 自动化Ralph优化循环，减少权限提示中断")

    print()
    print("## 新兴使用模式 (New Usage Patterns)")
    print("-" * 70)

    # 识别模式
    if stats['total'] > 50:
        print(f"  你的 {stats['total']} 次会话呈现以下趋势:")

        if iterative_count > stats['total'] * 0.4:
            print("  - **深度迭代**: 习惯通过多次循环逼近完美解决方案")

        if multi_count > stats['total'] * 0.15:
            print("  - **并行思维**: 将大型任务分解为多个子任务同时推进")

        if stats['goal_categories'].get('configuration', 0) > 10:
            print("  - **配置驱动**: 大量时间投入在环境搭建和配置优化")

        if any('browser' in str(k).lower() or 'mcp' in str(k).lower() for k in stats['goal_categories'].keys()):
            print("  - **平台集成**: 专注于 MCP 工作流和浏览器自动化")

    print()
    print("## 未来方向 (On the Horizon)")
    print("-" * 70)
    print("基于数据驱动的改进建议:")

    wrong_approach_count = stats['friction_counts'].get('wrong_approach', 0)
    if wrong_approach_count > 40:
        print("  1. **自优化代理**: 建立失败模式库，自动检测并切换策略")
        print("     - 记录失败尝试类型")
        print("     - 连续3次失败后触发策略切换")
        print("     - 保存成功方案供后续复用")

    if stats['total'] > 60:
        print("  2. **并行任务编排**: 将配置类任务分解为独立代理并行执行")
        print("     - 使用 headless 模式")
        print("     - 每个代理负责单一配置领域")
        print("     - 协调器合并结果并验证一致性")

    buggy_count = stats['friction_counts'].get('buggy_code', 0)
    if buggy_count > 40:
        print("  3. **测试驱动迭代**: 每代码修改后自动运行验证")
        print("     - 配置 PreToolUse Hook 拦截修改")
        print("     - 自动执行测试套件")
        print("     - 失败时自动回滚并记录原因")

    print()
    print("## 团队反馈 (Team Feedback)")
    print("-" * 70)
    print("基于你的使用数据总结:")
    print(f"  ✅ **优势**: 高容忍度迭代、技术深度强、自主性强")
    total_fr = sum(stats['friction_counts'].values())
    if total_fr > 0:
        wrong_pct = stats['friction_counts'].get('wrong_approach', 0) / total_fr * 100
        if wrong_pct > 50:
            print(f"  ⚠️ **改进点**: {wrong_pct:.0f}% 的摩擦来自错误方法选择")
            print("     建议: 实施'先简单后复杂'调试原则")

    print()
    print("=" * 70)
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("数据来源: lakon + usage-data/facets | 建议运行 `/insights` 查看完整英文报告")
    print("=" * 70)

if __name__ == '__main__':
    generate_report()
