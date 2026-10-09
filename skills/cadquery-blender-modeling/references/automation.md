# 可执行辅助脚本

在实际环境检查 `python`、CadQuery、Trimesh 和 Blender；不要把版本号写成统一安装保证。Python 依赖可在独立环境安装 `cadquery trimesh numpy`，Blender 使用自己的 Python。所有路径由参数传入，不依赖原项目目录。

## 通用试块示例

以下命令从技能目录运行；`blender` 换成实际可执行程序路径。Windows PowerShell 执行带空格的可执行路径时用 `& '完整路径'`。

```text
python scripts/build_fit_coupon.py --out work/coupon
python scripts/audit_models.py work/coupon/model_manifest.json --report work/coupon/audit.json
blender --background --factory-startup --threads 4 --python scripts/render_models.py -- work/coupon/scene.json --out work/coupon --resolution 1000 --samples 24
python scripts/package_delivery.py work/coupon/model_manifest.json --output work/coupon.zip
```

示例生成 26×30×20mm 的工艺试块，圆形净空 4.4mm，承压孔长 10mm，孔顶有 45°尖顶；螺母槽朝打印 +Z 开放。默认示例会检查名义螺母包络、垂直送入包络和承压材料。使用 `--parameters 参数.json` 覆盖脚本中明确定义的尺寸；未知键或破坏材料/净空约束的参数会报错。

交付清单默认包含模型、参数、说明和审核报告；若需要打包 `.blend` 与预览，将已生成文件的相对路径加入 `delivery_files`。未生成文件会使打包失败，不会悄悄省略。

## 模型检查清单

模型文件路径相对清单所在目录，不能越出该目录。最小示例：

```json
{
  "units": "mm",
  "dimension_tolerance_mm": 0.1,
  "relative_volume_tolerance": 0.01,
  "parts": [{
    "id": "bracket",
    "step": "bracket.step",
    "stl": "bracket.stl",
    "quantity": 2,
    "expected_solids": 1,
    "expected_mesh_components": 1,
    "print_on_bed": true,
    "expected_dimensions_mm": [26, 30, 20],
    "bores": [{
      "origin_mm": [0, 0, 10],
      "axis": [0, 1, 0],
      "diameter_mm": 4.4,
      "axial_span_mm": [0, 10]
    }]
  }],
  "delivery_files": ["bracket.step", "bracket.stl"]
}
```

`origin_mm` 定义孔轴上的基准，`axis` 是非零方向向量，`axial_span_mm` 是相对该基准沿轴的起止距离。检查导出的圆柱面半径、轴线和端点投影，并检查内接圆柱是否被材料占据，防止把外部凸柱误报成孔。孔的端点对应本段圆柱面，而不是整个不规则空腔的深度。分段孔、沉孔及圆角可能需要多个检查或模型专用测量；脚本不自动推断任意孔型。

公差由实际导出精度和任务要求确定。STEP 与 STL 的包围盒/体积一致是必要核对，但不是全部几何等价证明。预期尺寸应来自需求或图纸，不应只从导出文件自身反算作为期望。

`expected_mesh_components` 数的是网格表面连通分量，完全封闭的内部空腔可能产生额外的独立表面；它不总等于 CAD 实体数，需要根据零件结构显式设置。

审核失败返回非零状态并写入失败报告；不能只看“报告文件存在”。脚本不会自行修补开口网格，修改应回到参数化源模型。

## 场景清单

```json
{
  "units": "mm",
  "instances": [{
    "file": "bracket_assembled.stl",
    "name": "left bracket",
    "role": "PRINT",
    "translation_mm": [-55, 0, 0],
    "rotation_deg": [0, 0, 0],
    "color": [0.12, 0.19, 0.25]
  }]
}
```

姿态采用 Blender XYZ 欧拉角，先旋转再平移；尽量直接使用已变换到装配坐标的网格，以减少坐标约定误差。模型只缩放毫米到米一次。参考件可用 `role: "REFERENCE"` 导入，但应在场景中和交付说明标清用途。渲染脚本需要独立的后台 Blender 进程，避免清除用户正在编辑的场景。

自动生成 `assembly_preview.blend`、`preview_front.png`、`preview_back.png`、`preview_side.png` 和记录实际导入尺寸的 `render_checks.json`。输出脚本没有进行切片或物理测试。

## 打包

`package_delivery.py` 只打包 `delivery_files` 中的实际文件，用规范的相对路径存储，包内附 `SHA256SUMS.json` 并重读核对。它不会自动收集整个工程目录；把参数化源代码、说明与所需报告明确加入清单。技能发布仓库与模型交付包是两种产物，不要把用户项目全量复制到公开技能仓库。
