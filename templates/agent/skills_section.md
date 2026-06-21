## 已安装技能

{% for skill in skills %}
- **{{ skill.name }}**: {{ skill.description }}
{% endfor %}
