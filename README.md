# WallMock - 壁纸样机生成工具

一款 Windows 本地工具，自动将壁纸图片嵌入手机、平板、笔记本和显示器模型中，生成适合电商商品页面使用的展示图。

## 特性

- 🖼️ **6 套展示模板**：单手机、双手机、六手机套装、笔记本加手机、多设备组合、桌面展示
- 📱 **8 种设备类型**：灵动岛手机、宽刘海手机、水滴屏手机、居中打孔手机、无刘海手机、平板、笔记本、台式显示器
- 🎨 **实时预览**：调整参数即时看到效果
- 🔄 **自动比例识别**：支持 9:16、9:19.5、9:20、9:21、3:4、4:3、16:9、16:10 等常见比例
- ⏰ **锁屏覆盖层**：时间、日期、灵动岛、刘海、摄像头开孔
- 🏷️ **品牌文字**：自定义品牌名称、副标题、字号、颜色
- 📂 **批量处理**：自动扫描 input 目录，一键生成全部模板
- 👁️ **文件夹监听**：放入图片自动处理，无需手动操作
- 🔒 **完全离线**：不依赖网络，不上传图片，保护隐私

## 快速开始

### 环境要求

- Windows 系统
- Python 3.9 或更高版本

### 启动方式

1. 双击 `start.bat`
2. 等待服务启动，浏览器会自动打开
3. 拖拽壁纸图片到左侧上传区域
4. 选择模板，调整参数
5. 点击「生成图片」保存到 output 目录

## 目录结构

```
WallMock/
├── start.bat              # 启动脚本（双击启动）
├── app.py                 # Flask 应用入口
├── requirements.txt       # Python 依赖
├── README.md              # 说明文档
├── config/
│   └── settings.json      # 全局配置
├── input/                 # 输入目录（自动模式放这里）
├── output/                # 输出目录（生成的图片在这里）
├── assets/
│   ├── device_frames/     # 设备框素材（程序生成）
│   │   ├── devices.json   # 设备配置文件
│   │   └── *.png          # 设备框图片
│   └── icons/             # 图标资源
├── templates/             # 展示模板配置
│   ├── single_phone.json
│   ├── double_phone.json
│   ├── phone_pack_6.json
│   ├── laptop_phone.json
│   ├── all_devices.json
│   └── desktop.json
├── core/                  # 核心功能模块
│   ├── config.py          # 配置管理
│   ├── image_loader.py    # 图片加载
│   ├── ratio_detector.py  # 比例识别
│   ├── wallpaper_fitter.py # 壁纸适配
│   ├── device_renderer.py # 设备渲染
│   ├── device_frame_generator.py # 设备框生成
│   ├── template_engine.py # 模板引擎
│   ├── text_renderer.py   # 文字渲染
│   ├── batch_processor.py # 批量处理
│   └── folder_watcher.py  # 文件夹监听
├── web/                   # Web 界面
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── logs/                  # 日志目录
└── tests/                 # 测试脚本
```

## 使用说明

### 手动模式

1. **上传图片**：拖拽一张或多张壁纸到左侧上传区域，或点击上传区域选择文件
2. **选择模板**：在预览区顶部下拉菜单选择展示模板
3. **调整参数**：右侧面板切换「模板」「壁纸」「文字」「输出」标签页调整参数
4. **实时预览**：参数调整后自动刷新预览
5. **生成图片**：点击底部「生成图片」按钮，结果保存到 output 目录

### 自动模式（批量处理）

1. 将图片放入 `input/` 目录：
   - 单张图片直接放 input 根目录
   - 按商品分类：创建子文件夹，放入对应图片（如 `input/商品A/图片1.jpg`）
2. 点击「扫描 input 目录」查看待处理项目
3. 点击「批量生成」一次性处理全部

### 文件夹监听模式

1. 点击「启动监听」
2. 将新图片放入 `input/` 目录
3. 程序自动检测并处理新文件
4. 处理完成的文件不会重复处理

## 模板说明

