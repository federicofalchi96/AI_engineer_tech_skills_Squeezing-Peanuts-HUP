import logging
import asyncio
from agno.agent import Agent
from agno.models.anthropic import Claude
from data_layer.loader import DataLoader
from langsmith import traceable  # Used for FinanceAgent.run chain tracing


logger = logging.getLogger(__name__)


class FinanceAgent:
    def __init__(self, data_loader: DataLoader):
        """Finance Agent specialized in revenue and margin analysis"""
        self.data_loader = data_loader


        # langsmith traceable
        @traceable(
            name="FinanceAgent.analyze_margins",
            run_type="tool"
        )
        def analyze_margins() -> str:
            """Analyze gross margins by product category"""
            try:
                all_margins = self.data_loader.get_margins_by_category()
                low_margins = self.data_loader.get_low_margin_categories(threshold=40.0)

                if not all_margins:
                    return "No margin data available in the database."

                total_revenue = sum(m.get('total_revenue', 0) for m in all_margins)
                avg_margin = sum(m.get('gross_margin_pct', 0) for m in all_margins) / len(all_margins) if all_margins else 0

                output = "## Margin Analysis by Category\n\n"
                output += "**Key Metrics:**\n"
                output += f"- Total Revenue: €{total_revenue:,.2f}\n"
                output += f"- Average Gross Margin: {avg_margin:.1f}%\n"
                output += f"- Categories at Risk (<40%): {len(low_margins)}\n\n"

                output += "### Category Breakdown:\n\n"
                for margin_row in sorted(all_margins, key=lambda x: x.get('total_revenue', 0), reverse=True):
                    category = margin_row.get('category', 'Unknown')
                    margin_pct = margin_row.get('gross_margin_pct', 0)
                    revenue = margin_row.get('total_revenue', 0)
                    orders = margin_row.get('order_count', 0)
                    rev_pct = (revenue / total_revenue * 100) if total_revenue else 0
                    status = " **AT RISK**" if margin_pct < 40 else "Healthy"

                    output += f"**{category}** | {status}\n"
                    output += f"- Margin: {margin_pct:.1f}% | Revenue: €{revenue:,.2f} ({rev_pct:.1f}%) | Orders: {orders}\n\n"

                logger.info(f"Analyzed {len(all_margins)} categories")
                return output

            except Exception as e:
                logger.error(f"Margin analysis error: {e}")
                return f"Error analyzing margins: {str(e)}"

        # langsmith traceable
        @traceable(
            name="FinanceAgent.execute_sql",
            run_type="tool"
        )
        def execute_sql(sql_query: str) -> str:
            """Execute custom SQL query on financial data.
            Available tables:
            - orders (category, quantity, unit_price_eur, unit_cost_eur, order_date)
            - deals (deal_id, lead_id, value_eur, stage, created_at) - sales data
            - leads (lead_id, first_name, last_name, company, segment, created_at)

            Examples:
            - "SELECT COUNT(*) FROM orders WHERE category = 'Software'"
            - "SELECT category, SUM(quantity) FROM orders GROUP BY category"
            """
            try:
                results = self.data_loader.query(sql_query)

                if not results:
                    return "Query executed but no results found."

                # Format results as readable text
                output = f"Query returned {len(results)} row(s):\n\n"
                for i, row in enumerate(results, 1):
                    output += f"{i}. {row}\n"

                logger.info(f"SQL query executed: {sql_query[:100]}")
                return output

            except Exception as e:
                logger.error(f"SQL query error: {e}")
                return f"Error executing query: {str(e)}"

        self.agent = Agent(
            name="FinanceAgent",
            model=Claude(id="claude-haiku-4-5-20251001"),
            description="Finance expert for revenue and margin analysis",
            instructions="""You are a financial analyst with access to financial and sales data.
                Available data:
                - orders table: category, quantity, unit_price_eur, unit_cost_eur, order_date
                - deals table: deal_id, lead_id, value_eur, stage, created_at
                - leads table: lead_id, first_name, last_name, company, segment, created_at

                Your role:
                1. Answer any finance question by writing SQL queries when needed
                2. Use execute_sql() for custom queries not covered by specific tools
                3. Use analyze_margins() for margin analysis by category
                4. Calculate revenue, costs, profitability metrics
                5. Provide strategic insights and optimization recommendations

                Always structure your response with:
                - Executive summary (key metrics)
                - Detailed analysis
                - Risk assessment
                - Strategic recommendations""",
            tools=[analyze_margins, execute_sql],
            markdown=True,
        )

    # langsmith traceable
    @traceable(
        name="FinanceAgent.run",
        run_type="chain"
    )
    async def run(self, query: str) -> str:
        """Execute finance query asynchronously"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.agent.run(query))
            
            # Handle string, Message object, or agno RunOutput
            if isinstance(response, str):
                return response
            
            # agno RunOutput has .content as string
            if hasattr(response, 'content') and isinstance(response.content, str):
                return response.content
            
            # Message object with .content[0].text
            if response and hasattr(response, 'content') and isinstance(response.content, list):
                if len(response.content) > 0:
                    first_item = response.content[0]
                    if hasattr(first_item, 'text'):
                        return first_item.text
                    elif isinstance(first_item, str):
                        return first_item
            
            return "No response generated"
            
        except Exception as e:
            logger.error(f"Finance agent error: {e}")
            return f"Error: {str(e)}"
 