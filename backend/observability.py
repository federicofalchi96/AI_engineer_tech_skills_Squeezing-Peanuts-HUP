"""
Observability and cost tracking module
Handles cost calculation, query logging, and session statistics
"""

import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import os

logger = logging.getLogger(__name__)

# LangSmith integration (lazy import)
try:
    from langsmith import Client
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False


class CostCalculator:
    """Calculates costs based on Claude model usage"""

    HAIKU_INPUT_PRICE = 0.80
    HAIKU_OUTPUT_PRICE = 4.00
    TOKENS_PER_CHAR_INPUT = 0.25
    TOKENS_PER_CHAR_OUTPUT = 0.20

    @staticmethod
    def estimate_tokens(input_text: str, output_text: str) -> Dict[str, int]:
        """Estimate input and output tokens based on text length"""
        input_tokens = max(50, int(len(input_text) * CostCalculator.TOKENS_PER_CHAR_INPUT))
        output_tokens = max(50, int(len(output_text) * CostCalculator.TOKENS_PER_CHAR_OUTPUT))
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens
        }

    @staticmethod
    def calculate_cost(input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for query"""
        input_cost = (input_tokens * CostCalculator.HAIKU_INPUT_PRICE) / 1_000_000
        output_cost = (output_tokens * CostCalculator.HAIKU_OUTPUT_PRICE) / 1_000_000
        return input_cost + output_cost


class ObservabilityLogger:
    """Logs queries, tokens, and costs to LangSmith and file"""

    def __init__(self, project_name: str = "squeezing-peanuts-prod", logs_dir: str = "logs"):
        self.project_name = project_name
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)

        self.langsmith_client = None
        if LANGSMITH_AVAILABLE:
            try:
                api_key = os.getenv("LANGSMITH_API_KEY")
                if api_key:
                    self.langsmith_client = Client(api_key=api_key)
                    logger.info(f"✓ LangSmith client initialized successfully")
                else:
                    logger.warning("LANGSMITH_API_KEY not set")
            except Exception as e:
                logger.error(f"✗ LangSmith client init failed: {e}", exc_info=True)

    def log_query(self, trace_data: Dict[str, Any]) -> tuple:
        """Log a query with tokens and costs. Returns (trace_id, cost_usd)"""
        trace_id = trace_data.get("trace_id") or str(uuid.uuid4())

        token_info = CostCalculator.estimate_tokens(
            trace_data.get("query", ""),
            trace_data.get("response", "")
        )
        cost_usd = CostCalculator.calculate_cost(
            token_info["input_tokens"],
            token_info["output_tokens"]
        )

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "trace_id": trace_id,
            "query": trace_data.get("query", "")[:500],
            "domain": trace_data.get("domain", "UNKNOWN"),
            "used_db": trace_data.get("used_db", False),
            "input_tokens": token_info["input_tokens"],
            "output_tokens": token_info["output_tokens"],
            "total_tokens": token_info["total_tokens"],
            "cost_usd": cost_usd
        }

        # Log to file
        log_file = self.logs_dir / "queries.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        return trace_id, cost_usd

    def get_session_stats(self) -> Dict[str, Any]:
        """Read current session statistics"""
        log_file = self.logs_dir / "queries.jsonl"

        if not log_file.exists():
            return {
                "total_queries": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_cost_per_query": 0.0
            }

        logs = []
        with open(log_file, "r") as f:
            for line in f:
                try:
                    logs.append(json.loads(line))
                except:
                    pass

        if not logs:
            return {
                "total_queries": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_cost_per_query": 0.0
            }

        total_tokens = sum(log.get("total_tokens", 0) for log in logs)
        total_cost = sum(log.get("cost_usd", 0.0) for log in logs)

        return {
            "total_queries": len(logs),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_query": round(total_cost / len(logs), 6) if logs else 0.0,
            "by_domain": self._aggregate_by_domain(logs)
        }

    @staticmethod
    def _aggregate_by_domain(logs: list) -> Dict[str, Any]:
        """Aggregate statistics by domain"""
        by_domain = {}
        for log in logs:
            domain = log.get("domain", "UNKNOWN")
            if domain not in by_domain:
                by_domain[domain] = {"count": 0, "total_tokens": 0, "total_cost": 0.0}
            by_domain[domain]["count"] += 1
            by_domain[domain]["total_tokens"] += log.get("total_tokens", 0)
            by_domain[domain]["total_cost"] += log.get("cost_usd", 0.0)

        for domain in by_domain:
            by_domain[domain]["total_cost"] = round(by_domain[domain]["total_cost"], 6)

        return by_domain
