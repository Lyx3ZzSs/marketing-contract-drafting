from typing import Any


class DemoCRMAdapter:
    """Synthetic development data only. Never represents a real CRM connection."""

    def get_project(self) -> dict[str, Any]:
        return {
            "source": "demo",
            "project_code": "DEMO-WIND-001",
            "project_name": "示例风电场（虚构数据）",
            "customer_name": "演示客户（非真实客户）",
        }
