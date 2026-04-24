import asyncio
from agno.models.anthropic import Claude
from agno.agent import Agent
from data_layer.loader import DataLoader
import logging
from langsmith import traceable  # Used for SalesAgent.run chain tracing


logger = logging.getLogger(__name__)


class SalesAgent:
    """Sales agent specialized in lead and deal management analysis"""

    def __init__(self, data_loader: DataLoader):
        """
        Args:
            data_loader (DataLoader): An instance of the data loader.
        """
        self.data_loader = data_loader

        # langsmith traceable
        @traceable(
            name="SalesAgent.find_cold_leads",
            run_type="tool"
        )
        def find_cold_leads() -> str:
            """Get inactive leads (30+ days) with open deals above €20k"""
            try:
                results = self.data_loader.get_cold_leads_with_deals(days=30, min_deal_value=20000)

                if not results:
                    return "No cold leads found with open deals exceeding €20k in the past 30 days."

                output = f"Found {len(results)} inactive leads with open deals above €20k:\n\n"
                total_value = 0

                for row in results:
                    name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
                    company = row.get('company', '')
                    segment = row.get('segment', '')
                    deal_value = float(row.get('value_eur', 0))
                    deal_stage = row.get('stage', '')
                    last_activity = row.get('last_activity', 'No activity')

                    output += f"• **{name}** ({company}) - Segment: {segment}\n"
                    output += f"  Deal: €{deal_value:,.0f} | Stage: {deal_stage}\n"
                    output += f"  Last Activity: {last_activity}\n\n"
                    total_value += deal_value

                output += f"**Total Pipeline Value at Risk: €{total_value:,.0f}**"
                logger.info(f"Found {len(results)} cold leads")
                return output

            except Exception as e:
                logger.error(f"Cold leads query failed: {e}")
                return f"Error retrieving cold leads data: {str(e)}"

        # langsmith traceable
        @traceable(
            name="SalesAgent.find_open_opportunities",
            run_type="tool"
        )
        def find_open_opportunities(min_value: float = 50000) -> str:
            """Get all open opportunities above a certain value"""
            try:
                results = self.data_loader.get_open_deals_by_value(min_deal_value=min_value)

                if not results:
                    return f"No open opportunities found exceeding €{min_value:,.0f}."

                output = f"Found {len(results)} open opportunities above €{min_value:,.0f}:\n\n"
                total_value = 0

                for row in results:
                    name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
                    company = row.get('company', '')
                    segment = row.get('segment', '')
                    deal_value = float(row.get('value_eur', 0))
                    deal_stage = row.get('stage', '')
                    last_activity = row.get('last_activity', 'No activity')

                    output += f"• **{name}** ({company}) - Segment: {segment}\n"
                    output += f"  Opportunity: €{deal_value:,.0f} | Stage: {deal_stage}\n"
                    output += f"  Last Activity: {last_activity}\n\n"
                    total_value += deal_value

                output += f"**Total Pipeline Value: €{total_value:,.0f}**"
                logger.info(f"Found {len(results)} open opportunities")
                return output

            except Exception as e:
                logger.error(f"Open opportunities query failed: {e}")
                return f"Error retrieving opportunities data: {str(e)}"

        # langsmith traceable
        @traceable(
            name="SalesAgent.execute_sql",
            run_type="tool"
        )
        def execute_sql(sql_query: str) -> str:
            """Execute custom SQL query on sales data.
            Available tables:
            - leads (lead_id, first_name, last_name, company, segment, created_at)
            - deals (deal_id, lead_id, value_eur, stage, created_at)
            - activities (lead_id, date, type)

            Examples:
            - "SELECT COUNT(*) FROM deals WHERE stage = 'Negotiation'"
            - "SELECT * FROM leads WHERE segment = 'Enterprise'"
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
            name="SalesAgent",
            model=Claude(id="claude-haiku-4-5-20251001"),
            description="Expert in analyzing sales data and managing leads and deals",
            instructions="""You are a senior sales analyst with access to a sales database.

            Available data:
            - leads table: lead_id, first_name, last_name, company, segment, created_at, role, email
            - deals table: deal_id, lead_id, value_eur, stage, created_at
            - activities table: lead_id, date, type

            CRITICAL RULES:
            1. If user mentions a SPECIFIC LEAD NAME -> ALWAYS use execute_sql() IMMEDIATELY
            Example: "Find Amadeo Cabrini" -> Run: SELECT * FROM leads WHERE first_name='Amadeo' AND last_name='Cabrini'
            2. If user asks about a SPECIFIC COMPANY -> ALWAYS use execute_sql()
            Example: "Find info about Luria Group" -> Run: SELECT * FROM leads WHERE company='Luria Group'
            3. If user asks general sales questions without specific names/companies -> Use find_cold_leads() or find_open_opportunities()

            Your tools:
            - execute_sql() - For ANY custom query on leads, deals, activities
            - find_cold_leads() - For inactive leads with open deals
            - find_open_opportunities() - For high-value opportunities

            When using execute_sql():
            - Always include all fields: SELECT * FROM leads WHERE...
            - Always provide complete information about the lead (name, role, company, segment, email)

            RESPONSE FORMAT:
            - Directly answer the question with data
            - Provide all relevant details from query results
            - No excuses about missing tools when data exists in database""",
            tools=[find_cold_leads, find_open_opportunities, execute_sql],
            markdown=True
        )

    # langsmith traceable
    @traceable(
        name="SalesAgent.run",
        run_type="chain"
    )
    async def run(self, query: str):
        """Execute query asynchronously
        Args:
            query (str): The query to execute
        Returns:
            The result of the query execution
        """
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
            
            return "No relevant information found."
            
        except Exception as e:
            logger.error(f"Error occurred while getting event loop: {e}")
            return f"Error occurred: {e}"