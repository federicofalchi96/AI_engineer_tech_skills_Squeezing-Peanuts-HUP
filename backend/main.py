from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os
import logging
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cost control configuration
COST_CAP_USD = float(os.getenv("COST_CAP_USD", 0.20))
COST_WARN_THRESHOLD_USD = float(os.getenv("COST_WARN_THRESHOLD_USD", 0.15))

from agents.router import QueryRouter
from data_layer.loader import DataLoader
from models.schemas import ChatRequest, ChatResponse, LogQueryRequest, LogQueryResponse
from observability import CostCalculator, ObservabilityLogger

data_loader = None
router = None
obs_logger = None

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage app lifecycle
    """
    global data_loader, router, obs_logger

    try:
        logger.info("Starting lifespan...")
        data_loader = DataLoader()
        logger.info(f"Data loader initialized: {data_loader}")
        
        obs_logger = ObservabilityLogger()
        logger.info(f"Observability logger initialized")

        router = QueryRouter(data_loader, langsmith_client=obs_logger.langsmith_client)
        logger.info(f"Query router initialized: {router}")

        yield

        try:
            logger.info("Shutting down...")
            if data_loader:
                data_loader.close()
            logger.info("Cleanup complete")

        except Exception as e:
            logger.error(f"Shutdown error: {e}")

    except Exception as e:
        logger.error(f"Error occurred during app lifecycle: {e}", exc_info=True)
        raise


app = FastAPI(title="Squeezing Peanuts / HUP",
              description="Multiagent AI platform with Sales and Finance agents",
              version="1.0.0",
              lifespan=lifespan)

app.state.limiter = limiter


async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


# for the moment allowed origins
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,http://localhost:8001"
).split(",")

logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "message": "Service is running", "version": "1.0.0"}


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("2/minute")
async def chat(request: Request, chat_req: ChatRequest) -> ChatResponse:
    """Main chat endpoint"""
    try:
        query = chat_req.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Invalid query")
        if not router:
            raise HTTPException(status_code=500, detail="Service not initialized")

        # Check session cost limit
        if obs_logger:
            stats = obs_logger.get_session_stats()
            total_cost = stats.get("total_cost_usd", 0.0)
            if total_cost >= COST_CAP_USD:
                raise HTTPException(
                    status_code=429,
                    detail=f"Session cost limit reached: ${total_cost:.6f} >= ${COST_CAP_USD:.2f}"
                )
            if total_cost > COST_WARN_THRESHOLD_USD:
                logger.warning(f"Session cost warning: ${total_cost:.6f} >= ${COST_WARN_THRESHOLD_USD:.2f}")

        logger.info(f"Processing query: {query[:50]}...")

        result = await router.handle_query(query)

        # Convert RouterResponse to dict
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else result

        return ChatResponse(
            response=result_dict['response'],
            domain=result_dict['domain'],
            used_db=result_dict['used_db'],
            status="OK",
            query=query
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@app.get("/agents")
@limiter.limit("30/minute")
async def list_agents(request: Request):
    """List all available agents"""

    return {
        "agents" : [
            {
                "name" : "SalesAgent",
                "description" : "Agent for handling sales-related queries",
                "example" : "Which leads have had no activity in 30 days with open deals above €20k?"
            },
            {
                "name" : "FinanceAgent",
                "description" : "Agent for handling finance-related queries",
                "example" : "What is the current Q3 revenue projection?"
            },
            {
                "name" : "GeneralAgent",
                "description" : "Agent for handling general queries",
                "example" : "What is the capital of France?"
            }
        ]
    }



@app.post("/log-query", response_model=LogQueryResponse)
async def log_query(req: LogQueryRequest):
    """
    Log a query with tokens and costs
    The frontend calls this endpoint AFTER receiving a response from /chat.
    """
    try:
        if not obs_logger:
            raise HTTPException(status_code=500, detail="Observability logger not initialized")

        trace_id, cost_usd = obs_logger.log_query({
            "query": req.query,
            "response": req.response,
            "domain": req.domain,
            "used_db": req.used_db,
            "trace_id": req.trace_id
        })

        logger.info(f"Logged query {trace_id} - Cost: ${cost_usd:.6f}")

        return LogQueryResponse(
            trace_id=trace_id,
            cost_usd=cost_usd,
            status="logged"
        )

    except Exception as e:
        logger.error(f"Error logging query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats():
    """
    Get session statistics (total costs, tokens per domain, etc.)
    """
    try:
        if not obs_logger:
            raise HTTPException(status_code=500, detail="Observability logger not initialized")

        stats = obs_logger.get_session_stats()
        return stats

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cost-status")
async def cost_status():
    """
    Get session cost status with limit information
    """
    try:
        if not obs_logger:
            raise HTTPException(status_code=500, detail="Observability logger not initialized")

        stats = obs_logger.get_session_stats()
        total_cost = stats.get("total_cost_usd", 0.0)
        remaining = max(0, COST_CAP_USD - total_cost)
        percentage = min(100, (total_cost / COST_CAP_USD * 100)) if COST_CAP_USD > 0 else 0

        return {
            "total_cost": round(total_cost, 6),
            "cap": COST_CAP_USD,
            "remaining": round(remaining, 6),
            "percentage": round(percentage, 1),
            "exceeded": total_cost >= COST_CAP_USD,
            "warning": total_cost > COST_WARN_THRESHOLD_USD
        }

    except Exception as e:
        logger.error(f"Error getting cost status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))

    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")