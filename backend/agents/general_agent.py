import asyncio
from agno.models.anthropic import Claude
from agno.agent import Agent
import logging
from langsmith import traceable


logger = logging.getLogger(__name__)

# langsmith traceable
class GeneralAgent:
    """General knowledge agent for non-domain-specific queries"""

    def __init__(self):
        """Initialize GeneralAgent"""
        self.agent = Agent(
            name="GeneralAgent",
            model=Claude(id="claude-haiku-4-5-20251001"),
            description="General knowledge assistant for diverse topics",
            instructions="""You are a helpful and knowledgeable assistant.
                        Your role:
                        1. Answer questions accurately and concisely
                        2. Provide clear explanations
                        3. Admit when you don't know something

                        Structure your response with:
                        - Direct answer to the question
                        - Key points or examples
                        - Additional context if relevant""",
            markdown=True
        )

    # langsmith traceable
    @traceable(
        name="GeneralAgent.run",
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
            logger.info(f"GeneralAgent processed query successfully")
            return response
        except Exception as e:
            logger.error(f"GeneralAgent error: {e}")
            raise
