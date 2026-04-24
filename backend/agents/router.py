import logging
from .sales_agent import SalesAgent
from .finance_agent import FinanceAgent
from .general_agent import GeneralAgent
from data_layer.loader import DataLoader

logger = logging.getLogger(__name__)


class RouterResponse:
    """Wraps router response"""
    def __init__(self, domain: str, response: str, used_db: bool):
        self.domain = domain
        self.response = response
        self.used_db = used_db

    def to_dict(self):
        return {
            "domain": self.domain,
            "response": self.response,
            "used_db": self.used_db
        }


class QueryRouter:
    """Route queries to appropriate agents: SALES -> SalesAgent | FINANCE -> FinanceAgent | GENERAL -> Claude"""

    def __init__(self, data_loader: DataLoader, langsmith_client=None):
        self.data_loader = data_loader
        self.langsmith_client = langsmith_client  # LangSmith client (optional)

        self.sales_agent = SalesAgent(data_loader)
        self.finance_agent = FinanceAgent(data_loader)
        self.general_agent = GeneralAgent()

        self.knowledge_cache = {
            "ebitda": "EBITDA = Earnings Before Interest, Taxes, Depreciation, and Amortization. A measure of operational profitability.",
            "gross margin": "Gross Margin = (Revenue - COGS) / Revenue * 100%. Measures profit on each euro of sales.",
            "sales pipeline": "Sales pipeline: the set of opportunities at various closing stages (Prospect -> Qualified -> Proposal -> Negotiation -> Closed).",
            "deal stage": "Deal stages typically: Qualification -> Proposal -> Negotiation -> Closed Won/Lost.",
        }

    def _has_results(self, response_text: str) -> bool:
        """
        Check if response contains actual data/results.
        Returns False if response says "not found", "no results", "no access", error messages, etc.

        This helps the fallback system: if SALES/FINANCE say they don't have data,
        fallback to the next agent in the priority chain.
        """
        if not response_text:
            return False

        response_lower = response_text.lower()

        # Negative indicators (no results found or no access to data)
        no_results_patterns = [
            'no results',
            'not found',
            'no data',
            'nessun',
            'non trovato',
            'niente',
            'couldn\'t find',
            'unable to find',
            'error executing',
            'error retrieving',
            'non disponibile',
            'non ho accesso',
            'non ho informazioni',
            'no access to',
            'not available',
            'tables available', 
            'not in my',
            'outside my scope',
            'esula dal', 
            'mi dispiace',
        ]

        # Check if response contains negative patterns
        for pattern in no_results_patterns:
            if pattern in response_lower:
                return False

        # If response is very short (likely just "not found" or generic), consider it no results
        if len(response_text.strip()) < 50:
            return False

        return True

    def _extract_response_text(self, response):
        """Extract text from agent response (handles string, Message, and agno RunOutput)"""
        if isinstance(response, str):
            return response

        if hasattr(response, 'content') and isinstance(response.content, str):
            return response.content

        if hasattr(response, 'content') and isinstance(response.content, list):
            if len(response.content) > 0:
                first_item = response.content[0]
                if hasattr(first_item, 'text'):
                    return first_item.text
                elif isinstance(first_item, str):
                    return first_item

        if hasattr(response, 'text'):
            return response.text

        return str(response) if response else "No response generated"

    def _is_search_intent(self, query: str) -> bool:
        """Detect SEARCH intent: looking for specific people, companies, or data"""
        query_lower = query.lower()

        # Search verbs (Italian + English)
        search_verbs = ['cerca', 'find', 'search', 'dimmi', 'dammi', 'quale', 'which',
                       'get', 'retrieve', 'show', 'mostra', 'list', 'elenca']

        # Sales/business keywords
        sales_keywords = ['lead', 'deal', 'opportunity', 'prospect', 'client', 'customer',
                         'company', 'azienda', 'contact', 'role', 'ruolo', 'segment',
                         'enterprise', 'smb', 'inactive', 'cold', 'open']

        # Check: search verb + sales keyword = SEARCH intent
        has_search_verb = any(verb in query_lower for verb in search_verbs)
        has_sales_keyword = any(keyword in query_lower for keyword in sales_keywords)

        # "Chi" alone (person name query) only counts as SEARCH if also has sales keywords
        if 'chi ' in query_lower and not has_sales_keyword:
            return False

        # If has search verb, likely searching for data (SALES)
        if has_search_verb:
            return True

        # If mentions business entities, likely searching (SALES)
        if has_sales_keyword:
            return True

        return False

    def _is_analysis_intent(self, query: str) -> bool:
        """Detect ANALYSIS intent: financial/numerical analysis questions"""
        query_lower = query.lower()

        # Analysis verbs (Italian + English)
        analysis_verbs = ['calculate', 'analyz', 'compute', 'calcola', 'average',
                         'total', 'sum', 'count', 'media', 'totale', 'somma',
                         'confronta', 'compare', 'distribuzi', 'trend']

        # Finance keywords (Italian + English variants)
        finance_keywords = ['revenue', 'ricav', 'profit', 'profitt', 'margin', 'margin',
                           'cost', 'costo', 'price', 'prezzo', 'budget', 'ebitda',
                           'order', 'ordine', 'product', 'prodotto', 'category', 'categor',
                           'unit', 'unitari', 'financial', 'finanz',
                           'guadagno', 'fatturato', 'margine', 'ordini']

        # Check: analysis verb + finance keyword = ANALYSIS intent
        has_analysis_verb = any(verb in query_lower for verb in analysis_verbs)
        has_finance_keyword = any(keyword in query_lower for keyword in finance_keywords)

        if has_analysis_verb or has_finance_keyword:
            return True

        return False

    async def _classify_domain(self, query: str):
        """
        Intent-based domain classification with smart priority.
        Returns: SALES (search/database queries) | FINANCE (analysis) | GENERAL (knowledge)

        Priority:
        1. Knowledge cache -> GENERAL (definitive knowledge base)
        2. SEARCH intent -> SALES (e.g., "find Amadeo")
        3. ANALYSIS + FINANCE keywords -> FINANCE (e.g., "analyze margins")
        4. Default -> SALES (try data first, then fallback to FINANCE -> GENERAL)
        """
        try:
            query_lower = query.lower()

            # Priority 1: Check knowledge cache FIRST (definitive answers)
            for topic in self.knowledge_cache.keys():
                if topic in query_lower:
                    logger.info(f"Query classification - Knowledge cache hit for: {topic} -> GENERAL")
                    return "GENERAL"

            # Priority 2: Check for SEARCH intent -> SALES (has database access)
            is_search = self._is_search_intent(query)
            if is_search:
                logger.info(f"Query classification - Search intent detected -> SALES")
                return "SALES"

            # Priority 3: ANALYSIS intent (analyze, calculate, etc.) + FINANCE keywords -> FINANCE
            is_analysis = self._is_analysis_intent(query)
            if is_analysis:
                logger.info(f"Query classification - Analysis intent detected -> FINANCE")
                return "FINANCE"

            # Default: SALES (try data first, then fallback to FINANCE -> GENERAL)
            logger.info(f"Query classification - No intent detected, defaulting to SALES")
            return "SALES"

        except Exception as e:
            logger.warning(f"Error classifying domain: {e}")
            return "SALES"  # Default to SALES with fallback

    async def _route_to_sales(self, query: str):
        """Route to SalesAgent"""
        logger.info("...Routing to SalesAgent")
        response = await self.sales_agent.run(query)

        return RouterResponse(
            domain="SALES",
            response=self._extract_response_text(response),
            used_db=True
        )

    async def _route_to_finance(self, query: str):
        """Route to FinanceAgent"""
        logger.info("...Routing to FinanceAgent")
        response = await self.finance_agent.run(query)

        return RouterResponse(
            domain="FINANCE",
            response=self._extract_response_text(response),
            used_db=True
        )

    async def _route_to_general(self, query: str):
        """Route to GeneralAgent (Claude)"""
        logger.info("...Routing to GeneralAgent (Claude)")
        response = await self.general_agent.run(query)

        return RouterResponse(
            domain="GENERAL",
            response=self._extract_response_text(response),
            used_db=False
        )

    async def handle_query(self, query: str):
        """
        Main routing logic with smart classification + fallback.

        Strategy:
        1. If CLEARLY FINANCE (analysis intent) -> Go directly to FINANCE
        2. If CLEARLY SALES (search intent) -> Go directly to SALES
        3. If AMBIGUOUS -> Try SALES first, fallback to FINANCE -> GENERAL
        """
        try:
            # Check knowledge cache (fast path for common questions)
            query_lower = query.lower()
            for topic, answer in self.knowledge_cache.items():
                if topic in query_lower:
                    logger.info(f"Cache hit for topic: {topic}")
                    return RouterResponse(
                        domain="GENERAL",
                        response=answer,
                        used_db=False
                    )

            # Use smart classification to route directly when intent is clear
            domain = await self._classify_domain(query)

            # If clearly FINANCE, go directly (no need to try SALES first)
            if domain == "FINANCE":
                logger.info(f"Classified as FINANCE (analysis intent), routing directly")
                response = await self._route_to_finance(query)
                if self._has_results(response.response):
                    logger.info("SUCCESS! FINANCE found results")
                    return response
                logger.info("ERROR! FINANCE found no results, fallback to GENERAL")
                return await self._route_to_general(query)

            # If clearly SALES, go directly (no need to try FINANCE)
            if domain == "SALES":
                logger.info(f"Classified as SALES (search intent), routing directly")
                response = await self._route_to_sales(query)
                if self._has_results(response.response):
                    logger.info("SUCCESS! SALES found results")
                    return response
                logger.info("ERROR! SALES found no results, fallback to FINANCE")
                # Fallback from SALES to FINANCE
                response = await self._route_to_finance(query)
                if self._has_results(response.response):
                    logger.info("SUCCESS! FINANCE found results (via fallback from SALES)")
                    return response
                logger.info("ERROR! FINANCE found no results, fallback to GENERAL")
                return await self._route_to_general(query)

            # If ambiguous (GENERAL classification), try SALES first then fallback
            logger.info(f"Classified as GENERAL (ambiguous intent), trying SALES first with fallback")
            response = await self._route_to_sales(query)
            if self._has_results(response.response):
                logger.info("SUCCESS! SALES found results")
                return response
            logger.info("ERROR! SALES found no results, trying FINANCE")

            response = await self._route_to_finance(query)
            if self._has_results(response.response):
                logger.info("SUCCESS! FINANCE found results")
                return response
            logger.info("ERROR! FINANCE found no results, fallback to GENERAL")

            # Final fallback to GENERAL
            return await self._route_to_general(query)

        except Exception as e:
            logger.error(f"Error handling query: {e}", exc_info=True)
            raise
