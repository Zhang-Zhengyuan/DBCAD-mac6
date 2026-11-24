# AI-CAD 验收测试的 P0 与 P0.5 复算

阅读 [P0 选题与反例](P0-选题与反例.md) 或 [五页 PDF](../pdf/P0-AI-CAD验收测试选题与反例.pdf)。目录中有两组原生 CAD 对照和一次公开人评复算。

| 可核验的结论 | 记录 |
| --- | --- |
| CADWorld 003 中，5 mm 和 8 mm 两份重存的装配均得 1 分，初始件得 0 分。 | [原版判卷结果和文件散列](assembly_results.json) · [FreeCAD 独立量面](freecad_measurements.json) · [原生模型](models/) |
| 同形的 40 mm 开孔板变为 60 mm，一件仍居中，另一件偏心 10 mm。 | [重建后的读数](freecad_measurements.json) · [变长实验](freecad_evidence.py) |
| 770 份完整五人评分中，两种聚合只产生一项分歧。 | [分组计数及唯一分歧的匿名分数对](ratings_results.json) · [复算代码](audit_ratings.py) |

以下命令均从本目录运行，示例输出写入临时文件。

## 原版装配判分

Python 3.10 或更新版本即可。脚本下载并校验固定提交的四个原版 Python 模块。已克隆 CADWorld 时，加上选项 `--cadworld-source /path/to/CADWORLD` 即可离线运行。

```sh
python3 audit_assembly.py --out /tmp/dbcad-assembly.json
diff assembly_results.json /tmp/dbcad-assembly.json
```

初始件、参考解和题目复用仓库里已归档的 [CADWorld 样本](../observation-study/cadworld_seed/)。两个重存件都来自同一参考解。程序仅读取本地文件代替虚拟机传输，随即调用原版 `get_freecad_model_info`、`check_freecad_assemble_model` 及其明细函数。它使用题目 `evaluator.expected.rules` 中实际启用的规则。原计划另列有间距及自由度。[固定题目](https://github.com/Zdong104/CADWORLD/blob/5e9529ff984b5426a5c194b94a09dc84cbe7fa7a/evaluation_examples/examples/assemble/freecad-assemble-003.json) · [原版文件读取](https://github.com/Zdong104/CADWORLD/blob/5e9529ff984b5426a5c194b94a09dc84cbe7fa7a/desktop_env/evaluators/getters/freecad.py) · [数据集修订与许可](https://huggingface.co/datasets/Zihan1004/CADWORLD/tree/fa02aa03b944daf2ae5b23e56d135bb7cbb75994)

## 独立重开、求解与量面

本轮使用 FreeCAD 1.1.3 的原生 Python、Assembly 和 Part 模块。以下为 macOS 官方发行包的路径。其他系统可使用能导入同版本 FreeCAD、AssemblyApp、JointObject、Part 的 Python。建模、求解和测量均可无窗口运行。

```sh
FC_RES="/Applications/FreeCAD.app/Contents/Resources"
export PYTHONPATH="$FC_RES/lib:$FC_RES/Mod/Assembly"
export QT_QPA_PLATFORM=offscreen
"$FC_RES/bin/python" freecad_evidence.py models --out /tmp/dbcad-geometry.json
diff freecad_measurements.json /tmp/dbcad-geometry.json
```

若要从头建出四个文件，使用一个新目录。先求解装配，再保存、重开。量指定的两个 B-Rep 面，同时核对两个实体的最近距离。孔板在同一次重开后分别重建到 40 和 60 mm，量圆柱孔的中心，并算两种板体积的对称差。比较 5 mm 时采用 0.000001 mm 数值容差。此数值仅用于此次正常形与明显错形的判别。

```sh
MODEL_TMP=$(mktemp -d)
"$FC_RES/bin/python" freecad_evidence.py "$MODEL_TMP" --generate --out /tmp/dbcad-regenerated.json
diff freecad_measurements.json /tmp/dbcad-regenerated.json
python3 audit_assembly.py --models "$MODEL_TMP" --out /tmp/dbcad-regenerated-scores.json
```

重新保存会生成新的 FreeCAD 文档时间等元数据，重新生成的文件用几何读数和判分对照。已交付的原文件可按 JSON 内的 SHA-256 校验。报告配图使用两份结果中的面距及得分，横向按毫米画出两个方块在 X 轴的投影。需要重画时用独立 Python 环境运行 `python -m pip install matplotlib` 和 `python plot_gap.py`。[FreeCAD 1.1.3](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.3)

## 专家评分复算

在常规 Python 3.10 或更新版本的独立环境中安装 PyMongo 以读取 BSON。默认从固定版本 ZIP 定位八个数据库成员，合计约 1.65 MB 压缩数据，并验证解压后的 SHA-256。也可在命令行位置参数给出完整的本地 `edit_192_external.zip`。只读取在 Mongita 活动索引中的记录。

```sh
python3 -m venv /tmp/dbcad-ratings-env
/tmp/dbcad-ratings-env/bin/python -m pip install pymongo==4.20.1
/tmp/dbcad-ratings-env/bin/python audit_ratings.py --out /tmp/dbcad-ratings.json
diff ratings_results.json /tmp/dbcad-ratings.json
```

沿用作者排行榜对测试账号的排除、1 至 7 量表和缺分默认值。先复算全部 960 件的原规则，再在恰有五位不同专家且两维完整的作品上比较两种规则。所发布的分歧按编辑标识的散列定位，只列匿名数字对和作答来源。复算的结论描述评分规则的敏感性；对某件作品的真实工程签收是另一个待观测事件。[作者排行榜](https://github.com/AutodeskAILab/neuralCAD-Edit/blob/68d1acceda0743e364f45fb7823f7cf39c530ba5/src/notebooks/leaderboard.ipynb) · [Autodesk 数据与 CC BY-NC 4.0 许可](https://huggingface.co/datasets/autodesk/neuralCAD-Edit/tree/b29220c3ccceecd9188ab42f1688e4e6bf5d7a7d)

装配候选由 CADWorld 的 Apache-2.0 参考解派生，改动包括设置 5 或 8 mm 关节、重新求解和保存。[随原样本保留的许可](../observation-study/cadworld_seed/LICENSE)
