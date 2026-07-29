# mania-sunny-rework-web

一个用于 osu!mania 谱面难度与 PP 估算的 Chrome 扩展（同时兼容 Edge 等 Chromium 内核浏览器）。扩展基于 [Sunny Rework](https://github.com/sunnyxxy/Star-Rating-Rebirth) 算法，在 osu! 官网谱面页直接展示 Sunny Rework 星数、RC/LN 段位、实时 PP 计算以及 [6K 定数/Rating](https://github.com/IceRain5491/ManiaMapWorkshop)估算。

> [English Version](./README_EN.md)

---

## 功能

- **Sunny Rework 星数** — 4K/6K/7K/10K 的 Sunny Rework 难度星数估算
- **Daniel 算法** — 4K RC 的 Daniel 段位估算 (Alpha ~ Theta)
- **6K Rating 模式** — 显示 6K 定数与基于 Acc 的 Rating
- **7K Wild 模式** — 7K 支持 Auto / Wild 两种段位算法切换
- **RC / LN 段位** — 根据 LN 占比自动显示 RC 段位或 RC+LN 混合段位
- **PP 估算** — NM/DT/HT 三列实时 PP 计算，支持自定义倍速 (0.5x ~ 2.0x)
- **MOD 支持** — SV1/SV2/NF/EZ/HO/IN 等 mod 组合
- **自定义 OD** — 独立调节 OD 值，自动重新计算星数
- **判定输入** — 手动输入判定数以计算实际 Acc 对应的 PP
- **HO/IN 转换** — 一键切换 HO (纯米) 和 IN (反键) 模式，分别计算对应的星数和 PP

---

## 安装（其他浏览器可自行搜索添加自定义扩展教程）

1. 下载本仓库 ZIP 或 `git clone`
2. 打开 Chrome，进入 `chrome://extensions/`
3. 开启「开发者模式」
4. 点击「加载已解压的扩展程序」，选择仓库目录
5. 打开任意 osu! 谱面页面 (如 `https://osu.ppy.sh/beatmapsets/xxx#mania/xxx`)
6. 右下角有常驻难度分析 badge
7. 点击扩展图标即可查看详细难度分析面板

[视频教程](https://www.bilibili.com/video/BV1RPgd6VEUB)

> ⚠️ **更新插件时请务必先「移除」再重新「加载已解压的扩展程序」，直接点击刷新按钮可能导致旧代码残留，插件功能异常（插件作者因此耗费了不少时间排查）。**

---

## 使用

| 功能 | 说明 |
|------|------|
| **DT / NM / HT** | 三列分别显示 1.5x / 1.0x / 0.75x 的星数和 PP |
| **倍速滑块** | 支持 0.5x ~ 2.0x 自定义倍速，预设快捷键快速切换 |
| **判定输入** | 输入 320/300/200/100/50/miss 数量计算实时 PP |
| **算法切换** | 4K: Auto / Daniel / Sunny；6K: Rating / Sunny；7K: Auto / Wild |
| **MOD 按钮** | 切换 SV1/SV2/NF/EZ/HO/IN，自动重算 |
| **自定义 OD** | 修改 OD 值后自动请求后端重算星数 |

---

## 扩展是如何运行的

### 整体架构

扩展由两部分组成：

1. **Content Script（内容脚本）**：注入到 osu! 官网谱面页，负责抓取谱面 ID、下载 `.osu` 文件、运行完整难度算法、在页面右下角绘制常驻 badge，并把结果写入 `chrome.storage.local`。
2. **Popup（弹出面板）**：点击扩展图标后打开，从 `chrome.storage.local` 读取数据，展示 NM/DT/HT 三列详情、判定输入、PP、段位/定数以及 mod 选项。

### 数据流

```
用户打开 osu! 谱面页
    ↓
Content Script 提取 beatmapId
    ↓
请求 https://osu.ppy.sh/osu/{beatmapId} 下载原始 .osu 文件
    ↓
OsuParser 解析谱面（判定、键位、时间、LN、OD/HP 等）
    ↓
Star-Rating-Rebirth 算法计算 NM / DT / HT 星数
    ↓
根据 LN 占比、键位、算法模式计算 RC/LN 段位（或 6K 定数）
    ↓
结果存入 chrome.storage.local
    ↓
Popup 读取并渲染 NM/DT/HT 三列 + PP + 段位/定数
```

### 星数计算

核心算法使用 Sunny Rework（Star-Rating-Rebirth）。Content Script 对每张谱面跑三次完整计算：

- **NM**：原速 `1.0x`
- **DT**：1.5x 速，算法内将音符时间戳乘以 `2/3`
- **HT**：0.75x 速，算法内将音符时间戳乘以 `4/3`

HO / IN 模式会先在原始 `.osu` 文本上做变换，再跑 NM 算法，DT/HT 值通过 NM 的倍率推导：

- **HO（Hold Off）**：把所有 LN 转为普通音符，模拟纯米谱面。
- **IN（Invert）**：把每个音符到下一音符的间隙转成 LN，与 osu! 官方 Invert mod 算法一致（时长取 `max(gap/2, gap - beatLength/4)`）。

### 段位/定数计算

*注意，同时显示 RC 段位和 LN 段位时，RC段位使用的是开启 HO mod 后的 Sunny Rework 段位表难度，或者（仅4k） Daniel 算法估算的难度。*

#### 4K

- **Auto**：当 Daniel 4K 难度 ≥ 6.365 时使用 Daniel 算法，否则使用 Sunny Rework。
- **Daniel**：强制使用 Daniel 算法估算 Alpha ~ Theta 段位（该算法将面视为米处理）。
- **Sunny**：强制使用 Sunny Rework 的 RC4K_Reform 段位表，支持 Intro 1 到 Theta。

若 LN 占比 ≥ 15%，会同时显示 RC 段位和 LN 段位，格式如 `rf8/8⁻ | LN 11⁻`。

#### 6K

- **Rating**：显示 **定数**（Difficulty Constant），公式为 `定数 = SR × 200/81 + 7/6`；并基于 310 权重 Acc （仅在算法内使用，不显示）计算 **Rating**。
- **Sunny**：显示 RC6K 段位表（Arkman's Regular Dan）。

Badge 右下角常驻面板对 6K 谱面默认显示定数。

#### 7K

- **Auto**：使用 Regular 7K 段位表。
- **Wild**：使用 Wild 7K 段位表，仅支持 10 Dan（Jinjin's Dan）以上的米图。

#### 10K

直接显示 RC10K 段位表，无额外模式切换。

### PP 计算

每列同时展示两种 PP：

1. **Sunny PP**：基于 Sunny Rework SR 与 `computeSunnyPP` 公式，支持根据 miss/判定实时调整 Acc。
2. **Lazer PP**：基于 osu!lazer 官方 SR 与 `computeOfficialPP` 公式。

两者之差展示在 badge 的 `+/-Xpp` 中。

### 判定与 Acc

- 输入框支持 320 / 300 / 200 / 100 / 50 / miss。
- 显示的 Acc 遵循 SV1（320 彩判权重）或 SV2（305 彩判权重）设置。
- 6K Rating 模式内部计算 Rating 时固定使用 **310 权重 Acc** ，不影响显示 Acc。

### 自定义 OD

修改 OD 后，Popup 会向 Content Script 发送 `recalculateOd` 消息，后端用新 OD 重新跑 NM/DT/HT 算法并更新 storage，无需刷新页面。

---

## 算法与项目参考

- [Sunny Rework](https://github.com/sunnyxxy/Star-Rating-Rebirth) — 核心星数算法
   - [@sunnyxxy](https://github.com/sunnyxxy)
- [Daniel](https://github.com/TheBagelOfMan/Daniel) — 4K RC 段位估算
   - [@TheBagelOfMan](https://github.com/TheBagelOfMan)
- [osumania_map_analyser](https://github.com/LeoBlackMT/osumania_map_analyser) — RC/LN 段位映射参考
   - [@LeoBlackMT](https://github.com/LeoBlackMT) 和我自己
- [ManiaMapWorkshop](https://github.com/IceRain5491/ManiaMapWorkshop) — 6K Rating及定数算法
   - [@IceRain5491](https://github.com/IceRain5491)

## License

MIT
