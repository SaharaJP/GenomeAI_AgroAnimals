"""Context helper modules: data loading, KPI computation, attention-cow flagging."""
from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore
from web_cabinet.ai.context_helpers.kpi import compute_today_kpi, compute_period_trends
from web_cabinet.ai.context_helpers.attention import flag_attention_cows

__all__ = [
    "DemoDataStore",
    "compute_today_kpi",
    "compute_period_trends",
    "flag_attention_cows",
]
