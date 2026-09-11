# ADR-0001: 向量存储选型 Milvus（单库混合检索）

- 状态：已采纳（2026-09-10）
- 背景：中文医学 RAG 需要稠密语义检索 + 稀疏关键词检索（药物名/指标精确匹配），开发机内存 <16GB
- 备选方案：
  1. **Qdrant + Elasticsearch 双库**：每路一个专用引擎，自己写融合。语义最清晰但双引擎运维重（ES 单独 ~1-2GB）、管线要维护两套写入
  2. **Milvus 2.5 单库**：dense + BM25 sparse（内置 jieba analyzer，写入时函数自动生成稀疏向量）+ hybrid search 一体
  3. **pgvector + 倒排**：最轻但中文 BM25 能力弱、生产化故事单薄
- 决策：选 2。理由：内存预算下双库过重；Milvus 的 collection 三路字段（dense/sparse/标量元数据）一次写入满足全部检索需求，且科室过滤（标量）与向量检索同引擎完成
- 代价与已知问题：融合未用内置 RRFRanker，改为两路独立 search + 自实现 RRF（见 ADR-0002）；Milvus stats 接口有最终一致延迟，精确计数用 `query count(*)`
- 修正记录：初版部署用 daocloud 镜像源（Docker Hub 直连超时）；宿主端口 3307/6380 避开本机已有服务

# ADR-0002: 两阶段检索与手写融合，而非调用内置 hybrid_search

- 状态：已采纳
- 背景：Milvus 提供 hybrid_search + RRFRanker 一步到位，我们却拆成两路独立检索 + 自写 RRF/加权融合
- 决策理由：
  1. **消融实验需要**：P7 评估要对比 rrf vs weighted vs dense-only，内置 ranker 无法逐路控制权重
  2. **面试可讲性**：融合公式 `Σ 1/(k+rank+1)` 是自己实现的（含手算已知值单测），而非黑盒参数
  3. 调试器价值：`make retrieve` 能展示 dense/sparse/fused/rerank 四级分数的排序变化
- 实测数据（P7）：rerank 才是本场景最大收益项（Recall@5 0.550→0.631）；RRF 提升 MRR 但对口语化改写查询召回略降——收益依赖查询分布
- 重排器：BGE-reranker-v2-m3（SiliconFlow API），送评文本截断 1000 字符对齐模型上限

# ADR-0003: Agentic 编排用 LangGraph，但模型调用与检索逻辑自研

- 状态：已采纳
- 背景：编排层选型在「全自研状态机 / LangChain 全家桶 / LangGraph」之间
- 决策：只用 LangGraph 的 StateGraph 做图编排（条件路由、节点循环），LLM/Embedding/Reranker 调用走自研 ModelProvider（openai SDK 直连 + 超时重试），检索融合自研
- 理由：
  1. LangGraph 提供反思循环（grade 失败→rewrite 重试）的声明式表达，比手写状态机少 300+ 行且 checkpoint 生态可用（P5 会话）
  2. 不整体依赖 LangChain：面试被追问任何节点机制都能答（每节点独立 Pydantic schema，五条路径有集成测试）
  3. 简历关键词与代码掌控力兼得
- 代价：langgraph 的 add_node 类型协议与 mypy strict 不兼容（注册处统一 Any）；ainvoke 返回类型随版本变化（dict/state 双兼容）
- 流式方案：token 级流式用 `token_sink: ContextVar` 注入 generate 节点（同 task 内 contextvar 可达），不需要把回调穿透节点签名

# ADR-0004: 自建轻量 trace，不引入 LangFuse

- 状态：已采纳
- 背景：RAG 可观测常见选型 LangFuse（全链路 UI），但其完整栈（server/worker/clickhouse）内存 4GB+
- 决策：loguru 结构化日志 + X-Trace-Id 中间件贯穿请求 + 每节点 StepEvent（名称/耗时/详情）写入 AgentState.steps，经 SSE step 事件直达前端检索时间线
- 理由：开发机 <16GB 内存预算下，基础设施已占 ~2.7GB；StepEvent 本身就是产品功能（前端可视化是演示核心），一份数据两用
- 代价：无历史查询聚合分析；预留 OpenTelemetry 接口作为演进方向

# ADR-0005: 评估方法——知识库反向生成测试集 + 中文自建 LLM-as-Judge

- 状态：已采纳
- 决策：
  1. 测试集不用公开医学 QA 数据集（与知识库不匹配），而是从 Milvus 采样 chunk 让 LLM 反向出题（question generation），ground-truth 即该 chunk——标注零成本且与检索目标严格对齐；多跳题取跨文档 chunk 对出对比题
  2. 生成层指标不用 RAGAS（英文 prompt 直译中文不可控），自建中文 judge prompt（忠实度/相关性，0-1 + issues）
- 已知局限（报告与 README 均如实标注）：样本量小（生成层 9 个有效样本）；合成分布偏"可答单跳"；judge 与被评系统同模型系存在自评偏差
- 结果：拒答率 100% / 急症拦截 100% / in-KB 回答率 75% / 忠实度 0.833——重排消融与拒答-误拒权衡均有数据支撑