| 模板 ID | 名称 | 说明 | 建议图片数量 |
|---------|------|------|-------------|
| `single_phone` | 单手机 | 一台手机居中 | 1 张 |
| `double_phone` | 双手机 | 两台手机并排 | 2 张 |
| `phone_pack_6` | 六手机套装 | 两行三列 | 6 张 |
| `laptop_phone` | 笔记本加手机 | 横图放电脑，竖图放手机 | 2 张（一横一竖最佳） |
| `all_devices` | 多设备组合 | 显示器、笔记本、平板、手机 | 4 张 |
| `desktop` | 桌面展示 | 单显示器 | 1 张横图 |

## 设备类型

第一版内置 8 种设备：

1. **灵动岛手机** (Dynamic Island Phone)
2. **宽刘海手机** (Notch Phone)
3. **水滴屏手机** (Waterdrop Phone)
4. **居中打孔手机** (Punch-hole Phone)
5. **无刘海手机** (No-notch Phone)
6. **平板** (Tablet)
7. **笔记本** (Laptop)
8. **台式显示器** (Desktop Monitor)

## 模板 JSON 字段说明

每个模板是一个独立 JSON 文件，位于 `templates/` 目录下。

```json
{
  "id": "模板ID",
  "name": "模板名称",
  "description": "描述",
  "canvas_width": 2000,       // 画布宽度（像素）
  "canvas_height": 2000,      // 画布高度（像素）
  "background_color": "#F5F2EB", // 默认背景色
  "devices": [                // 设备列表
    {
      "id": "phone1",         // 设备唯一ID
      "type": "dynamic_island_phone", // 设备类型
      "x": 0.5,               // 水平位置（0-1，相对画布宽度）
      "y": 0.46,              // 垂直位置（0-1，相对画布高度）
      "scale": 0.55,          // 设备缩放比例
      "rotation": 0,          // 旋转角度
      "z_index": 2,           // 层级（越大越上层）
      "image_slot": 0,        // 图片槽位编号
      "preferred_orientation": "portrait" // 推荐图片方向（可选）
    }
  ],
  "brand_text": {             // 品牌文字配置
    "enabled": true,
    "x": 0.5,
    "y": 0.85,
    "brand_size": 44,
    "subtitle_size": 20,
    "default_subtitle": "PHONE WALLPAPER",
    "align": "center"
  }
}
```

## 设备 JSON 字段说明

设备配置在 `assets/device_frames/devices.json`：

```json
{
  "device_id": {
    "name": "设备名称",
    "category": "phone|tablet|laptop|monitor",
    "frame_image": "设备框图片路径",
    "screen": {
      "x": 屏幕左边界,
      "y": 屏幕上边界,
      "width": 屏幕宽度,
      "height": 屏幕高度,
      "corner_radius": 屏幕圆角半径
    },
    "total_size": { "width": 总宽, "height": 总高 },
    "screen_ratio": 屏幕比例,
    "has_cutout": 是否有开孔,
    "cutout_type": "dynamic_island|notch|punch_hole",
    "cutout_config": { 开孔配置 }
  }
}
```

## 快捷键

- 拖拽图片到上传区域：上传
- 拖拽图片列表项：调整顺序
- 点击 × 按钮：移除单张图片

## 常见问题

### Q: 启动后浏览器没打开？
A: 手动访问 `http://127.0.0.1:5876`

### Q: 中文文件名乱码？
A: 已兼容中文路径和文件名，如遇问题请检查系统编码

### Q: 生成的图片在哪里？
A: 保存在项目目录下的 `output/` 文件夹中，可点击右上角「打开 output 目录」快速访问

### Q: 怎么添加新模板？
A: 在 `templates/` 目录中新建 JSON 文件，参考现有模板的格式。重启后自动加载。

### Q: 设备框可以替换吗？
A: 可以。替换 `assets/device_frames/` 中的 PNG 图片，并在 `devices.json` 中调整屏幕坐标。

## 技术栈

- **后端**：Python + Flask
- **图片处理**：Pillow
- **文件监听**：watchdog
- **前端**：原生 HTML / CSS / JavaScript

## 开发说明

### 重新生成设备框
```bash
python -m core.device_frame_generator
```

### 运行测试
```bash
python tests/test_templates.py
python tests/test_api.py
python tests/test_upload_preview.py
python tests/test_batch.py
```

### 直接启动服务
```bash
python app.py
```

## 许可证

本工具仅供内部使用。
