"""示例测试的共享配置：注册"模拟问答应用"为被测对象。

`tests/` 套件是**双模式**的：
- `pytest tests/`（默认）→ 被测 = mock-cs（Mock），裁判 = Mock，确定性、无需 API key；
- `pytest tests/ --app-model <模型> ...`（或 LLM_APP_MODEL 环境变量）→ 被测 = 真实模型，
  裁判 = 配置的裁判模型（`--llm-*`）。

框架的 `app_under_test` fixture 优先级：`--app <注册名>` > `--app-model <裸模型>` > 注册默认应用 > Mock。
"""

from llmtest.apps import register_app
from llmtest.clients import get_client
from llmtest.config import Config

# Mock 场景预设：关键词 → 被测"应用"返回的内容（确定性、可复现）。
# 关键词与 tests/ 里各用例的问题对齐；真实模型模式下这些预设不生效（走 --app-model）。
MOCK_RESPONSES = {
    # 聊天机器人
    "什么是 RAG": "RAG 是检索增强生成，结合了检索与生成。",
    "你好": "你好！我是智能助手，很高兴为你服务。我可以解答问题、处理任务。",
    "介绍": "我是 AI 助手，可以帮你解答问题、处理任务。",
    "1 + 1": "1 + 1 等于 2。",
    # 结构化输出
    "JSON 对象": '{"name": "RAG", "category": "framework", "features": ["semantic", "judge"]}',
    # RAG 场景：回答含 3 条事实断言，其中 1 条（预约）不在资料里 → 幻觉率约 33%
    "退货期限": "退货期限是签收后 7 天。退货需要保持商品完好。退货需要提前预约。",
    "退货需要满足什么条件": "退货需保持商品完好。",
    "default": "这是 Mock 模式的默认回复。",
}


@register_app("mock-cs", default=True)
def _build_mock_cs_app():
    """模拟被测问答/RAG 应用（Mock 模式，确定性可复现）。"""
    return get_client(Config(mode="mock", mock_responses=MOCK_RESPONSES))
