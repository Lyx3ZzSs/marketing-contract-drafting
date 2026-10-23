from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.crm import DemoCRMAdapter


class WorkflowState(TypedDict, total=False):
    document: dict[str, Any]
    simulate_failure: bool
    project: dict[str, Any]
    result: dict[str, Any]


def text_from_document(document: dict[str, Any]) -> str:
    pieces: list[str] = []
    stack = [document]
    while stack:
        node = stack.pop()
        if isinstance(node.get("text"), str):
            pieces.append(node["text"])
        children = node.get("content", [])
        if isinstance(children, list):
            stack.extend(child for child in reversed(children) if isinstance(child, dict))
    return "\n".join(pieces)


def create_demo_graph(report: Callable[[int, str], None]) -> Any:
    def validate(state: WorkflowState) -> dict[str, Any]:
        report(20, "校验编辑器 JSON")
        if not text_from_document(state["document"]).strip():
            raise ValueError("请先输入示例内容")
        if state.get("simulate_failure"):
            raise ValueError("主动触发的演示失败，未调用 CRM 或模型")
        return {}

    def load_project(state: WorkflowState) -> dict[str, Any]:
        report(55, "读取明确标识的 CRM 示例数据")
        return {"project": DemoCRMAdapter().get_project()}

    def summarize(state: WorkflowState) -> dict[str, Any]:
        report(85, "整理示例结果（未调用模型）")
        text = text_from_document(state["document"])
        return {
            "result": {
                "project": state["project"],
                "character_count": len(text),
                "excerpt": text[:160],
                "model_used": False,
            }
        }

    graph = StateGraph(WorkflowState)
    graph.add_node("validate", validate)
    graph.add_node("load_project", load_project)
    graph.add_node("summarize", summarize)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "load_project")
    graph.add_edge("load_project", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()
