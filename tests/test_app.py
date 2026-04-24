"""
Complete test suite for Squeezing Peanuts application.
Tests for cost flow, frontend-backend integration, and agent SQL capabilities.
"""

import json
import tempfile
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Set up test environment
os.environ['COST_CAP_USD'] = '0.20'
os.environ['COST_WARN_THRESHOLD_USD'] = '0.15'

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import pytest
from data_layer.loader import DataLoader
from agents.sales_agent import SalesAgent
from agents.finance_agent import FinanceAgent


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def data_loader():
    """Initialize data loader once per session"""
    # Get the backend data directory relative to test file location
    test_dir = Path(__file__).parent
    project_root = test_dir.parent
    data_dir = project_root / "backend" / "data"
    return DataLoader(data_dir=str(data_dir))


@pytest.fixture
def sales_agent(data_loader):
    """Create a fresh SalesAgent for each test"""
    return SalesAgent(data_loader)


@pytest.fixture
def finance_agent(data_loader):
    """Create a fresh FinanceAgent for each test"""
    return FinanceAgent(data_loader)


# ============================================================================
# SALES AGENT TESTS (SQL Integration)
# ============================================================================

class TestSalesAgentSQL:
    """Test Sales Agent with SQL queries"""

    @pytest.mark.asyncio
    async def test_deal_stage_query(self, sales_agent):
        """Test: How many deals in Negotiation stage?"""
        response = await sales_agent.run("How many deals are in Negotiation stage?")

        assert response is not None, "Response should not be None"
        assert len(response) > 0, "Response should not be empty"
        assert isinstance(response, str), "Response should be a string"
        print(f"\n[PASS] Deal stage query returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_enterprise_customers_query(self, sales_agent):
        """Test: Show all Enterprise segment customers"""
        response = await sales_agent.run("Show me all Enterprise customers")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] Enterprise customers query returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_closed_deals_query(self, sales_agent):
        """Test: List closed won deals"""
        response = await sales_agent.run("Which deals are Closed Won?")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] Closed deals query returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_cold_leads_predefined_tool(self, sales_agent):
        """Test: Use predefined cold leads tool"""
        response = await sales_agent.run("Find me cold leads with high-value deals")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] Cold leads tool returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_opportunities_predefined_tool(self, sales_agent):
        """Test: Use predefined open opportunities tool"""
        response = await sales_agent.run("What are the open opportunities above 50k?")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] Open opportunities tool returned: {len(response)} chars")


# ============================================================================
# FINANCE AGENT TESTS (SQL Integration)
# ============================================================================

class TestFinanceAgentSQL:
    """Test Finance Agent with SQL queries"""

    @pytest.mark.asyncio
    async def test_total_orders_query(self, finance_agent):
        """Test: Count total orders in database"""
        response = await finance_agent.run("How many total orders do we have?")

        assert response is not None, "Response should not be None"
        assert len(response) > 0, "Response should not be empty"
        assert isinstance(response, str), "Response should be a string"
        print(f"\n[PASS] Total orders query returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_revenue_by_category_query(self, finance_agent):
        """Test: Get total revenue breakdown by category"""
        response = await finance_agent.run("What's the total revenue by product category?")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] Revenue by category query returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_highest_revenue_category_query(self, finance_agent):
        """Test: Which category generates most revenue?"""
        response = await finance_agent.run("Which product category has the highest total revenue?")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] Highest revenue category query returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_high_value_orders_query(self, finance_agent):
        """Test: Orders above specific price threshold"""
        response = await finance_agent.run("Show me orders with unit price above 100 EUR")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] High value orders query returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_margins_predefined_tool(self, finance_agent):
        """Test: Use predefined margins analysis tool"""
        response = await finance_agent.run("Analyze gross margins by category")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] Margins analysis tool returned: {len(response)} chars")

    @pytest.mark.asyncio
    async def test_low_margin_categories_implicit(self, finance_agent):
        """Test: Identify underperforming categories (should use SQL)"""
        response = await finance_agent.run("Which categories are underperforming with margins below 40%?")

        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        print(f"\n[PASS] Low margin categories query returned: {len(response)} chars")


# ============================================================================
# COST FLOW TESTS (Original tests from test_cost_flow.py)
# ============================================================================

class TestCostFlow:
    """Test the complete cost tracking and blocking flow"""

    def test_complete_cost_flow(self):
        """Test cost tracking, calculation, and blocking"""
        from backend.main import (
            ObservabilityLogger, CostCalculator, COST_CAP_USD,
            COST_WARN_THRESHOLD_USD
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ObservabilityLogger(logs_dir=tmpdir)

            # Step 1: Initial state
            stats = logger.get_session_stats()
            assert stats['total_cost_usd'] == 0.0
            assert stats['total_queries'] == 0

            # Step 2: Log query
            trace_id_1, cost_1 = logger.log_query({
                "query": "What is EBITDA?",
                "response": "EBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortization.",
                "domain": "GENERAL",
                "used_db": False
            })
            assert trace_id_1 is not None
            assert cost_1 > 0

            # Step 3: Verify stats updated
            stats = logger.get_session_stats()
            assert stats['total_queries'] == 1
            assert stats['total_cost_usd'] > 0.0

            print(f"\n[PASS] Cost flow test passed")


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for frontend-backend interaction"""

    @pytest.mark.asyncio
    async def test_multiple_agent_queries(self, sales_agent, finance_agent):
        """Test sequential queries to different agents"""

        # Sales query
        sales_response = await sales_agent.run("Show Enterprise deals")
        assert sales_response is not None and len(sales_response) > 0

        # Finance query
        finance_response = await finance_agent.run("Revenue by category")
        assert finance_response is not None and len(finance_response) > 0

        print(f"\n[PASS] Integration test: 2 agents ran successfully")

    @pytest.mark.asyncio
    async def test_agent_responds_without_errors(self, sales_agent, finance_agent):
        """Test that agents handle queries gracefully"""

        # Even malformed/odd queries should not crash, just return no results
        response1 = await sales_agent.run("xyz abc qwerty")
        assert isinstance(response1, str)

        response2 = await finance_agent.run("hello world foo bar")
        assert isinstance(response2, str)

        print(f"\n[PASS] Error handling test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
