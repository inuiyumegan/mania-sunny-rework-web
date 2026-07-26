# mania-sunny-rework-web

基于 [Sunny Rework](https://github.com/sunnyxxy/Star-Rating-Rebirth) 算法的 osu!mania 谱面难度与 PP 估算 Chrome 扩展（edge等支持扩展的浏览器均可使用）。在 osu! 官网谱面页直接查看 Sunny Rework 星数、RC 段位、以及实时 PP 计算。

## 功能

- **Sunny Rework 星数** — 4K/6K/7K 的 Sunny Rework 难度星数估算
- **Daniel 算法** — 4K RC 的 Daniel 段位估算 (Alpha ~ Theta)
- **RC / LN 段位** — 根据 LN 占比自动显示 RC 段位或 RC+LN 混合段位
- **PP 估算** — NM/DT/HT 三列实时 PP 计算，支持自定义倍速 (0.5x ~ 2.0x)
- **MOD 支持** — SV1/SV2/NF/EZ/HO/IN 等 mod 组合
- **自定义 OD** — 独立调节 OD 值，自动重新计算星数
- **判定输入** — 手动输入 miss 和判定数以计算实际 Acc 对应的 PP
- **HO/IN 转换** — 一键切换 HO (纯米) 和 IN (反转) 模式，分别计算对应的星数和 PP

## 安装

1. 下载本仓库 ZIP 或 `git clone`
2. 打开 Chrome，进入 `chrome://extensions/`
3. 开启「开发者模式」
4. 点击「加载已解压的扩展程序」，选择仓库目录
5. 打开任意 osu! 谱面页面 (如 `https://osu.ppy.sh/beatmapsets/xxx#mania/xxx`)
6. 点击扩展图标即可查看难度分析

## 使用

| 功能 | 说明 |
|------|------|
| **DT / NM / HT** | 三列分别显示 1.5x / 1.0x / 0.75x 的星数和 PP |
| **倍速滑块** | 支持 0.5x ~ 2.0x 自定义倍速，预设快捷键快速切换 |
| **判定输入** | 输入 320/300/200/100/50/miss 数量计算实时 PP |
| **算法切换** | Auto / Daniel / Sunny 三种难度估算模式 |
| **MOD 按钮** | 切换 SV1/SV2/NF/EZ/HO/IN，自动重算 |
| **自定义 OD** | 修改 OD 值后自动请求后端重算星数 |

## 算法参考

- [Sunny Rework](https://github.com/sunnyxxy/Star-Rating-Rebirth) — 核心星数算法
   - [@sunnyxxy](https://github.com/sunnyxxy)
- [Daniel](https://github.com/TheBagelOfMan/Daniel) — 4K RC 段位估算
   - [@TheBagelOfMan](https://github.com/TheBagelOfMan)
- [osumania_map_analyser](https://github.com/LeoBlackMT/osumania_map_analyser) — RC/LN 段位映射参考
   - [@LeoBlackMT](https://github.com/LeoBlackMT)和我自己

## License

MIT
