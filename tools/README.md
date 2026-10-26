# tools — CAD 装配体 → 网页拆解台 的管线

全部是 Python 3 标准库（`04_emit_data.py` 用到 `zlib`，打包用 `struct`），**不需要 CAD 内核、不需要 numpy**（只有 `03_pack_3mf.py` 用了 numpy，见下）。脚本之间用中间文件（JSON / bin）串联，可以单独重跑任意一步。

```
python3 01_step_split.py        # 需要改脚本顶部的 SRC 路径
python3 02_step_leaf_sizes.py
python3 03_pack_3mf.py
python3 04_emit_data.py
python3 05_fix_names.py
python3 06_explode_layout.py    # 直接改页面里的 ROBOT_META
python3 07_patch_labels.py
python3 08_patch_floor.py
```

## 01_step_split.py — 从 STEP 取装配树、中文零件名、变换

自己写的 STEP 解析器，不依赖任何 CAD 库。要点：

- STEP 里装配关系是 `NEXT_ASSEMBLY_USAGE_OCCURRENCE` → `PRODUCT_DEFINITION_SHAPE` → `SHAPE_REPRESENTATION`，其中 **pd → PDS → SDR 是反向引用**，要先把所有实体建索引再反查
- 变换藏在**复数实体实例**里的 `REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(#idt)`，顺着 `ITEM_DEFINED_TRANSFORMATION` → `AXIS2_PLACEMENT_3D` 取出 4×4
- 零件级的 `SHAPE_REPRESENTATION_RELATIONSHIP` 是**简单实体**，装配级的是**复数实例**，两者写法不同
- 中文名是 `\X2\...\X0\` 包起来的 **UTF-16BE**，要 hex 解码
- 实体定义有**跨行**写法，解析时不能按行切

输出：`leaves2/pd_*.step`（每个叶子零件一个文件）、`leaves2/index.json`、`instances.json`（55 个顶层实例的名字 + 变换 + 含哪些叶子）。

## 02_step_leaf_sizes.py — 用尺寸（而不是位置）反查零件名

对每个叶子零件，在它自己的实体闭包里收集所有 `CARTESIAN_POINT` 求包围盒。这个尺寸与摆放姿态无关，因此可以和 3MF 里解出来的「局部包围盒」按尺寸配对，补上仅靠位置配不上的那批名字。

## 03_pack_3mf.py — 从 3MF 取几何并量化打包

- `zipfile` 读 `3D/3dmodel.model`，正则取 `<vertex>` / `<triangle>` / `<component>`
- 根对象正好挂着 55 个子件；每个子件**去掉自身摆放**后剩下的局部几何就是它的网格
- 局部几何相同的零件（14 个同型舵机、成对的连板、滚子、垫圈……）**共享同一份网格**：55 个实例 → 只有 33 种几何，体积省约 60%
- 量化：顶点坐标按局部包围盒归一化到 **u16**，索引 u16/u32；再用 `zlib` 压一遍（页面里内联 pako 解压）
- 同时按变换把每个实例的**世界包围盒**算出来

**矩阵约定（踩过坑，务必保留原样）**：3MF 的 `transform` 是 12 个数、行向量约定；把它按原顺序写进 16 元素数组（第 4/8/12 位补 0、最后补 1）恰好就是 three.js `Matrix4.fromArray()` 要的**列主序**布局，**不要转置、不要重排**。居中时只改 `[12..14]` 三个平移分量。

输出：`geoms.bin`、`parts.json`。

## 04_emit_data.py — 生成页面数据

把装配体按世界包围盒居中，然后算每个零件的爆炸向量 `ex`（单位方向）与 `exd`（行程），最后写出 `45_data.js`（`window.AP2.DIMS` / `window.ROBOT_META` / `window.ROBOT_BIN_Z`）。这里的 `ex/exd` 会被 `06_explode_layout.py` 覆盖成最终排布。

## 05_fix_names.py — 名称补全

镜像件、头部/脚部、同几何件、描述性占位名的传播规则，把 55 个名字尽量补全（本机型最终 48/55）。

## 06_explode_layout.py — 爆炸排布（核心）

读页面里的 `ROBOT_META`，重算 `ex/exd`，再写回去。算法：

- 方向 = `normalize(整机中心 → 零件中心)`，垂直分量压 0.66；下半身射线再往两侧摊（`LEG_SPREAD` / `LEG_FLAT`）
- 距离 = `12 + 0.58 · r`，上限 170
- 同射线且相邻的零件聚类后，做**保序一维堆叠**：`rel[i] = max(rel[j] + 间距 − 现有间隔)`，只补差
- 去穿插松弛：重叠时推「簇内序号更大 / 半径更大」的那件，**只能向外推**
- `PINNED = {31}` 外壳2 钉住；`FORCE_DIR` 指定电池 / K230D / 前盖板 朝 −Z

最后打印行程统计与互穿对数（应为 0）。

## 07_patch_labels.py — 标签规则

标签默认只显示「选中 / 悬停 / 正在拖拽」的那几个（保证不会重叠），`L` 切换成全部显示，并且全部显示时按**零件索引**而不是屏幕 y 排序（按 y 排会因帧间顺序交换而看起来在闪）。

## 08_patch_floor.py — 地板跟随

拆解时下半身的零件会往外下方摊开，地板（全息网格 + 阴影面）跟着**最低零件**下移，保证没有零件沉到网格下面；装配态则停在原位。

## check_overlap.py — 互穿自检

打印每个射线分组的射程、拆解后的整体包围盒与中心偏移，以及**所有仍然互穿的零件对**（含重叠体积与名字）。改完排布先跑这个。

## preview_explode_views.py — 排布四视图

用 matplotlib 把每个零件的包围盒画成线框：装配态灰色虚线、拆解态彩色，出**立体 / 前视 / 侧视 / 俯视**四张，肉眼查对称、顺序和疏密。没有 GPU 也能看排布对不对。

## preview_ui_layout.py — 界面布局自检

页面要 WebGL，预览面板渲染不了；但**布局可以截**。这个脚本把页面的 `<style>` 和 body 摘出来做成「无脚本孪生页」，另存一份宽屏版（剥掉所有 `@media` + 用 `transform: scale()` 把 1400×900 塞进小视口，顺带让 `position:fixed` 相对这个框定位），于是纯 CSS 的界面能被截图检查。