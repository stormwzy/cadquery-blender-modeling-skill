# CAD、SolidWorks 与 Blender 互通

## 格式与源文件

CadQuery 的 Python 代码与参数是可重建源文件。STEP 交换精确实体与装配；STL 是切片网格，通常不记录单位。Blender 场景用于检查外观、方向与装配展示，不作为未经验证的尺寸真值。

STEP 导入 SolidWorks 后通常是导入实体，不携带原建模脚本的完整特征历史。需要 SLDPRT/SLDASM 或原生草图、拉伸、孔、装配约束时，应使用可用的 SolidWorks UI/API，并实际保存、重开和检查；FeatureWorks 的识别能力也不能预先保证能重建所有特征。不要仅改后缀或把“可导入”写成“原生可编辑特征树”。

官方说明：[CadQuery 格式与参数化信息](https://cadquery.readthedocs.io/en/latest/importexport.html)、[SolidWorks STEP 支持](https://help.solidworks.com/2025/english/SolidWorks/sldworks/c_Step_Files.htm)、[FeatureWorks 特征识别](https://help.solidworks.com/2025/english/SolidWorks/fworks/t_Recognizing_Features_Using_step_by_step.htm)。软件接口会变化，以当前安装版本为准。

## 单位与姿态

CAD 源数据统一按毫米建模。导出后核对 STEP 单位和实际尺寸，切片 STL 按毫米、100% 导入。保留每个零件的打印姿态，并用另外的网格或显式刚体变换表示装配姿态。

Blender 用米作为内部坐标时，将毫米网格坐标乘 `0.001` 一次；`scene.unit_settings.length_unit = 'MILLIMETERS'` 只控制显示，不能替代坐标转换。不要同时启用导入缩放、场景单位换算和对象缩放三次转换。导入后用包围盒对照至少一项已知尺寸。

当前脚本使用 `bpy.ops.wm.stl_import`；较旧 Blender 可能需要旧版 STL 插件及不同操作名称。检查安装版本，缺失时明确报错或按官方 API 调整，不悄悄忽略模型。官方接口：[Blender STL 导入](https://docs.blender.org/api/current/bpy.ops.wm.html)。

参考零件、安装板与五金用独立角色标记。它们可参与干涉检查，但不应进入正式打印网格。渲染从导出模型导入，避免为了效果另建一个几何不一致的替身。
