## 子代理

{% for agent in subagents %}
### {{ agent.display_name }}
- **描述**: {{ agent.description }}
- **工具白名单**: {{ agent.allowed_tools|join(', ') }}
- **最大轮数**: {{ agent.max_turns }}
{% endfor %}
