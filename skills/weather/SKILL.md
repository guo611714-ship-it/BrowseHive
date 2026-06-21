---
name: weather
description: 天气查询
triggers:
  - keyword: "weather"
  - keyword: "天气"
  - keyword: "天气预报"
---

# 天气查询技能

## 功能
查询指定城市的当前天气和预报。

## 使用
```
load_skill weather "北京天气怎么样"
```

## 输出
```
城市: 北京
当前: 晴 25°C
湿度: 45%
风力: 3级
预报:
- 明天: 多云 22-28°C
- 后天: 小雨 20-25°C
```

## 注意
需要配置天气 API（如 OpenWeatherMap 或和风天气）
