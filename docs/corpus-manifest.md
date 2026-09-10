# 真实语料清单（2026-09-10 收集）

> 语料存放于 `data/raw/`（gitignore，仅本地学习用途，不分发）。本清单记录来源与获取方式，便于重建。

## 指南 PDF（6 份，约 240 页）

| 科室 | 文件 | 来源 | 获取方式 |
|------|------|------|----------|
| 心血管 | `pdf/心血管/中国高血压防治指南2024修订版.pdf`（98 页） | 上海市疾控中心转载官方指南 | [scdc.sh.cn 附件直链](https://www.scdc.sh.cn/shjk/gxy-gfzn/20241011/9843.html) |
| 内分泌 | `pdf/内分泌/中国2型糖尿病防治指南2017.pdf`（64 页） | 中华糖尿病杂志官网下载通道 | [down.jctnb.org.cn 直链](https://down.jctnb.org.cn/uploads/download_content/2019/07/15d22d3faae23a.pdf) |
| 呼吸 | `pdf/呼吸/支气管哮喘防治指南2024.pdf`（41 页） | 湖南药事服务网转载《中华结核和呼吸杂志》 | [hnysfww.com 文章页附件](https://www.hnysfww.com/mobile/article.php?id=4172) |
| 消化 | `pdf/消化/中国幽门螺杆菌感染治疗指南2022.pdf`（12 页） | headwaychina 公开 PDF | [直链](https://www.headwaychina.com/hdw/cyyfw/wx37/1335422/2023060809574268318.pdf) |
| 神经 | `pdf/神经/中国急性缺血性脑卒中诊治指南2018.pdf`（12 页） | 中华医学会神经病学分会（e-cspc 转载） | [直链](https://www.e-cspc.com/oldfile/content/20190513/a8cfad64ffbc1901ef608ee2b03e0e65.pdf) |
| 肿瘤 | `pdf/肿瘤/胰腺癌诊疗指南2022年版.pdf`（15 页，节选） | 《临床肝胆病杂志》开放获取 | [lcgdbzz.org 附件](https://www.lcgdbzz.com/cn/article/doi/10.3969/j.issn.1001-5256.2022.05.007) |

## 结构化数据

| 文件 | 来源 | 说明 |
|------|------|------|
| `structured/icd10_disease.csv`（1586 条） | [chaseliu/ICD-10-CN](https://github.com/chaseliu/ICD-10-CN) | ICD-10 中文编码表；原为 TSV 已转标准 CSV |

## 入库统计（2026-09-10）

- 7 份文档 → 1562 chunks（structural 策略，无错误）
- 科室元数据：心血管 614 / 内分泌 438 / 呼吸 268 / 消化 78 / 神经 67 / 肿瘤 9 / 综合（ICD）88

## 已知问题与扩容指引

- **卫健委官网（nhc.gov.cn）屏蔽程序化下载**（TLS 层拒绝）：其指南可经浏览器手动下载后放入对应科室目录，官方指南索引见[医政医管栏目](https://www.nhc.gov.cn/yzygj/)（含肿瘤/血液病 12 种诊疗指南 2022 版、脑血管病防治指南 2024 等）
- **GitHub 直连不稳**：用 jsDelivr CDN 前缀替代（`https://cdn.jsdelivr.net/gh/<user>/<repo>@<branch>/<path>`）
- 胰腺癌指南为期刊节选（文字层薄），扩容时建议补充完整版
- 扩容目标（P7 评估前）：每科室 3-5 份、总量 20+ 份 PDF；优先补：肾病（CKD）、肝病（乙肝/丙肝防治指南）、精神科（抑郁防治指南）、儿科
- 下载校验命令：`make ingest` 前先 `cd backend && uv run python -c "import fitz,pathlib; [print(p.name, fitz.open(p).page_count) for p in pathlib.Path('../data/raw/pdf').rglob('*.pdf')]"` 确认 PDF 有效
