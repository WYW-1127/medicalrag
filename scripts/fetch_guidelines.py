import warnings

warnings.filterwarnings("ignore")  # verify=False 的证书告警

"""权威网页指南 → markdown 语料（data/raw/markdown/<科室>/）。

用法：cd backend && uv run python ../scripts/fetch_guidelines.py
URL 清单在脚本内维护（注释标注来源），抓取失败会显式列出，可重跑。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx  # noqa: E402
import trafilatura  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"

# (输出文件名, 科室, URL, 标题)
TARGETS = [
    (
        "中国心力衰竭诊断和治疗指南2024_上",
        "心血管",
        "https://csc.cma.org.cn/art/2024/4/18/art_619_56220.html",
        "中国心力衰竭诊断和治疗指南2024（上）",
    ),
    (
        "心房颤动诊断和治疗中国指南2023",
        "心血管",
        "https://www.icuguideline.com/%E5%BF%83%E6%88%BF%E9%A2%A4%E5%8A%A8%E8%AF%8A%E6%96%AD%E5%92%8C%E6%B2%BB%E7%96%97%E4%B8%AD%E5%9B%BD%E6%8C%87%E5%8D%97-2023/",
        "心房颤动诊断和治疗中国指南2023",
    ),
    (
        "稳定性冠心病基层诊疗指南2020",
        "心血管",
        "https://cmab.yiigle.com/uploads/guide_html/%25E7%25A8%25B3%25E5%25AE%259A%25E6%2580%25A7%25E5%2586%25A0%25E5%25BF%2583%25E7%2597%2585%25E5%259F%25BA%25E5%25B1%2582%25E8%25AF%258A%25E7%2596%2597%25E6%258C%2587%25E5%258D%2597%25%25EF%25%25BC%25882020%25E5%25B9%25B4%25%25EF%25%25BC%2589.html",
        "稳定性冠心病基层诊疗指南（2020年）",
    ),
]

RAW_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "markdown"


def main() -> int:
    failed: list[str] = []
    for name, dept, url, title in TARGETS:
        out_dir = RAW_ROOT / dept
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{name}.md"
        try:
            resp = httpx.get(url, headers={"User-Agent": UA}, timeout=60, follow_redirects=True,
                             verify=False, trust_env=True)
            resp.raise_for_status()
            md = trafilatura.extract(
                resp.text, output_format="markdown", include_tables=True, no_fallback=False
            )
            if not md or len(md) < 2000:
                raise ValueError(f"正文抽取过短（{len(md or '')} 字符），疑似反爬或结构异常")
            out.write_text(f"# {title}\n\n{md}\n", encoding="utf-8")
            print(f"[ok]   {out.relative_to(RAW_ROOT.parents[1])} ({len(md)} 字符)")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"[fail] {name}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
